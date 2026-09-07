from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://saff:saff@localhost:5432/saff_tasks"
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET: str = "dev-secret"
    ACCESS_TTL_MIN: int = 15
    REFRESH_TTL_DAYS: int = 14
    SERVICE_TOKEN: str = "dev-service-token"
    FILE_SIGNING_SECRET: str = "dev-file-secret"
    UPLOAD_DIR: str = "./uploads"
    PUBLIC_API_URL: str = "http://localhost:8000"
    ADMIN_LOGIN: str = "admin"
    ADMIN_PASSWORD: str = "admin12345"
    TZ_NAME: str = "Asia/Tashkent"
    BOT_TOKEN: str = ""
    WEBHOOK_SECRET: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_STT_MODEL: str = "gpt-4o-transcribe"
    OPENAI_LLM_MODEL: str = "gpt-4o-mini"
    MIN_PASSWORD_LEN: int = 4
    MAX_IMAGE_MB: int = 20
    MAX_DOC_MB: int = 50
    SCHEDULER_ENABLED: bool = True


settings = Settings()
