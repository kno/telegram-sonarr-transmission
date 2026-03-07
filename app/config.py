from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_ID: int
    API_HASH: str
    SESSION_NAME: str = "torznab_session"
    SESSION_DIR: str = "/data"
    TORZNAB_APIKEY: str
    CHANNELS_FILE: str = "/data/channels.json"
    USER_CHANNELS_FILE: str = ""
    DEFAULT_LIMIT: int = 50
    MAX_LIMIT: int = 100
    BASE_URL: str = "http://localhost:9117"
    DOWNLOAD_DIR: str = "/data/cache"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


class _SettingsProxy:
    """Lazy proxy — validation runs on first attribute access, not at import."""
    def __getattr__(self, name):
        return getattr(get_settings(), name)


settings = _SettingsProxy()
