import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.telegram_client as tc_mod


@pytest.fixture(autouse=True)
def _reset_client():
    old = tc_mod._client
    tc_mod._client = None
    yield
    tc_mod._client = old


class TestGetClient:
    def test_before_connect_raises(self):
        with pytest.raises(RuntimeError, match="not initialized"):
            tc_mod.get_client()

    def test_after_setting_client(self):
        mock_client = MagicMock()
        tc_mod._client = mock_client
        assert tc_mod.get_client() is mock_client


class TestSessionPath:
    def test_joins_dir_and_name(self, test_settings):
        result = tc_mod._session_path()
        assert result == os.path.join(test_settings.SESSION_DIR, test_settings.SESSION_NAME)


class TestConnectClient:
    @patch("app.telegram_client.Client")
    async def test_connect(self, MockClient, test_settings):
        mock_instance = AsyncMock()
        mock_instance.get_me = AsyncMock(return_value=MagicMock(first_name="Test", username="testbot"))

        async def fake_dialogs():
            yield MagicMock()
            yield MagicMock()

        mock_instance.get_dialogs = fake_dialogs
        MockClient.return_value = mock_instance

        result = await tc_mod.connect_client()

        assert result is mock_instance
        mock_instance.start.assert_called_once()
        mock_instance.get_me.assert_called_once()
        assert tc_mod._client is mock_instance


class TestDisconnectClient:
    async def test_disconnect(self):
        mock_client = AsyncMock()
        tc_mod._client = mock_client
        await tc_mod.disconnect_client()
        mock_client.stop.assert_called_once()
        assert tc_mod._client is None

    async def test_disconnect_when_none(self):
        tc_mod._client = None
        await tc_mod.disconnect_client()  # Should not raise
        assert tc_mod._client is None
