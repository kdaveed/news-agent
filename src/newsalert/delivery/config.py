from typing import Literal

from pydantic import EmailStr, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DeliverySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NEWSALERT_",
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: str = "sqlite:///./data/newsalert.db"
    smtp_host: str = "127.0.0.1"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_from: EmailStr = "alerts@example.com"
    smtp_security: Literal["none", "starttls", "tls"] = "none"
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    delivery_timeout: float = Field(default=10, gt=0, le=60)
    delivery_max_attempts: int = Field(default=3, ge=1, le=10)
    delivery_retry_seconds: int = Field(default=30, ge=1, le=3600)
    dispatcher_poll_seconds: float = Field(default=5, ge=1, le=300)
    dispatcher_batch_size: int = Field(default=100, ge=1, le=1000)

    @model_validator(mode="after")
    def smtp_credentials(self):
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise ValueError("Configure both SMTP username and password")
        if self.smtp_username and self.smtp_security == "none":
            raise ValueError("SMTP authentication requires starttls or tls")
        return self
