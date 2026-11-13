from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "ResQNet API"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    secret_key: str = "development-only-change-me"
    access_token_expire_minutes: int = 60
    database_url: str = "sqlite:///./resqnet.db"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    seed_demo_data: bool = True
    gemini_api_key: str = ""
    whisper_api_key: str = ""
    upload_dir: str = "uploads"
    rate_limit_enabled: bool = False
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
