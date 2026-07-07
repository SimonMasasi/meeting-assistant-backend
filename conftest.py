"""
Root conftest – loaded by pytest before any test module.
Environment variables MUST be set here so that pydantic-settings
picks them up when config.py / src/shared/database.py are first imported.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_database.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("DEBUG", "True")
os.environ.setdefault("HUGGINGFACE_TOKEN", "fake-hf-token")
# Real env vars beat .env in pydantic-settings; without this a developer's live
# SONIOX_API_KEY in .env would route test transcriptions to the cloud.
os.environ.setdefault("SONIOX_API_KEY", "")
os.environ.setdefault("USE_RUSTF_UPLOADS", "False")
