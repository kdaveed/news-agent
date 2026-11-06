import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from newsalert.db import Base, CollectorRun, Delivery, Event, User
from newsalert.db.base import utc_now
from newsalert.settings import Settings
from newsalert.web.app import create_app
from newsalert.web.security import passwords

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

    # Test-only, disposable schema. Production app never creates tables.
    Base.metadata.create_all(engine)
    yield create_app(Settings(secret_key="test-only-secret-" * 4), engine)
    engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def mutate(client, method, path, body=None):
    token = client.get("/api/auth/csrf").json()["csrf_token"]
    return client.request(method, path, json=body, headers={"X-CSRF-Token": token})


def register(client, email="reader@example.com"):
    return mutate(client, "POST", "/api/auth/register", {"email": email, "password": PASSWORD})


def test_register_login_logout_and_password_storage(client, app):
    assert client.get("/settings", follow_redirects=False).headers["location"] == "/login"
    assert register(client, "Reader@EXAMPLE.com").status_code == 201
    assert client.get("/api/auth/me").json()["email"] == "reader@example.com"
    assert client.get("/settings").status_code == 200
    with Session(app.state.engine) as session:
        user = session.scalar(select(User))
        assert user.password_hash != PASSWORD
        assert passwords.verify(PASSWORD, user.password_hash)
    assert mutate(client, "POST", "/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    bad = mutate(
        client, "POST", "/api/auth/login", {"email": "reader@example.com", "password": "wrong"}
    )
    assert bad.status_code == 401
    missing = mutate(
        client, "POST", "/api/auth/login", {"email": "missing@example.com", "password": "wrong"}
    )
    assert bad.json() == missing.json()
    good = mutate(
        client, "POST", "/api/auth/login", {"email": "READER@example.com", "password": PASSWORD}
    )
    assert good.status_code == 200
    assert "httponly" in good.headers["set-cookie"].lower()
    assert "samesite=lax" in good.headers["set-cookie"].lower()


def test_duplicate_accounts_and_invalid_inputs_do_not_echo_secrets(client):
    assert register(client).status_code == 201
    assert register(client, "READER@example.com").status_code == 409
    secret = "shortsecret"
    response = mutate(
        client, "POST", "/api/auth/register", {"email": "other@example.com", "password": secret}
    )
    assert response.status_code == 422
    assert secret not in response.text
    response = mutate(
        client,
        "POST",
        "/api/destinations",
        {
            "type": "slack",
            "webhook_url": "http://127.0.0.1/private-webhook-secret",
        },
    )
    assert response.status_code == 422
    assert "private-webhook-secret" not in response.text


def test_csrf_required_and_rotated_on_login(client):
    old_token = client.get("/api/auth/csrf").json()["csrf_token"]
    assert (
        client.post(
            "/api/auth/register",
            json={
                "email": "reader@example.com",
                "password": PASSWORD,
            },
        ).status_code
        == 403
    )
    assert register(client).status_code == 201
    assert (
        client.post(
            "/api/destinations",
            json={"type": "email", "email_address": "a@example.com"},
            headers={"X-CSRF-Token": old_token},
        ).status_code
        == 403
    )
    assert client.get("/api/auth/csrf").json()["csrf_token"] != old_token


def test_owner_isolation_masking_and_disable(client, app):
    assert register(client).status_code == 201
    email = mutate(
        client,
        "POST",
        "/api/destinations",
        {
            "type": "email",
            "email_address": "alerts@example.com",
        },
    )
    slack = mutate(client, "POST", "/api/destinations", {"type": "slack", "webhook_url": WEBHOOK})
    assert email.status_code == slack.status_code == 201
    assert WEBHOOK not in slack.text
    assert "secret123" not in client.get("/api/destinations").text
    assert len(client.get("/api/destinations").json()) == 2
    destination_id = slack.json()["id"]
    assert (
        mutate(client, "PATCH", f"/api/destinations/{destination_id}", {"enabled": False}).json()[
            "enabled"
        ]
        is False
    )

    with TestClient(app) as other:
        assert register(other, "other@example.com").status_code == 201
        assert other.get("/api/destinations").json() == []
        assert (
            mutate(
                other, "PATCH", f"/api/destinations/{destination_id}", {"enabled": True}
            ).status_code
            == 404
        )
        assert (
            mutate(
                other,
                "POST",
                "/api/destinations",
                {
                    "type": "email",
                    "email_address": "other@example.com",
                    "user_id": 1,
                },
            ).status_code
            == 422
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://hooks.slack.com.evil.example/services/T/B/secret",
        "https://hooks.slack.com@evil.example/services/T/B/secret",
        "https://hooks.slack.com/services/T/B/secret?leak=yes",
        "http://hooks.slack.com/services/T/B/secret",
        "https://example.com/services/T/B/secret",
    ],
)
def test_only_slack_incoming_webhooks_allowed(client, url):
    register(client)
    assert (
        mutate(
            client, "POST", "/api/destinations", {"type": "slack", "webhook_url": url}
        ).status_code
        == 422
    )


def test_delivery_history_is_scoped_and_hides_provider_errors(client, app):
    register(client)
    destination = mutate(
        client,
        "POST",
        "/api/destinations",
        {
            "type": "email",
            "email_address": "reader@example.com",
        },
    ).json()
    with Session(app.state.engine) as session:
        run = CollectorRun(window_start=utc_now(), window_end=utc_now(), status="ok")
        session.add(run)
        session.flush()
        session.add(
            Event(
                id="stable-story-id",
                headline="An important development",
                score=100,
                independent_outlets=100,
                band="auto",
                status="selected",
                first_seen=utc_now(),
                selected_at=utc_now(),
                last_run_id=run.id,
            )
        )
        session.flush()
        session.add(
            Delivery(
                event_id="stable-story-id",
                destination_id=destination["id"],
                status="failed",
                attempts=3,
                last_error=f"Failed requesting {WEBHOOK}",
            )
        )
        session.commit()
    history = client.get("/api/deliveries")
    assert len(history.json()) == 1
    assert history.json()[0]["status"] == "failed"
    assert history.json()[0]["headline"] == "An important development"
    assert WEBHOOK not in history.text
    assert client.get("/api/deliveries?limit=101").status_code == 422
    with TestClient(app) as other:
        register(other, "other@example.com")
        assert other.get("/api/deliveries").json() == []
    with Session(app.state.engine) as session:
        session.add(Delivery(event_id="stable-story-id", destination_id=destination["id"]))
        with pytest.raises(IntegrityError):
            session.commit()


def test_html_flow_has_forms_and_csrf(client):
    for path in ["/login", "/register"]:
        response = client.get(path)
        assert response.status_code == 200
        assert re.search(r'<meta name="csrf-token" content="[^"]+">', response.text)
        assert 'id="auth-form"' in response.text
        assert response.headers["cache-control"] == "no-store"
    register(client)
    html = client.get("/settings")
    assert 'id="destination-form"' in html.text
    assert 'id="delivery-list"' in html.text
    assert client.get("/static/app.js").status_code == 200


def test_app_factory_does_not_create_or_migrate_tables(tmp_path):
    path = tmp_path / "uninitialized.db"
    create_app(Settings(secret_key="test-only-secret-" * 4, database_url=f"sqlite:///{path}"))
    assert not path.exists()
