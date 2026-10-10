
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    REDIS_URL: str
    TMDB_BEARER_TOKEN: str

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
