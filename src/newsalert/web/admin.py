"""Admin view: inspect collector output and delivery operations.

Read-only except for promoting a 'review' candidate to selected or dropping a candidate.
Access requires a signed-in account listed in NEWSALERT_ADMIN_EMAILS.
"""
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select, update

from newsalert.db.base import utc_now
from newsalert.db.collector import (
    CollectorRun,
    Event,
    EventEvidence,
    GdeltCluster,
    RssItem,
    WikiCheck,
    WikiEntry,
)
from newsalert.db.session import DbSession
from newsalert.db.users import Delivery, Destination
from newsalert.web.security import AdminUser, admin_user, csrf_token, require_csrf

router = APIRouter(prefix="/admin", dependencies=[Depends(admin_user)])

BANDS = ("auto", "review", "drop")
EVENT_STATUSES = ("candidate", "selected", "dropped")
DELIVERY_STATUSES = ("pending", "sent", "failed", "skipped")
URL_PATTERN = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.IGNORECASE)


def format_timestamp(value: str | None) -> str:
    """Shorten stored ISO 8601 UTC text for tables; unknown formats are shown as-is."""
    if not value:
        return "—"
    match = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})", value)
    return f"{match[1]} {match[2]}" if match else value


def json_list(value: str | None) -> list:
    try:
        parsed = json.loads(value) if value else []
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def safe_link(value) -> str | None:
    return value if isinstance(value, str) and value.startswith(("https://", "http://")) else None


def redact_error(error: str | None, webhook_url: str | None) -> str | None:
    # last_error should already be credential-free; mask any URL as a second defence.
    if not error:
        return None
    if webhook_url:
        error = error.replace(webhook_url, "[webhook hidden]")
    return URL_PATTERN.sub("[URL hidden]", error)


def page_params(limit: int, offset: int) -> None:
    if not 1 <= limit <= 200 or offset < 0:
        raise HTTPException(422, "Limit must be 1–200 and offset must be nonnegative")


def choice(value: str | None, allowed: tuple[str, ...], name: str) -> str | None:
    if not value:
        return None
    if value not in allowed:
        raise HTTPException(422, f"Unknown {name}")
    return value


def render(request: Request, name: str, context: dict):
    return request.app.state.templates.TemplateResponse(
        request=request,
        name=name,
        context={"csrf": csrf_token(request), "is_admin": True, **context},
    )


def wiki_label(matched: bool | None) -> str:
    return "not checked" if matched is None else ("yes" if matched else "no")


@router.get("")
def overview(request: Request, user: AdminUser, session: DbSession, limit: int = 50):
    page_params(limit, 0)
    runs = session.scalars(select(CollectorRun).order_by(CollectorRun.id.desc()).limit(limit))
    event_counts = session.execute(
        select(Event.band, Event.status, func.count())
        .group_by(Event.band, Event.status)
        .order_by(Event.band, Event.status)
    ).all()
    delivery_counts = session.execute(
        select(Delivery.status, func.count()).group_by(Delivery.status).order_by(Delivery.status)
    ).all()
    checked, matched = session.execute(
        select(func.count(), func.coalesce(func.sum(WikiCheck.matched), 0)).where(
            WikiCheck.method == "keyword"
        )
    ).one()
    return render(
        request,
        "admin/overview.html",
        {
            "user": user,
            "section": "overview",
            "runs": list(runs),
            "event_counts": event_counts,
            "delivery_counts": delivery_counts,
            "wiki": {"checked": checked, "matched": matched},
        },
    )


