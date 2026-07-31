# Backward compatibility shim - delegates to settings.py
from app.core.settings import settings


class Settings:
    """Legacy settings facade - delegates to the new settings instance."""
    DATAHUB_BASE_URL = settings.DATAHUB_BASE_URL
    DATAHUB_TOKEN = settings.DATAHUB_TOKEN
    USE_MOCK_DATAHUB = settings.USE_MOCK_DATAHUB
    API_BASE_URL = settings.FRONTEND_URL
    ENV = settings.ENV
    WRITERBACK_PATH = settings.WRITEBACK_PATH
