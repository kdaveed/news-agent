import io
import json
import os
import smtplib
from datetime import UTC, datetime, timedelta
from email import policy
from email.parser import BytesParser
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from newsalert.db import (
    Base,
    CollectorRun,
    Delivery,
    Destination,
    Event,
    EventEvidence,
    RssItem,
    User,
)
from newsalert.db.session import make_engine
from newsalert.delivery.channels import ChannelSender, email_message, slack_payload
from newsalert.delivery.config import DeliverySettings
from newsalert.delivery.dispatcher import dispatch_once, enqueue, single_dispatcher, timestamp
from newsalert.delivery.messages import Notification, SendError, Target
from newsalert.settings import Settings
from newsalert.web.app import create_app

NOW = datetime(2026, 11, 6, 12, tzinfo=UTC)
WEBHOOK = "https://hooks.slack.com/services/T123/B456/supersecret"


class Sender:
    def __init__(self, failures=()):
        self.calls = []
        self.failures = list(failures)

    def send(self, notification, target):
        self.calls.append((notification, target))
        if self.failures:
            raise self.failures.pop(0)


@pytest.fixture
def engine(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'delivery.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def seed(engine, *, status="selected", enabled=True, destination_type="email"):
    with Session(engine) as session:
        user = User(email="reader@example.com", password_hash="fixture-only")
        run = CollectorRun(window_start=timestamp(NOW), window_end=timestamp(NOW), status="ok")
        session.add_all([user, run])
        session.flush()
        destination = Destination(
            user_id=user.id,
            type=destination_type,
            enabled=enabled,
            email_address="reader@example.com" if destination_type == "email" else None,
            webhook_url=WEBHOOK if destination_type == "slack" else None,
            created_at=timestamp(NOW - timedelta(days=1)),
        )
        event = Event(
            id="evt-one",
            headline="Important event",
            summary="Verified details",
            score=100,
            independent_outlets=100,
            band="auto",
            status=status,
            first_seen=timestamp(NOW),
            selected_at=timestamp(NOW) if status == "selected" else None,
            last_run_id=run.id,
        )
        session.add_all([destination, event])
        session.flush()
        rss = RssItem(
            feed="bbc", guid="article", url="https://example.com/article", title="Headline"
        )
        session.add(rss)
        session.flush()
        session.add(
            EventEvidence(
                event_id=event.id, source="rss", item_id=rss.id, match_method="url", confidence=1
            )
        )
        session.commit()
        return destination.id


def job(engine):
    with Session(engine) as session:
        result = session.scalar(select(Delivery))
        session.expunge(result)
        return result


def test_selected_event_sent_once_with_evidence_and_no_db_lock(engine):
    destination_id = seed(engine)

    class ConcurrentWriter(Sender):
        def send(self, notification, target):
            # A write on a second connection proves network submission holds no write transaction.
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "UPDATE destinations SET enabled=enabled WHERE id=?", (destination_id,)
                )
            super().send(notification, target)

    sender = ConcurrentWriter()
    result = dispatch_once(engine, sender, DeliverySettings(), now_fn=lambda: NOW)
    assert result["sent"] == 1
    assert sender.calls[0][0].source_links == ("https://example.com/article",)
    assert job(engine).status == "sent"
    assert job(engine).attempts == 1
    dispatch_once(engine, sender, DeliverySettings(), now_fn=lambda: NOW)
    assert len(sender.calls) == 1


def test_no_candidate_or_historical_backfill(engine):
    seed(engine, status="candidate")
    assert enqueue(engine, NOW) == 0
    with Session(engine) as session:
        event = session.get(Event, "evt-one")
        event.status = "selected"
        event.selected_at = timestamp(NOW - timedelta(days=2))
        session.commit()
    assert enqueue(engine, NOW) == 0


