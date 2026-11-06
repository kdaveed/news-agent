import json
import re
import smtplib
import ssl
import threading
import time
from contextlib import suppress
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from html import escape
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from email_validator import EmailNotValidError, validate_email

from newsalert.delivery.config import DeliverySettings
from newsalert.delivery.messages import Notification, SendError, Target


def valid_slack_webhook(value: str) -> bool:
    try:
        url = urlsplit(value)
        return bool(
            url.scheme == "https"
            and url.netloc == "hooks.slack.com"
            and not url.query
            and not url.fragment
            and re.fullmatch(r"/services/[A-Za-z0-9]+/[A-Za-z0-9]+/[A-Za-z0-9]+", url.path)
        )
    except ValueError:
        return False


def email_message(notification: Notification, address: str, sender: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = address
    message["Subject"] = " ".join(notification.headline.splitlines())[:200]
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[-1])
    text = f"{notification.headline}\n\n{notification.summary}"
    if notification.source_links:
        text += "\n\nSources:\n" + "\n".join(notification.source_links)
    message.set_content(text)
    links = "".join(
        f'<li><a href="{escape(url, quote=True)}">Source {index}</a></li>'
        for index, url in enumerate(notification.source_links, 1)
    )
    message.add_alternative(
        f"<h1>{escape(notification.headline)}</h1>"
        f"<p>{escape(notification.summary).replace(chr(10), '<br>')}</p>"
        + (f"<h2>Sources</h2><ul>{links}</ul>" if links else ""),
        subtype="html",
    )
    return message


def slack_payload(notification: Notification) -> dict:
    def plain(value):
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Escape source-provided text, so a headline cannot inject @channel or links.
    text = plain(notification.headline[:250]) + "\n\n" + plain(notification.summary[:2500])
    if notification.source_links:
        text += "\n\n" + " · ".join(
            f"<{url}|Source {index}>" for index, url in enumerate(notification.source_links, 1)
        )
    return {"text": text, "unfurl_links": False, "unfurl_media": False}


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class ChannelSender:
    def __init__(self, settings: DeliverySettings):
        self.settings = settings
        self._slack_lock = threading.Lock()
        self._last_slack_attempt = 0.0
        # urllib does not log credential-bearing request URLs. Do not follow redirects
        # or send webhook credentials through ambient proxy configuration.
        self.opener = build_opener(ProxyHandler({}), NoRedirects())

    def send(self, notification: Notification, target: Target) -> None:
        if target.type == "email":
            self._email(notification, target.address)
        elif target.type == "slack":
            self._slack(notification, target.address)
        else:
            raise SendError("Unsupported notification channel")

    def _slack(self, notification: Notification, webhook: str) -> None:
        if not valid_slack_webhook(webhook):
            raise SendError("Invalid Slack incoming webhook URL")
        # Conservatively pace this sender at Slack's one-message-per-second limit.
        with self._slack_lock:
            time.sleep(max(0, 1 - (time.monotonic() - self._last_slack_attempt)))
            self._last_slack_attempt = time.monotonic()
        request = Request(
            webhook,
            data=json.dumps(slack_payload(notification)).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=self.settings.delivery_timeout) as response:
                if response.status != 200 or response.read(1024).strip() != b"ok":
                    raise SendError("Slack did not accept the notification")
        except HTTPError as error:
            code = error.code
            retry_after = 0
            if code == 429:
                try:
                    retry_after = max(1, int(error.headers.get("Retry-After", "60")))
                except (ValueError, TypeError):
                    retry_after = 60
            error.close()
            raise SendError(
                f"Slack returned HTTP {code}",
                retryable=code == 429 or 500 <= code < 600,
                retry_after=retry_after,
            ) from None
        except (URLError, OSError, TimeoutError):
            raise SendError("Slack connection failed or timed out", retryable=True) from None

    def _email(self, notification: Notification, address: str) -> None:
        try:
            validate_email(address, check_deliverability=False)
        except EmailNotValidError:
            raise SendError("Invalid notification email address") from None
        smtp = None
        try:
            settings = self.settings
            if settings.smtp_security == "tls":
                smtp = smtplib.SMTP_SSL(
                    settings.smtp_host,
                    settings.smtp_port,
                    timeout=settings.delivery_timeout,
                    context=ssl.create_default_context(),
                )
            else:
                smtp = smtplib.SMTP(
                    settings.smtp_host,
                    settings.smtp_port,
                    timeout=settings.delivery_timeout,
                )
                if settings.smtp_security == "starttls":
                    smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            refused = smtp.send_message(
                email_message(notification, address, str(settings.smtp_from))
            )
            if refused:
                code = next(iter(refused.values()))[0]
                raise SendError("SMTP rejected the recipient", retryable=400 <= code < 500)
        except smtplib.SMTPRecipientsRefused as error:
            code = next(iter(error.recipients.values()))[0]
            raise SendError("SMTP rejected the recipient", retryable=400 <= code < 500) from None
        except smtplib.SMTPResponseException as error:
            raise SendError(
                f"SMTP returned {error.smtp_code}",
                retryable=400 <= error.smtp_code < 500,
            ) from None
        except smtplib.SMTPNotSupportedError:
            raise SendError(
                "SMTP server does not support the configured authentication or TLS"
            ) from None
        except (smtplib.SMTPServerDisconnected, OSError, TimeoutError):
            raise SendError("SMTP connection failed or timed out", retryable=True) from None
        except smtplib.SMTPException:
            raise SendError("SMTP submission failed") from None
        finally:
            if smtp is not None:
                # A failed QUIT after successful DATA must not turn acceptance into failure.
                with suppress(smtplib.SMTPException, OSError):
                    smtp.quit()
                with suppress(smtplib.SMTPException, OSError):
                    smtp.close()
