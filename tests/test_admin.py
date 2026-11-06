"""Admin view: access control, pages and the select/drop actions. In-memory database only."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from newsalert.db import (
    Base,
    CollectorRun,
    Delivery,
    Destination,
    Event,
    EventEvidence,
    RssItem,
    User,
    WikiCheck,
)
from newsalert.settings import Settings
from newsalert.web.app import create_app

PASSWORD = "correct horse battery staple"
WEBHOOK = "https://hooks.slack.com/services/T123/B456/secret123"


@pytest.fixture
def app():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def configure(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    settings = Settings(secret_key="test-only-secret-" * 4, admin_emails="admin@example.com")
    yield create_app(settings, engine)
    engine.dispose()


def mutate(client, method, path, body=None):
    token = client.get("/api/auth/csrf").json()["csrf_token"]
    return client.request(method, path, json=body, headers={"X-CSRF-Token": token})


def login(app, email):
    client = TestClient(app)
    assert (
        mutate(
            client, "POST", "/api/auth/register", {"email": email, "password": PASSWORD}
        ).status_code
        == 201
    )
    return client


def seed(app):
    with Session(app.state.engine) as s:
        run = CollectorRun(
            window_start="2026-11-05T00:00:00+00:00",
            window_end="2026-11-06T00:00:00+00:00",
            status="ok",
            n_events=2,
        )
        s.add(run)
        s.flush()
        common = {
            "score": 100.0,
            "independent_outlets": 80,
            "first_seen": "2026-11-05T08:00:00+00:00",
            "last_run_id": run.id,
        }
        s.add_all(
            [
                Event(
                    id="evt-review",
                    headline="Paraguay president resigns",
                    band="review",
                    status="candidate",
                    rss_confirmations=1,
                    **common,
                ),
                Event(
                    id="evt-sel",
                    headline="Bomb threats disrupt flights",
                    band="auto",
                    status="selected",
                    selected_at="2026-11-05T09:00:00+00:00",
                    rss_confirmations=4,
                    **common,
                ),
            ]
        )
        item = RssItem(
            feed="bbc_world", guid="g1", url="https://www.bbc.co.uk/news/x", title="Peña resigns"
        )
        s.add(item)
        s.flush()
        s.add_all(
            [
                EventEvidence(
                    event_id="evt-review",
                    source="rss",
                    item_id=item.id,
                    match_method="url",
                    confidence=1.0,
                ),
                WikiCheck(event_id="evt-review", method="keyword", matched=True),
            ]
        )
        user = s.query(User).filter_by(email="admin@example.com").one()
        dest = Destination(user_id=user.id, type="slack", webhook_url=WEBHOOK)
        s.add(dest)
        s.flush()
        s.add(
            Delivery(
                event_id="evt-sel",
                destination_id=dest.id,
                status="failed",
                attempts=3,
                last_error=f"HTTP 500 from {WEBHOOK}",
            )
        )
        s.commit()


def test_non_admin_is_refused(app):
    client = login(app, "reader@example.com")
    assert client.get("/admin").status_code == 403
    assert client.get("/admin/events").status_code == 403


def test_signed_out_admin_page_redirects_to_login(app):
    response = TestClient(app).get("/admin", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/login"


def test_admin_pages_show_collector_output(app):
    client = login(app, "admin@example.com")
    seed(app)
    overview = client.get("/admin")
    assert overview.status_code == 200 and "1 of 1 checked events matched" in overview.text
    page = client.get("/admin/events?band=review").text
    assert "Paraguay president resigns" in page and "Bomb threats" not in page
    detail = client.get("/admin/events/evt-review").text
    assert "Peña resigns" in detail and "bbc_world" in detail


@pytest.mark.parametrize("matches", [(), (False, False, False), (True, False, True)])
def test_wikipedia_match_total_is_numeric_and_keyword_only(app, matches):
    client = login(app, "admin@example.com")
    seed(app)
    with Session(app.state.engine) as session:
        session.query(WikiCheck).delete()
        original = session.get(Event, "evt-review")
        for index, matched in enumerate(matches):
            event_id = f"evt-count-{index}"
            session.add(
                Event(
                    id=event_id,
                    headline="Count fixture",
                    score=100,
                    independent_outlets=80,
                    first_seen=original.first_seen,
                    last_run_id=original.last_run_id,
                    band="review",
                    status="candidate",
                )
            )
            session.flush()
            session.add(WikiCheck(event_id=event_id, method="keyword", matched=matched))
        # A different checker must not inflate the keyword agreement count.
        session.add(WikiCheck(event_id=original.id, method="llm", matched=True))
        session.commit()
    response = client.get("/admin")
    assert response.status_code == 200
    assert f"{sum(matches)} of {len(matches)} checked events matched" in response.text


def test_deliveries_page_never_shows_the_webhook(app):
    client = login(app, "admin@example.com")
    seed(app)
    html = client.get("/admin/deliveries").text
    assert "failed" in html and "secret123" not in html and WEBHOOK not in html


def test_select_and_drop_follow_the_collector_contract(app):
    client = login(app, "admin@example.com")
    seed(app)
    assert mutate(client, "POST", "/admin/events/evt-review/select").status_code == 200
    with Session(app.state.engine) as s:
        e = s.get(Event, "evt-review")
        assert e.status == "selected" and e.selected_at and "by admin" in e.note
    # Selected is final: neither a second select nor a drop may change it.
    assert mutate(client, "POST", "/admin/events/evt-sel/select").status_code == 409
    assert mutate(client, "POST", "/admin/events/evt-sel/drop").status_code == 409


def test_admin_actions_need_csrf(app):
    client = login(app, "admin@example.com")
    seed(app)
    assert client.post("/admin/events/evt-review/drop").status_code == 403
