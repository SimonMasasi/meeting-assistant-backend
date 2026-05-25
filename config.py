from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_SECONDS: int = 300
    JWT_REFRESH_TOKEN_EXPIRE_SECONDS: int = 60 * 60 * 24 * 7

    model_config = SettingsConfigDict(env_file=".env")


SETTINGS = Settings()