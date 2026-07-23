from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    DEBUG: bool = True
    APP_NAME: str = "Meeting Assistant"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_SECONDS: int = 60 * 60 * 24 * 7
    JWT_REFRESH_TOKEN_EXPIRE_SECONDS: int = 60 * 60 * 24 * 7
    JWT_PASSWORD_RESET_TOKEN_EXPIRE_SECONDS: int = 60 * 60 * 24

    # Google OAuth. The OAuth 2.0 Client ID of the desktop app. Required to
    # verify Google ID tokens on POST /auth/google; when empty that endpoint
    # rejects all requests.
    GOOGLE_CLIENT_ID: str | None = None

    # Uploads. MAX_UPLOAD_SIZE_BYTES caps the single-request multipart path
    # (POST /uploads/upload-file), which buffers the whole body in memory and so
    # stays small. Anything larger goes through the resumable tus endpoint
    # (/uploads/tus), which streams to disk and is capped separately.
    MAX_UPLOAD_SIZE_BYTES: int = 50 * 1024 * 1024
    TUS_MAX_UPLOAD_SIZE_BYTES: int = 2 * 1024 * 1024 * 1024
    # Scratch space for in-progress tus uploads; needs roughly
    # TUS_MAX_UPLOAD_SIZE_BYTES free per concurrent upload.
    TUS_UPLOAD_DIR: str = "uploads_media/.tus"
    # Abandoned uploads (client never finished) are reaped after this long.
    TUS_UPLOAD_EXPIRY_SECONDS: int = 60 * 60 * 24

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

    # Soniox cloud STT + speaker diarization (preferred for transcription when
    # set; otherwise the local Whisper + pyannote pipeline is used).
    SONIOX_API_KEY: str | None = None
    SONIOX_BASE_URL: str = "https://api.soniox.com"
    SONIOX_MODEL: str = "stt-async-v5"

    # Live single-utterance STT for cloud-mode live transcription
    # (POST /inference/transcribe-utterance). Any OpenAI-compatible *synchronous*
    # /audio/transcriptions endpoint (OpenAI, or a local server). Kept separate
    # from Soniox because that path is async/polling and too slow for the live
    # critical path. When STT_BASE_URL is empty the local faster-whisper model
    # (WHISPER_MODEL) is used instead — single utterance, no diarization.
    STT_BASE_URL: str = ""
    STT_API_KEY: str | None = None
    STT_MODEL: str = "whisper-1"

    model_config = SettingsConfigDict(env_file=".env")


SETTINGS = Settings()