def test_paused_destinations_and_jobs_are_skipped(engine):
    destination_id = seed(engine, enabled=False)
    sender = Sender()
    dispatch_once(engine, sender, DeliverySettings(), now_fn=lambda: NOW)
    assert job(engine).status == "skipped"
    with Session(engine) as session:
        session.get(Destination, destination_id).enabled = True
        session.commit()
    dispatch_once(engine, sender, DeliverySettings(), now_fn=lambda: NOW)
    assert not sender.calls
    with Session(engine) as session:
        session.get(Destination, destination_id).enabled = False
        old_job = session.scalar(select(Delivery))
        old_job.status = "pending"
        session.commit()
    assert dispatch_once(engine, sender, DeliverySettings(), now_fn=lambda: NOW)["skipped"] == 1


def test_retry_after_due_time_and_attempt_limit(engine):
    seed(engine)
    sender = Sender(
        [
            SendError("Slack returned HTTP 429", retryable=True, retry_after=120),
            SendError("SMTP connection failed", retryable=True),
            SendError("SMTP connection failed", retryable=True),
        ]
    )
    settings = DeliverySettings()
    assert dispatch_once(engine, sender, settings, now_fn=lambda: NOW)["retry"] == 1
    assert job(engine).next_attempt_at == timestamp(NOW + timedelta(seconds=120))
    dispatch_once(engine, sender, settings, now_fn=lambda: NOW + timedelta(seconds=119))
    assert len(sender.calls) == 1
    assert (
        dispatch_once(engine, sender, settings, now_fn=lambda: NOW + timedelta(seconds=120))[
            "retry"
        ]
        == 1
    )
    assert job(engine).next_attempt_at == timestamp(NOW + timedelta(seconds=180))
    assert (
        dispatch_once(engine, sender, settings, now_fn=lambda: NOW + timedelta(seconds=180))[
            "failed"
        ]
        == 1
    )
    assert job(engine).attempts == 3
    dispatch_once(engine, sender, settings, now_fn=lambda: NOW + timedelta(days=1))
    assert len(sender.calls) == 3


def test_permanent_failure_and_secret_exception_redaction(engine):
    seed(engine)
    sender = Sender([SendError("Slack returned HTTP 403")])
    assert dispatch_once(engine, sender, DeliverySettings(), now_fn=lambda: NOW)["failed"] == 1
    assert job(engine).attempts == 1
    with Session(engine) as session:
        row = session.scalar(select(Delivery))
        row.status = "pending"
        row.attempts = 0
        session.commit()
    sender = Sender([RuntimeError(f"private URL {WEBHOOK}")])
    dispatch_once(engine, sender, DeliverySettings(), now_fn=lambda: NOW)
    assert "supersecret" not in job(engine).last_error


def test_interrupted_attempt_does_not_exceed_limit(engine):
    seed(engine)
    enqueue(engine, NOW)
    with Session(engine) as session:
        session.scalar(select(Delivery)).attempts = 3
        session.commit()
    sender = Sender()
    assert dispatch_once(engine, sender, DeliverySettings(), now_fn=lambda: NOW)["failed"] == 1
    assert not sender.calls


def test_single_worker_lock(engine):
    with (
        single_dispatcher(engine),
        pytest.raises(RuntimeError, match="already running"),
        single_dispatcher(engine),
    ):
        pass
    with single_dispatcher(engine):
        pass


def test_rendering_escapes_content_and_excludes_unsafe_links():
    notification = Notification(
        "evt",
        "<@channel> Alert\nBcc: attacker@example.com",
        "<script>bad()</script>",
        (
            "javascript:alert(1)",
            "https://example.com/<@all>",
            "https://example.com/article",
            "https://example.com/article",
        ),
    )
    message = email_message(notification, "reader@example.com", "alerts@example.com")
    parsed = BytesParser(policy=policy.default).parsebytes(message.as_bytes())
    assert parsed["Bcc"] is None
    assert "<script>" not in parsed.get_body(preferencelist=("html",)).get_content()
    assert "https://example.com/article" in parsed.get_body(preferencelist=("plain",)).get_content()
    payload = slack_payload(notification)
    assert "<@channel>" not in payload["text"]
    assert "&lt;@channel&gt;" in payload["text"]
    assert "javascript:" not in payload["text"]


