from dataclasses import dataclass, field
from urllib.parse import urlsplit


def safe_link(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and not parsed.username
            and not any(char.isspace() or char in "<>|" for char in value)
            and len(value) <= 2000
        )
    except ValueError:
        return False


@dataclass(frozen=True)
class Notification:
    event_id: str
    headline: str
    summary: str = ""
    links: tuple[str, ...] = ()

    @property
    def source_links(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(link for link in self.links if safe_link(link)))[:3]


@dataclass(frozen=True)
class Target:
    type: str
    address: str = field(repr=False)


class SendError(Exception):
    """Only fixed, credential-free messages may be exposed or persisted."""

    def __init__(self, message: str, *, retryable: bool = False, retry_after: int = 0):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


TEST_NOTIFICATION = Notification(
    event_id="test",
    headline="News alerts: test notification",
    summary="Your notification destination is working. This is a test, not a news event.",
)
