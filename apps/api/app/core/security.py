import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import Settings

password_hasher = PasswordHasher()


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenValidationError(Exception):
    """Raised when a token cannot be decoded or does not match the expected type."""


@dataclass(frozen=True)
class TokenClaims:
    subject: UUID
    token_type: TokenType
    expires_at: datetime
    token_id: str | None


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_token(
    *,
    subject: UUID,
    token_type: TokenType,
    settings: Settings,
    expires_delta: timedelta,
    token_id: str | None = None,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(subject),
        "typ": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
    }
    if token_id is not None:
        payload["jti"] = token_id
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(*, subject: UUID, settings: Settings) -> str:
    return create_token(
        subject=subject,
        token_type=TokenType.ACCESS,
        settings=settings,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(*, subject: UUID, settings: Settings) -> str:
    return create_token(
        subject=subject,
        token_type=TokenType.REFRESH,
        settings=settings,
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
        token_id=uuid4().hex,
    )


def decode_token(
    token: str,
    *,
    expected_type: TokenType,
    settings: Settings,
) -> UUID:
    return decode_token_claims(token, expected_type=expected_type, settings=settings).subject


def decode_token_claims(
    token: str,
    *,
    expected_type: TokenType,
    settings: Settings,
) -> TokenClaims:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("typ") != expected_type.value:
            raise TokenValidationError
        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise TokenValidationError
        expires_at = datetime.fromtimestamp(float(payload["exp"]), tz=UTC)
        token_id = payload.get("jti")
        if token_id is not None and not isinstance(token_id, str):
            raise TokenValidationError
        return TokenClaims(
            subject=UUID(subject),
            token_type=expected_type,
            expires_at=expires_at,
            token_id=token_id,
        )
    except (ValueError, jwt.PyJWTError) as exc:
        raise TokenValidationError from exc


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_api_key_secret() -> str:
    return f"ocr_sk_{secrets.token_urlsafe(32)}"


def create_webhook_secret() -> str:
    return f"ocr_wh_{secrets.token_urlsafe(32)}"


def api_key_prefix(secret: str) -> str:
    return secret[:16]


def hash_api_key(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()
