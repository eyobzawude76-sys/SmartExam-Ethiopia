import pytest
from pydantic import ValidationError

from app.core.config import Settings


SECRET = "ci-test-secret-that-is-at-least-32-characters-long"


def test_environment_must_be_explicitly_configured():
    with pytest.raises(ValidationError, match="app_env"):
        Settings(
            _env_file=None,
            jwt_secret_key=SECRET,
        )


def test_production_requires_https_frontend_origin():
    with pytest.raises(ValidationError, match="must use HTTPS"):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret_key=SECRET,
            frontend_origin="http://example.com",
        )


def test_production_rejects_example_jwt_secret():
    with pytest.raises(ValidationError, match="unique production JWT_SECRET_KEY"):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret_key="replace-with-a-long-random-secret-at-least-32-characters",
            frontend_origin="https://exam.example",
        )


def test_production_accepts_https_frontend_origin():
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret_key=SECRET,
        frontend_origin="https://exam.example",
    )
    assert settings.frontend_origin == "https://exam.example"


def test_unknown_environment_name_is_rejected():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="prod",
            jwt_secret_key=SECRET,
            frontend_origin="https://exam.example",
        )


def test_unsupported_jwt_algorithm_is_rejected():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="test",
            jwt_secret_key=SECRET,
            jwt_algorithm="none",
        )
