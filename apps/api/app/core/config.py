from functools import lru_cache
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_JWT_SECRET_KEY = "change-this-local-secret-at-least-32-bytes"  # noqa: S105
DEFAULT_GATEWAY_INTERNAL_TOKEN = "change-this-local-gateway-token"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="OPEN_CHAT_RELAY_",
        extra="ignore",
    )

    project_name: str = "OpenChatRelay"
    version: str = "0.1.0"
    node_id: str = Field(default_factory=lambda: uuid4().hex)
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False
    log_level: str = "INFO"
    docs_enabled: bool | None = None
    max_request_body_bytes: int = 1_048_576
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    rate_limit_general_requests: int = 600
    rate_limit_auth_requests: int = 30
    rate_limit_webhook_requests: int = 120
    rate_limit_app_api_requests: int = 300
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    rate_limit_redis_key_prefix: str = "open_chat_relay:rate_limit"
    rate_limit_fail_open: bool = True
    outbox_publisher_enabled: bool = True
    outbox_publisher_poll_interval_seconds: float = 1.0
    outbox_publisher_batch_size: int = 100
    outbox_publisher_max_attempts: int = 5
    outbox_redis_channel_prefix: str = "open_chat_relay"
    realtime_redis_fanout_enabled: bool = True
    realtime_redis_signals_enabled: bool = True
    realtime_redis_reconnect_seconds: float = 1.0
    presence_backend: Literal["memory", "redis"] = "memory"
    presence_redis_key_prefix: str = "open_chat_relay:presence"
    presence_ttl_seconds: int = 120
    typing_backend: Literal["memory", "redis"] = "memory"
    typing_redis_key_prefix: str = "open_chat_relay:typing"
    typing_ttl_seconds: int = 10

    api_v1_prefix: str = "/v1"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    database_url: str = (
        "postgresql+asyncpg://openchatrelay:openchatrelay@localhost:5432/openchatrelay"
    )
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = DEFAULT_JWT_SECRET_KEY
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    first_user_system_admin: bool = True

    webtransport_enabled: bool = False
    webtransport_url: str | None = None
    webtransport_health_url: str | None = None
    webtransport_health_timeout_seconds: float = 0.5
    gateway_internal_token: str | None = None

    sse_poll_interval_seconds: float = 1.0

    storage_backend: Literal["s3", "none"] = "s3"
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_public_endpoint_url: str | None = "http://localhost:9000"
    s3_region_name: str = "us-east-1"
    s3_access_key_id: str = "openchatrelay"
    s3_secret_access_key: str = "openchatrelay-secret"  # noqa: S105
    s3_bucket: str = "open-chat-relay"
    s3_presigned_upload_expire_seconds: int = 900
    s3_presigned_download_expire_seconds: int = 900
    verify_attachment_uploads: bool | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    def effective_docs_enabled(self) -> bool:
        if self.docs_enabled is not None:
            return self.docs_enabled
        return self.environment != "production"

    def effective_verify_attachment_uploads(self) -> bool:
        if self.verify_attachment_uploads is not None:
            return self.verify_attachment_uploads
        return self.storage_backend == "s3" and self.environment != "test"

    def effective_realtime_redis_fanout_enabled(self) -> bool:
        return self.realtime_redis_fanout_enabled and self.environment != "test"

    def effective_realtime_redis_signals_enabled(self) -> bool:
        return self.realtime_redis_signals_enabled and self.environment != "test"

    def effective_rate_limit_backend(self) -> Literal["memory", "redis"]:
        if self.environment == "test":
            return "memory"
        return self.rate_limit_backend

    def effective_presence_backend(self) -> Literal["memory", "redis"]:
        if self.environment == "test":
            return "memory"
        return self.presence_backend

    def effective_typing_backend(self) -> Literal["memory", "redis"]:
        if self.environment == "test":
            return "memory"
        return self.typing_backend


def validate_startup_settings(settings: Settings) -> None:
    if settings.environment != "production":
        return

    errors: list[str] = []
    if settings.debug:
        errors.append("OPEN_CHAT_RELAY_DEBUG must be false in production.")
    if settings.jwt_secret_key == DEFAULT_JWT_SECRET_KEY or is_placeholder_secret(
        settings.jwt_secret_key
    ):
        errors.append("OPEN_CHAT_RELAY_JWT_SECRET_KEY must be changed in production.")
    if "*" in settings.cors_origins:
        errors.append("OPEN_CHAT_RELAY_CORS_ORIGINS cannot contain '*' in production.")
    if settings.webtransport_enabled and settings.webtransport_url is None:
        errors.append("OPEN_CHAT_RELAY_WEBTRANSPORT_URL is required when WebTransport is enabled.")
    if settings.webtransport_enabled and settings.gateway_internal_token is None:
        errors.append(
            "OPEN_CHAT_RELAY_GATEWAY_INTERNAL_TOKEN is required when WebTransport is enabled."
        )
    gateway_token_is_unsafe = settings.gateway_internal_token == DEFAULT_GATEWAY_INTERNAL_TOKEN or (
        settings.gateway_internal_token is not None
        and is_placeholder_secret(settings.gateway_internal_token)
    )
    if settings.webtransport_enabled and gateway_token_is_unsafe:
        errors.append("OPEN_CHAT_RELAY_GATEWAY_INTERNAL_TOKEN must be changed in production.")

    if errors:
        raise RuntimeError("Invalid production settings: " + " ".join(errors))


def is_placeholder_secret(value: str) -> bool:
    return value.startswith("replace-with-")


@lru_cache
def get_settings() -> Settings:
    return Settings()
