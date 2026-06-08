from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts import auth


def test_telethon_session_name_is_separate_from_pyrogram_session():
    assert auth.telethon_session_name("torznab_session") == "torznab_session_telethon"
    assert auth.telethon_session_name("already_telethon") == "already_telethon"


def test_resolve_session_paths_preserves_existing_pyrogram_session(tmp_path):
    pyrogram_session = tmp_path / "torznab_session.session"
    pyrogram_session.write_text("old pyrogram session")

    paths = auth.resolve_session_paths(str(tmp_path), "torznab_session")

    assert paths.pyrogram_session_file == pyrogram_session
    assert paths.telethon_session_base == tmp_path / "torznab_session_telethon"
    assert paths.telethon_session_file == tmp_path / "torznab_session_telethon.session"
    assert pyrogram_session.read_text() == "old pyrogram session"


def test_missing_env_vars_lists_required_values(monkeypatch):
    for name in ("API_ID", "API_HASH", "PHONE"):
        monkeypatch.delenv(name, raising=False)

    assert auth.missing_env_vars() == ["API_ID", "API_HASH", "PHONE"]


def test_mask_phone_keeps_only_last_two_digits():
    assert auth.mask_phone("+54 9 11 1234-5678") == "+** * ** ****-**78"


def test_main_redacts_phone_output(tmp_path, monkeypatch, capsys):
    raw_phone = "+541112345678"
    monkeypatch.setenv("API_ID", "12345")
    monkeypatch.setenv("API_HASH", "testhash")
    monkeypatch.setenv("PHONE", raw_phone)
    monkeypatch.setattr(auth, "PHONE", raw_phone)
    monkeypatch.setattr(auth, "SESSION_DIR", str(tmp_path))
    monkeypatch.setattr(auth, "SESSION_NAME", "torznab_session")
    monkeypatch.setattr("sys.argv", ["auth.py", "--backend", "telethon"])

    def fake_run(coro):
        coro.close()

    monkeypatch.setattr(auth.asyncio, "run", fake_run)

    auth.main()

    output = capsys.readouterr().out
    assert raw_phone not in output
    assert "Phone: +**********78" in output


async def test_authenticate_pyrogram_reuses_existing_session(tmp_path, monkeypatch):
    paths = auth.resolve_session_paths(str(tmp_path), "torznab_session")
    paths.pyrogram_session_file.write_text("legacy pyrogram session")
    monkeypatch.setitem(__import__("sys").modules, "pyrogram", None)

    await auth.authenticate_pyrogram(paths)

    assert paths.pyrogram_session_file.read_text() == "legacy pyrogram session"


async def test_authenticate_pyrogram_creates_missing_session(tmp_path, monkeypatch):
    paths = auth.resolve_session_paths(str(tmp_path), "torznab_session")
    monkeypatch.setenv("API_ID", "12345")
    monkeypatch.setenv("API_HASH", "testhash")
    monkeypatch.setenv("PHONE", "+10000000000")
    monkeypatch.setattr(auth, "SESSION_NAME", "torznab_session")
    monkeypatch.setattr(auth, "SESSION_DIR", str(tmp_path))
    calls = []

    class FakeClient:
        def __init__(self, name, api_id, api_hash, phone_number, workdir):
            calls.append((name, api_id, api_hash, phone_number, workdir))

        async def start(self):
            calls.append("start")

        async def get_me(self):
            return MagicMock(first_name="Test", username="test")

        async def stop(self):
            calls.append("stop")

    fake_pyrogram = MagicMock(Client=FakeClient)
    monkeypatch.setitem(__import__("sys").modules, "pyrogram", fake_pyrogram)

    await auth.authenticate_pyrogram(paths)

    assert calls == [("torznab_session", 12345, "testhash", "+10000000000", str(tmp_path)), "start", "stop"]


async def test_authenticate_pyrogram_missing_dependency_has_clear_error(tmp_path, monkeypatch):
    paths = auth.resolve_session_paths(str(tmp_path), "torznab_session")
    monkeypatch.setitem(__import__("sys").modules, "pyrogram", None)

    with pytest.raises(RuntimeError, match="Pyrogram is required"):
        await auth.authenticate_pyrogram(paths)
