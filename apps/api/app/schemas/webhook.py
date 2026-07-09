from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IncomingWebhookMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(default="", max_length=8000)
    external_id: str | None = Field(default=None, max_length=160)
    source: str | None = Field(default=None, max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_content(self) -> "IncomingWebhookMessageRequest":
        if not self.content.strip():
            raise ValueError("Webhook message requires content.")
        return self