@router.get("/events")
def events_page(
    request: Request,
    session: DbSession,
    band: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    page_params(limit, offset)
    band = choice(band, BANDS, "band")
    status = choice(status, EVENT_STATUSES, "status")
    query = (
        select(Event, WikiCheck.matched)
        .outerjoin(WikiCheck, (WikiCheck.event_id == Event.id) & (WikiCheck.method == "keyword"))
        .order_by(Event.last_run_id.desc(), Event.score.desc(), Event.id)
    )
    if band:
        query = query.where(Event.band == band)
    if status:
        query = query.where(Event.status == status)
    # Fetch one extra row to know whether a next page exists.
    rows = session.execute(query.limit(limit + 1).offset(offset)).all()
    filters = {"band": band or "", "status": status or "", "limit": limit}
    return render(
        request,
        "admin/events.html",
        {
            "section": "events",
            "rows": [(event, wiki_label(matched)) for event, matched in rows[:limit]],
            "filters": filters,
            "bands": BANDS,
            "statuses": EVENT_STATUSES,
            "offset": offset,
            "previous_offset": max(offset - limit, 0) if offset else None,
            "next_offset": offset + limit if len(rows) > limit else None,
        },
    )


def evidence_for(session, event_id: str) -> tuple[list[dict], list[dict]]:
    clusters, rss = [], []
    for evidence in session.scalars(
        select(EventEvidence).where(EventEvidence.event_id == event_id).order_by(EventEvidence.id)
    ):
        base = {"match_method": evidence.match_method, "confidence": evidence.confidence}
        if evidence.source == "gdelt":
            cluster = session.get(GdeltCluster, evidence.item_id)
            clusters.append(
                {
                    **base,
                    "item_id": evidence.item_id,
                    "cluster": cluster,
                    "keywords": json_list(cluster.keywords) if cluster else [],
                    "urls": [
                        (url, safe_link(url))
                        for url in (json_list(cluster.sample_urls) if cluster else [])
                    ],
                }
            )
        else:
            item = session.get(RssItem, evidence.item_id)
            rss.append(
                {
                    **base,
                    "item_id": evidence.item_id,
                    "item": item,
                    "link": safe_link(item.url) if item else None,
                }
            )
    return clusters, rss


@router.get("/events/{event_id}")
def event_detail(request: Request, event_id: str, session: DbSession):
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(404, "Event not found")
    # Iterate the mapped columns so fields added by the collector appear automatically.
    fields = [(column.key, getattr(event, column.key, None)) for column in Event.__table__.columns]
    clusters, rss = evidence_for(session, event_id)
    checks = []
    for check in session.scalars(
        select(WikiCheck).where(WikiCheck.event_id == event_id).order_by(WikiCheck.method)
    ):
        entry = session.get(WikiEntry, check.wiki_entry_id) if check.wiki_entry_id else None
        checks.append(
            {"check": check, "entry": entry, "shared_terms": json_list(check.shared_terms)}
        )
    deliveries = session.execute(
        select(Delivery, Destination)
        .join(Destination, Delivery.destination_id == Destination.id)
        .where(Delivery.event_id == event_id)
        .order_by(Delivery.id.desc())
    ).all()
    return render(
        request,
        "admin/event.html",
        {
            "section": "events",
            "event": event,
            "fields": fields,
            "clusters": clusters,
            "rss": rss,
            "checks": checks,
            "has_keyword_check": any(c["check"].method == "keyword" for c in checks),
            "deliveries": [
                delivery_view(delivery, destination, event.headline)
                for delivery, destination in deliveries
            ],
            "can_select": event.band == "review" and event.status == "candidate",
            "can_drop": event.status == "candidate",
        },
    )


def delivery_view(delivery: Delivery, destination: Destination | None, headline) -> dict:
    return {
        "id": delivery.id,
        "event_id": delivery.event_id,
        "headline": headline,
        "destination_id": delivery.destination_id,
        "destination_type": destination.type if destination else None,
        "status": delivery.status,
        "attempts": delivery.attempts,
        "last_error": redact_error(
            delivery.last_error, destination.webhook_url if destination else None
        ),
        "created_at": delivery.created_at,
        "next_attempt_at": delivery.next_attempt_at,
        "sent_at": delivery.sent_at,
    }


@router.get("/deliveries")
def deliveries_page(
    request: Request,
    session: DbSession,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    page_params(limit, offset)
    status = choice(status, DELIVERY_STATUSES, "status")
    query = (
        select(Delivery, Destination, Event.headline)
        .outerjoin(Destination, Delivery.destination_id == Destination.id)
        .outerjoin(Event, Delivery.event_id == Event.id)
        .order_by(Delivery.id.desc())
    )
    if status:
        query = query.where(Delivery.status == status)
    rows = session.execute(query.limit(limit + 1).offset(offset)).all()
    return render(
        request,
        "admin/deliveries.html",
        {
            "section": "deliveries",
            "deliveries": [delivery_view(*row) for row in rows[:limit]],
            "filters": {"status": status or "", "limit": limit},
            "statuses": DELIVERY_STATUSES,
            "previous_offset": max(offset - limit, 0) if offset else None,
            "next_offset": offset + limit if len(rows) > limit else None,
        },
    )


def transition(session, event_id: str, conditions: list, values: dict) -> dict:
    # Conditional UPDATE: a concurrent collector write cannot be overwritten, and an event
    # that is already 'selected' (final per the collector contract) never matches.
    result = session.execute(
        update(Event)
        .where(Event.id == event_id, Event.status == "candidate", *conditions)
        .values(updated_at=utc_now(), **values)
    )
    if result.rowcount != 1:
        event = session.get(Event, event_id)
        session.rollback()
        if event is None:
            raise HTTPException(404, "Event not found")
        raise HTTPException(409, f"Event is {event.band}/{event.status}; action not allowed")
    session.commit()
    return {"id": event_id, "status": values["status"]}


@router.post("/events/{event_id}/select", dependencies=[Depends(require_csrf)])
def select_event(event_id: str, user: AdminUser, session: DbSession):
    return transition(
        session,
        event_id,
        [Event.band == "review"],
        {"status": "selected", "selected_at": utc_now(), "note": f"selected by admin {user.email}"},
    )


@router.post("/events/{event_id}/drop", dependencies=[Depends(require_csrf)])
def drop_event(event_id: str, user: AdminUser, session: DbSession):
    return transition(
        session, event_id, [], {"status": "dropped", "note": f"dropped by admin {user.email}"}
    )
