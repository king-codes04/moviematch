
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    REDIS_URL: str
    TMDB_BEARER_TOKEN: str
    CORS_ORIGINS: list[str] = Field(default_factory=list)

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
