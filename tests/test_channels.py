import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.channels as ch_mod
from app.channels import (
    load_channels,
    save_channels,
    import_user_channels,
    auto_discover_channels,
    init_channels,
    get_all_channels,
    get_channel_by_category,
    get_category_by_chat,
)


@pytest.fixture(autouse=True)
def _reset_channels():
    old = ch_mod._channels[:], dict(ch_mod._by_category), dict(ch_mod._by_chat)
    ch_mod._channels.clear()
    ch_mod._by_category.clear()
    ch_mod._by_chat.clear()
    yield
    ch_mod._channels[:] = old[0]
    ch_mod._by_category.clear()
    ch_mod._by_category.update(old[1])
    ch_mod._by_chat.clear()
    ch_mod._by_chat.update(old[2])


class TestLoadChannels:
    def test_file_exists(self, test_settings, tmp_path):
        channels_data = [{"chat_id": "-100", "category_id": 1000, "name": "Ch1"}]
        with open(test_settings.CHANNELS_FILE, "w") as f:
            json.dump(channels_data, f)
        result = load_channels()
        assert len(result) == 1
        assert result[0]["name"] == "Ch1"
        assert get_channel_by_category(1000)["name"] == "Ch1"

    def test_file_missing(self, test_settings):
        result = load_channels()
        assert result == []


class TestSaveChannels:
    def test_persists(self, test_settings):
        channels = [{"chat_id": "-100", "category_id": 1000, "name": "Saved"}]
        save_channels(channels)
        with open(test_settings.CHANNELS_FILE) as f:
            data = json.load(f)
        assert data[0]["name"] == "Saved"

    def test_creates_directory(self, test_settings, monkeypatch):
        nested = os.path.join(os.path.dirname(test_settings.CHANNELS_FILE), "sub", "channels.json")
        monkeypatch.setattr(test_settings, "CHANNELS_FILE", nested)
        save_channels([{"chat_id": "-1", "category_id": 1000, "name": "X"}])
        assert os.path.exists(nested)

    def test_rebuilds_indexes(self, test_settings):
        save_channels([
            {"chat_id": "-100", "category_id": 1000, "name": "A"},
            {"chat_id": "-200", "category_id": 1001, "name": "B"},
        ])
        assert get_channel_by_category(1000)["name"] == "A"
        assert get_category_by_chat("-200")["name"] == "B"


class TestImportUserChannels:
    def test_import(self, tmp_path):
        data = {
            "marked_channels": [{"id": -100, "name": "Chan1"}],
            "marked_groups": [{"id": -200, "name": "Group1"}],
        }
        path = str(tmp_path / "user_channels.json")
        with open(path, "w") as f:
            json.dump(data, f)
        result = import_user_channels(path)
        assert len(result) == 2
        assert result[0]["chat_id"] == "-100"
        assert result[0]["category_id"] == 1000
        assert result[1]["chat_id"] == "-200"
        assert result[1]["category_id"] == 1001

    def test_empty(self, tmp_path):
        data = {"marked_channels": [], "marked_groups": []}
        path = str(tmp_path / "user_channels.json")
        with open(path, "w") as f:
            json.dump(data, f)
        result = import_user_channels(path)
        assert result == []


class TestAutoDiscoverChannels:
    async def test_discovers(self):
        from pyrogram.enums import ChatType

        dialogs = []
        for chat_type, chat_id, title, username in [
            (ChatType.CHANNEL, -100, "Channel1", "chan1"),
            (ChatType.SUPERGROUP, -200, "Group1", None),
        ]:
            dialog = MagicMock()
            dialog.chat.type = chat_type
            dialog.chat.id = chat_id
            dialog.chat.title = title
            dialog.chat.username = username
            dialogs.append(dialog)

        client = AsyncMock()

        async def fake_get_dialogs():
            for d in dialogs:
                yield d

        client.get_dialogs = fake_get_dialogs
        result = await auto_discover_channels(client)
        assert len(result) == 2
        assert result[0]["chat_id"] == "-100"
        assert result[0]["name"] == "Channel1"
        assert result[1]["username"] is None

    async def test_filters_non_channels(self):
        from pyrogram.enums import ChatType

        dialogs = []
        for chat_type, chat_id, title in [
            (ChatType.PRIVATE, -1, "Private"),
            (ChatType.GROUP, -2, "SmallGroup"),
            (ChatType.CHANNEL, -3, "RealChannel"),
        ]:
            dialog = MagicMock()
            dialog.chat.type = chat_type
            dialog.chat.id = chat_id
            dialog.chat.title = title
            dialog.chat.username = None
            dialogs.append(dialog)

        client = AsyncMock()

        async def fake_get_dialogs():
            for d in dialogs:
                yield d

        client.get_dialogs = fake_get_dialogs
        result = await auto_discover_channels(client)
        assert len(result) == 1
        assert result[0]["name"] == "RealChannel"


class TestInitChannels:
    async def test_existing_file(self, test_settings):
        channels_data = [{"chat_id": "-100", "category_id": 1000, "name": "Existing"}]
        os.makedirs(os.path.dirname(test_settings.CHANNELS_FILE), exist_ok=True)
        with open(test_settings.CHANNELS_FILE, "w") as f:
            json.dump(channels_data, f)
        await init_channels()
        assert len(get_all_channels()) == 1
        assert get_all_channels()[0]["name"] == "Existing"

    async def test_auto_discover(self, test_settings, monkeypatch):
        from pyrogram.enums import ChatType

        client = AsyncMock()

        async def fake_get_dialogs():
            dialog = MagicMock()
            dialog.chat.type = ChatType.CHANNEL
            dialog.chat.id = -999
            dialog.chat.title = "Discovered"
            dialog.chat.username = "disc"
            yield dialog

        client.get_dialogs = fake_get_dialogs
        monkeypatch.setattr("app.telegram_client.get_client", lambda: client)
        # Ensure init triggers auto_discover path
        monkeypatch.setattr(test_settings, "USER_CHANNELS_FILE", "")

        await init_channels()
        assert len(get_all_channels()) == 1
        assert get_all_channels()[0]["name"] == "Discovered"


class TestLookups:
    def test_get_all_channels(self):
        ch_mod._channels[:] = [{"chat_id": "-1", "category_id": 1000, "name": "A"}]
        assert len(get_all_channels()) == 1

    def test_get_channel_by_category(self):
        ch = {"chat_id": "-1", "category_id": 1000, "name": "A"}
        ch_mod._by_category[1000] = ch
        assert get_channel_by_category(1000) == ch

    def test_get_channel_by_category_missing(self):
        assert get_channel_by_category(9999) is None

    def test_get_category_by_chat(self):
        ch = {"chat_id": "-1", "category_id": 1000, "name": "A"}
        ch_mod._by_chat["-1"] = ch
        assert get_category_by_chat("-1") == ch

    def test_get_category_by_chat_missing(self):
        assert get_category_by_chat("-9999") is None
