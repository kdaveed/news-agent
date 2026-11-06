import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from newsalert.db.collector import Event
from newsalert.db.session import DbSession
from newsalert.db.users import Delivery, Destination, User
from newsalert.delivery.messages import TEST_NOTIFICATION, SendError, Target
from newsalert.web.schemas import DestinationCreate, DestinationUpdate, Login, Register
from newsalert.web.security import CurrentUser, csrf_token, dummy_hash, passwords, require_csrf

router = APIRouter()
api = APIRouter(prefix="/api", dependencies=[Depends(require_csrf)])


def destination_view(destination: Destination) -> dict:
    return {
        "id": destination.id,
        "type": destination.type,
        "email_address": destination.email_address,
        "webhook_url": "Configured · hidden" if destination.webhook_url else None,
        "enabled": destination.enabled,
        "created_at": destination.created_at,
    }


@router.get("/api/auth/csrf")
def get_csrf(request: Request):
    return {"csrf_token": csrf_token(request)}


@api.post("/auth/register", status_code=201)
def register(body: Register, request: Request, session: DbSession):
    user = User(
        email=str(body.email).strip().casefold(),
        password_hash=passwords.hash(body.password.get_secret_value()),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "An account with this email already exists") from None
    request.session.clear()
    request.session.update(user_id=user.id, csrf=secrets.token_urlsafe(32))
    return {"id": user.id, "email": user.email}


@api.post("/auth/login")
def login(body: Login, request: Request, session: DbSession):
    user = session.scalar(select(User).where(User.email == str(body.email).strip().casefold()))
    valid = passwords.verify(
        body.password.get_secret_value(), user.password_hash if user else dummy_hash
    )
    if not user or not valid:
        raise HTTPException(401, "Incorrect email or password")
    request.session.clear()
    request.session.update(user_id=user.id, csrf=secrets.token_urlsafe(32))
    return {"id": user.id, "email": user.email}


@api.post("/auth/logout", status_code=204)
def logout(request: Request):
    request.session.clear()


@router.get("/api/auth/me")
def me(user: CurrentUser):
    return {"id": user.id, "email": user.email}


@router.get("/api/destinations")
def list_destinations(user: CurrentUser, session: DbSession):
    return [
        destination_view(d)
        for d in session.scalars(
            select(Destination)
            .where(Destination.user_id == user.id)
            .order_by(Destination.id.desc())
        )
    ]


@api.post("/destinations", status_code=201)
def add_destination(body: DestinationCreate, user: CurrentUser, session: DbSession):
    destination = Destination(
        user_id=user.id,
        type=body.type,
        enabled=body.enabled,
        email_address=str(body.email_address) if body.email_address else None,
        webhook_url=body.webhook_url.get_secret_value() if body.webhook_url else None,
    )
    session.add(destination)
    session.commit()
    return destination_view(destination)


@api.patch("/destinations/{destination_id}")
def update_destination(
    destination_id: int, body: DestinationUpdate, user: CurrentUser, session: DbSession
):
    destination = session.scalar(
        select(Destination).where(Destination.id == destination_id, Destination.user_id == user.id)
    )
    if destination is None:
        raise HTTPException(404, "Destination not found")
    destination.enabled = body.enabled
    session.commit()
    return destination_view(destination)


@router.get("/api/deliveries")
def list_deliveries(user: CurrentUser, session: DbSession, limit: int = 50, offset: int = 0):
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, "Limit must be 1–100 and offset must be nonnegative")
    rows = session.execute(
        select(Delivery, Destination, Event.headline)
        .join(Destination, Delivery.destination_id == Destination.id)
        .join(Event, Delivery.event_id == Event.id)
        .where(Destination.user_id == user.id)
        .order_by(Delivery.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [
        {
            "id": delivery.id,
            "event_id": delivery.event_id,
            "headline": headline,
            "destination_id": destination.id,
            "destination_type": destination.type,
            "status": delivery.status,
            "attempts": delivery.attempts,
            # Provider error messages may contain request URLs or other credentials.
            "error": "Submission failed; inspect the sanitized server delivery log"
            if delivery.last_error
            else None,
            "created_at": delivery.created_at,
            "sent_at": delivery.sent_at,
        }
        for delivery, destination, headline in rows
    ]


@api.post("/destinations/{destination_id}/test")
def test_destination(destination_id: int, request: Request, user: CurrentUser, session: DbSession):
    destination = session.scalar(
        select(Destination).where(
            Destination.id == destination_id,
            Destination.user_id == user.id,
        )
    )
    if destination is None:
        raise HTTPException(404, "Destination not found")
    target = Target(destination.type, destination.email_address or destination.webhook_url or "")
    # Test sends work even when paused, but never create events or delivery jobs.
    session.rollback()
    try:
        request.app.state.sender.send(TEST_NOTIFICATION, target)
    except SendError as error:
        raise HTTPException(503 if error.retryable else 502, str(error)) from None
    except Exception:  # noqa: BLE001 - never expose credential-bearing adapter exceptions
        raise HTTPException(502, "Notification test failed") from None
    return {"status": "accepted", "message": "Test notification accepted by the channel"}


@router.get("/")
def home(request: Request):
    return RedirectResponse("/settings" if request.session.get("user_id") else "/login", 303)


@router.get("/login")
@router.get("/register")
def auth_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/settings", 303)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="auth.html",
        context={"register": request.url.path == "/register", "csrf": csrf_token(request)},
    )


@router.get("/settings")
def settings_page(request: Request, session: DbSession):
    user_id = request.session.get("user_id")
    user = session.get(User, user_id) if isinstance(user_id, int) else None
    if user is None:
        return RedirectResponse("/login", 303)
    return request.app.state.templates.TemplateResponse(
        request=request, name="settings.html", context={"user": user, "csrf": csrf_token(request)}
    )


router.include_router(api)
