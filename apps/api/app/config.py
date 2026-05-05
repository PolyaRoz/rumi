from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://rumi:changeme@localhost:5432/rumi_db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret: str = "change-me-in-production-use-64-char-random-string"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 30

    # S3 / Yandex Object Storage
    s3_endpoint_url: str = "https://storage.yandexcloud.net"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket_name: str = "rumi-files"
    s3_region: str = "ru-central1"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "rumi_products"

    # YooKassa
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_webhook_secret: str = ""

    # Email
    smtp_host: str = "smtp.yandex.ru"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""

    # Anthropic (Claude Vision)
    anthropic_api_key: str = ""

    # App
    frontend_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
