from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from newsalert.db.base import Base, utc_now


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, default=utc_now)


class Destination(Base):
    __tablename__ = "destinations"
    __table_args__ = (
        CheckConstraint("type IN ('email', 'slack')", name="ck_destination_type"),
        CheckConstraint("enabled IN (0, 1)", name="ck_destination_enabled"),
        CheckConstraint(
            "(type = 'email' AND email_address IS NOT NULL AND webhook_url IS NULL) OR "
            "(type = 'slack' AND webhook_url IS NOT NULL AND email_address IS NULL)",
            name="ck_destination_address",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(10))
    email_address: Mapped[str | None] = mapped_column(Text)
    webhook_url: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(default=True, server_default=text("1"))
    created_at: Mapped[str] = mapped_column(Text, default=utc_now)


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint("event_id", "destination_id", name="uq_delivery_event_destination"),
        CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'skipped')", name="ck_delivery_status"
        ),
        CheckConstraint("attempts >= 0", name="ck_delivery_attempts"),
        Index("ix_deliveries_due", "status", "next_attempt_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Collector registers events on this same Base; no duplicate event model here.
    event_id: Mapped[str] = mapped_column(String(255), ForeignKey("events.id"))
    destination_id: Mapped[int] = mapped_column(ForeignKey("destinations.id"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    next_attempt_at: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, default=utc_now)
    sent_at: Mapped[str | None] = mapped_column(Text)