class Reply(io.BytesIO):
    status = 200


def test_slack_posts_json_and_checks_acceptance(monkeypatch):
    sender = ChannelSender(DeliverySettings())
    requests = []

    def respond(request, timeout):
        requests.append(request)
        return Reply(b"ok")

    monkeypatch.setattr(sender.opener, "open", respond)
    sender.send(Notification("evt", "Headline"), Target("slack", WEBHOOK))
    assert requests[0].method == "POST"
    assert json.loads(requests[0].data)["text"].startswith("Headline")
    monkeypatch.setattr(sender.opener, "open", lambda *_args, **_kw: Reply(b"not_ok"))
    with pytest.raises(SendError, match="did not accept"):
        sender.send(Notification("evt", "Headline"), Target("slack", WEBHOOK))


@pytest.mark.parametrize("status,retryable", [(429, True), (503, True), (403, False), (302, False)])
def test_slack_classifies_errors_without_leaking_url(monkeypatch, status, retryable):
    sender = ChannelSender(DeliverySettings())

    def fail(*args, **kwargs):
        raise HTTPError(WEBHOOK, status, "private", {"Retry-After": "90"}, io.BytesIO(b"secret"))

    monkeypatch.setattr(sender.opener, "open", fail)
    with pytest.raises(SendError) as result:
        sender.send(Notification("evt", "Headline"), Target("slack", WEBHOOK))
    assert result.value.retryable is retryable
    assert WEBHOOK not in str(result.value)
    assert result.value.retry_after == (90 if status == 429 else 0)


def test_slack_connection_failure_and_invalid_stored_url(monkeypatch):
    sender = ChannelSender(DeliverySettings())

    def fail(*args, **kwargs):
        raise URLError(WEBHOOK)

    monkeypatch.setattr(sender.opener, "open", fail)
    with pytest.raises(SendError) as result:
        sender.send(Notification("evt", "Headline"), Target("slack", WEBHOOK))
    assert result.value.retryable
    assert WEBHOOK not in str(result.value)
    with pytest.raises(SendError, match="Invalid Slack"):
        sender.send(Notification("evt", "Headline"), Target("slack", "http://localhost/private"))


@pytest.mark.parametrize("code,retryable", [(451, True), (550, False)])
def test_smtp_errors_are_classified(monkeypatch, code, retryable):
    class SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def send_message(self, message):
            raise smtplib.SMTPRecipientsRefused({"reader@example.com": (code, b"private response")})

        def quit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(smtplib, "SMTP", SMTP)
    with pytest.raises(SendError) as result:
        ChannelSender(DeliverySettings()).send(
            Notification("evt", "Headline"), Target("email", "reader@example.com")
        )
    assert result.value.retryable is retryable
    assert "private response" not in str(result.value)


def test_smtp_success_is_not_lost_when_quit_fails(monkeypatch):
    messages = []

    class SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def send_message(self, message):
            messages.append(message)
            return {}

        def quit(self):
            raise smtplib.SMTPServerDisconnected("already accepted")

        def close(self):
            pass

    monkeypatch.setattr(smtplib, "SMTP", SMTP)
    ChannelSender(DeliverySettings()).send(
        Notification("evt", "Headline"), Target("email", "reader@example.com")
    )
    assert messages[0]["To"] == "reader@example.com"


def test_smtp_auth_requires_tls_and_config_errors_hide_passwords():
    with pytest.raises(ValidationError) as result:
        DeliverySettings(
            smtp_username="sender", smtp_password="smtp-private-password", smtp_security="none"
        )
    assert "requires starttls or tls" in str(result.value)
    assert "smtp-private-password" not in str(result.value)
    assert DeliverySettings(
        smtp_username="sender", smtp_password="private", smtp_security="starttls"
    )


