from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, model_validator

from newsalert.delivery.channels import valid_slack_webhook


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=128)


class Register(Login):
    password: SecretStr = Field(min_length=12, max_length=128)


class DestinationCreate(Input):
    type: Literal["email", "slack"]
    email_address: EmailStr | None = None
    webhook_url: SecretStr | None = Field(default=None, max_length=2048)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_address(self):
        if self.type == "email":
            if self.email_address is None or self.webhook_url is not None:
                raise ValueError("Email destinations require only an email address")
        else:
            if self.webhook_url is None or self.email_address is not None:
                raise ValueError("Slack destinations require only a webhook URL")
            value = self.webhook_url.get_secret_value()
            if not valid_slack_webhook(value):
                raise ValueError(
                    "Use a Slack incoming webhook URL at https://hooks.slack.com/services/…"
                )
        return self


class DestinationUpdate(Input):
    enabled: bool
