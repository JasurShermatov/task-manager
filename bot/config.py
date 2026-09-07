import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    BOT_TOKEN: str
    BOT_MODE: str = "polling"           # polling | webhook
    WEBHOOK_URL: str = ""
    WEBHOOK_SECRET: str = "secret"
    WEBHOOK_PORT: int = 8080
    API_BASE_URL: str = "http://localhost:8000"
    SERVICE_TOKEN: str = "dev-service-token"
    REDIS_URL: str = "redis://localhost:6379/1"
    TZ_NAME: str = "Asia/Tashkent"
    WEB_URL: str = os.environ.get("WEB_URL", "")
    OUTBOX_INTERVAL: float = 3.0


settings = Settings()
