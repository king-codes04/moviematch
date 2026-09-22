from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    REDIS_URL: str

    model_config = SettingsConfigDict(env_file=".env")