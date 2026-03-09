import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings, _SettingsProxy


class _NoEnvSettings(Settings):
    """Settings subclass that ignores .env file for test isolation."""
    model_config = {"env_file": None, "extra": "ignore"}


@pytest.fixture(autouse=True)
def _clear_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def _env(monkeypatch):
    monkeypatch.setenv("API_ID", "12345")
    monkeypatch.setenv("API_HASH", "testhash")
    monkeypatch.setenv("TORZNAB_APIKEY", "testapikey")
    # Clear any env vars that would override defaults
    for var in ("BASE_URL", "DOWNLOAD_DIR", "CHANNELS_FILE", "SESSION_DIR",
                "SESSION_NAME", "DEFAULT_LIMIT", "MAX_LIMIT", "USER_CHANNELS_FILE"):
        monkeypatch.delenv(var, raising=False)


class TestSettings:
    def test_loads_from_env(self, _env):
        s = _NoEnvSettings()
        assert s.API_ID == 12345
        assert s.API_HASH == "testhash"
        assert s.TORZNAB_APIKEY == "testapikey"

    def test_defaults(self, _env):
        s = _NoEnvSettings()
        assert s.SESSION_NAME == "torznab_session"
        assert s.DEFAULT_LIMIT == 50
        assert s.MAX_LIMIT == 100
        assert s.BASE_URL == "http://localhost:9117"
        assert s.DOWNLOAD_DIR == "/data/cache"
        assert s.CHANNELS_FILE == "/data/channels.json"
        assert s.SESSION_DIR == "/data"
        assert s.USER_CHANNELS_FILE == ""

    def test_missing_required_raises(self, monkeypatch):
        monkeypatch.delenv("API_ID", raising=False)
        monkeypatch.delenv("API_HASH", raising=False)
        monkeypatch.delenv("TORZNAB_APIKEY", raising=False)
        with pytest.raises(ValidationError):
            _NoEnvSettings()

    def test_extra_ignored(self, _env, monkeypatch):
        monkeypatch.setenv("TOTALLY_UNKNOWN_VAR", "whatever")
        s = Settings()
        assert not hasattr(s, "TOTALLY_UNKNOWN_VAR")

    def test_get_settings_cached(self, _env):
        a = get_settings()
        b = get_settings()
        assert a is b

    def test_proxy_lazy(self):
        proxy = _SettingsProxy()
        # Creating proxy should not raise, only attribute access would
        assert isinstance(proxy, _SettingsProxy)
