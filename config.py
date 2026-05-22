from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str = None

    model_config = SettingsConfigDict(env_file=".env")


SETTINGS = Settings()