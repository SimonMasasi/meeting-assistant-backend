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
    
    USE_RUSTF_UPLOADS: bool = False
    RUSTF_URL: str = "http://localhost:9000"
    RUSTF_ACCESS_KEY: str = None
    RUSTF_SECRET_KEY: str = None
    RUSTF_BUCKET_NAME: str = None
    RUSTF_REGION: str = None

    model_config = SettingsConfigDict(env_file=".env")


SETTINGS = Settings()