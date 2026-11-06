from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEWSALERT_", env_file=".env", extra="ignore")

    secret_key: SecretStr = Field(min_length=32)
    database_url: str = "sqlite:///./data/newsalert.db"
    cookie_secure: bool = False
    session_seconds: int = 12 * 60 * 60
    # Comma-separated account emails allowed to open /admin. Empty disables the admin view.
    admin_emails: str = ""

    def admin_email_set(self) -> frozenset[str]:
        return frozenset(
            email.strip().casefold() for email in self.admin_emails.split(",") if email.strip()
        )

    @field_validator("secret_key")
    @classmethod
    def reject_example_secret(cls, value: SecretStr) -> SecretStr:
        if value.get_secret_value().startswith("replace-with-"):
            raise ValueError("Generate a private NEWSALERT_SECRET_KEY before starting the app")
        return value
