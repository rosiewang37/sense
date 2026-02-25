from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    app_name: str = "Sense"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://sense:sense@localhost:5432/sense"
    database_url_sync: str = "postgresql://sense:sense@localhost:5432/sense"

    # Auth
    jwt_secret_key: str = "dev-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    # Backboard API
    backboard_api_url: str = "https://app.backboard.io/api"
    backboard_api_key: str = ""

    # Integrations
    slack_client_id: str = ""
    slack_client_secret: str = ""
    slack_signing_secret: str = ""
    github_app_id: str = ""
    github_private_key: str = ""
    github_webhook_secret: str = ""

    # Encryption
    encryption_key: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