def test_test_send_requires_owner_and_csrf_and_creates_no_jobs(engine):
    destination_id = seed(engine, enabled=False)
    sender = Sender()
    app = create_app(Settings(secret_key="test-only-secret-" * 4), engine, sender=sender)
    with TestClient(app) as client:
        token = client.get("/api/auth/csrf").json()["csrf_token"]
        # Register another user; that user must not be able to send to the seeded user's address.
        response = client.post(
            "/api/auth/register",
            json={"email": "other@example.com", "password": "a sufficiently long password"},
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 201
        token = client.get("/api/auth/csrf").json()["csrf_token"]
        assert (
            client.post(
                f"/api/destinations/{destination_id}/test", headers={"X-CSRF-Token": token}
            ).status_code
            == 404
        )
        created = client.post(
            "/api/destinations",
            json={"type": "email", "email_address": "other@example.com", "enabled": False},
            headers={"X-CSRF-Token": token},
        ).json()
        path = f"/api/destinations/{created['id']}/test"
        assert client.post(path).status_code == 403
        assert client.post(path, headers={"X-CSRF-Token": token}).json()["status"] == "accepted"
        assert sender.calls[0][0].event_id == "test"
        sender.failures.append(SendError("SMTP returned 451", retryable=True))
        assert client.post(path, headers={"X-CSRF-Token": token}).status_code == 503
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Delivery)) == 0
        assert session.scalar(select(func.count()).select_from(Event)) == 1


@pytest.mark.skipif(
    not os.environ.get("NEWSALERT_TEST_MAILPIT_URL"), reason="Optional local Mailpit integration"
)
def test_local_mailpit_captures_dispatcher_and_test_button_emails(engine):
    """Opt in with a local Mailpit URL and NEWSALERT_SMTP_PORT; never an external inbox."""
    from urllib.parse import urlsplit

    url = os.environ["NEWSALERT_TEST_MAILPIT_URL"]
    assert urlsplit(url).hostname == "127.0.0.1"
    settings = DeliverySettings()
    assert settings.smtp_host == "127.0.0.1"

    def inbox():
        with urlopen(f"{url}/api/v1/messages?limit=100", timeout=5) as response:
            return json.load(response)["messages"]

    before = {message["ID"] for message in inbox()}
    seed(engine)
    sender = ChannelSender(settings)
    assert dispatch_once(engine, sender, settings, now_fn=lambda: NOW)["sent"] == 1
    app = create_app(Settings(secret_key="mailpit-integration-secret-" * 3), engine, sender=sender)
    with TestClient(app) as client:
        token = client.get("/api/auth/csrf").json()["csrf_token"]
        assert (
            client.post(
                "/api/auth/register",
                json={
                    "email": "button@example.com",
                    "password": "a sufficiently long password",
                },
                headers={"X-CSRF-Token": token},
            ).status_code
            == 201
        )
        token = client.get("/api/auth/csrf").json()["csrf_token"]
        destination = client.post(
            "/api/destinations",
            json={
                "type": "email",
                "email_address": "button@example.com",
            },
            headers={"X-CSRF-Token": token},
        ).json()
        assert (
            client.post(
                f"/api/destinations/{destination['id']}/test",
                headers={
                    "X-CSRF-Token": token,
                },
            ).status_code
            == 200
        )
    messages = [message for message in inbox() if message["ID"] not in before]
    assert {message["Subject"] for message in messages} == {
        "Important event",
        "News alerts: test notification",
    }
    assert len(messages) == 2
    sent = next(message for message in messages if message["Subject"] == "Important event")
    with urlopen(f"{url}/api/v1/message/{sent['ID']}", timeout=5) as response:
        captured = json.load(response)
    assert "Verified details" in captured["Text"]
    assert "https://example.com/article" in captured["HTML"]
    assert job(engine).status == "sent"
