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
    JWT_PASSWORD_RESET_TOKEN_EXPIRE_SECONDS: int = 60 * 60 * 24
    
    USE_RUSTF_UPLOADS: bool = False
    RUSTF_URL: str = "http://localhost:9000"
    RUSTF_ACCESS_KEY: str = None
    RUSTF_SECRET_KEY: str = None
    RUSTF_BUCKET_NAME: str = None
    RUSTF_REGION: str = None

    PYNOTE_MODEL: str = "pyannote/speaker-diarization-community-1"
    HUGGINGFACE_TOKEN: str = None

    # Cloud inference (Phase 3).
    # Summarization: any OpenAI-compatible chat endpoint. Point these at OpenAI
    # (https://api.openai.com/v1) or a local server you run (e.g. Ollama at
    # http://localhost:11434/v1, no key needed).
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_API_KEY: str | None = None
    LLM_MODEL: str = "gpt-4o-mini"
    # Whisper model size for transcription (tiny|base|small|medium|large-v3).
    WHISPER_MODEL: str = "base"

    model_config = SettingsConfigDict(env_file=".env")


SETTINGS = Settings()