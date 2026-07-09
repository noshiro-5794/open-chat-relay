import pytest
from app.core.config import DEFAULT_GATEWAY_INTERNAL_TOKEN, DEFAULT_JWT_SECRET_KEY, Settings
from app.main import create_app
from starlette.testclient import TestClient


def production_settings(**overrides) -> Settings:
    values = {
        "environment": "production",
        "jwt_secret_key": "production-secret-at-least-32-bytes",
        "cors_origins": ["https://app.example.com"],
    }
    values.update(overrides)
    return Settings(**values)


def test_production_rejects_default_jwt_secret() -> None:
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        create_app(production_settings(jwt_secret_key=DEFAULT_JWT_SECRET_KEY))


def test_production_rejects_placeholder_jwt_secret() -> None:
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        create_app(production_settings(jwt_secret_key="replace-with-generated-secret"))  # noqa: S106


def test_production_rejects_debug_mode() -> None:
    with pytest.raises(RuntimeError, match="DEBUG"):
        create_app(production_settings(debug=True))


def test_production_rejects_default_gateway_token_when_webtransport_is_enabled() -> None:
    with pytest.raises(RuntimeError, match="GATEWAY_INTERNAL_TOKEN"):
        create_app(
            production_settings(
                webtransport_enabled=True,
                webtransport_url="https://chat.example.com:8081/v1/wt",
                gateway_internal_token=DEFAULT_GATEWAY_INTERNAL_TOKEN,
            )
        )


def test_production_rejects_placeholder_gateway_token_when_webtransport_is_enabled() -> None:
    with pytest.raises(RuntimeError, match="GATEWAY_INTERNAL_TOKEN"):
        create_app(
            production_settings(
                webtransport_enabled=True,
                webtransport_url="https://chat.example.com:8081/v1/wt",
                gateway_internal_token="replace-with-generated-gateway-token",  # noqa: S106
            )
        )


def test_production_disables_docs_by_default() -> None:
    app = create_app(production_settings())

    with TestClient(app) as client:
        docs_response = client.get("/docs")
        openapi_response = client.get("/v1/openapi.json")

    assert docs_response.status_code == 404
    assert openapi_response.status_code == 404


def test_request_body_size_limit_returns_413() -> None:
    app = create_app(
        Settings(
            environment="test",
            jwt_secret_key="test-secret-at-least-32-bytes-long",  # noqa: S106
            max_request_body_bytes=10,
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/auth/register",
            json={
                "email": "large@example.com",
                "password": "correct horse battery staple",
                "display_name": "Large Body",
            },
        )

    assert response.status_code == 413
    assert response.json()["detail"] == "Request body is too large."
