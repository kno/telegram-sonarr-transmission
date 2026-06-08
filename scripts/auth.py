#!/usr/bin/env python3
"""
Interactive Telegram authentication.
Run once to generate the .session file: docker compose run --rm torznab-auth
"""
import os
import sys
import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PHONE = os.getenv("PHONE")
SESSION_NAME = os.getenv("SESSION_NAME", "torznab_session")
SESSION_DIR = os.getenv("SESSION_DIR", "/data")


@dataclass(frozen=True)
class SessionPaths:
    pyrogram_session_file: Path
    telethon_session_base: Path
    telethon_session_file: Path


def telethon_session_name(session_name: str) -> str:
    """Return a Telethon-specific session name without overwriting Pyrogram sessions."""
    return session_name if session_name.endswith("_telethon") else f"{session_name}_telethon"


def resolve_session_paths(session_dir: str, session_name: str) -> SessionPaths:
    base_dir = Path(session_dir)
    telethon_base = base_dir / telethon_session_name(session_name)
    return SessionPaths(
        pyrogram_session_file=base_dir / f"{session_name}.session",
        telethon_session_base=telethon_base,
        telethon_session_file=telethon_base.with_suffix(".session"),
    )


def missing_env_vars() -> list[str]:
    errors = []
    if not os.getenv("API_ID"):
        errors.append("API_ID")
    if not os.getenv("API_HASH"):
        errors.append("API_HASH")
    if not os.getenv("PHONE"):
        errors.append("PHONE")
    return errors


def mask_phone(phone: str | None) -> str:
    if not phone:
        return "<not set>"
    visible_digits = 2
    digits_seen = 0
    masked = []
    for char in reversed(phone):
        if char.isdigit():
            digits_seen += 1
            masked.append(char if digits_seen <= visible_digits else "*")
        else:
            masked.append(char)
    return "".join(reversed(masked))


async def authenticate_telethon(paths: SessionPaths):
    from getpass import getpass
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError

    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    phone = os.getenv("PHONE")
    client = TelegramClient(str(paths.telethon_session_base), int(api_id), api_hash)

    print(f"Telethon session: {paths.telethon_session_base}")
    await client.connect()
    try:
        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            code = input("Telegram login code: ").strip()
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                password = getpass("Two-step verification password: ")
                await client.sign_in(password=password)
        me = await client.get_me()
        print(f"Telethon authentication successful: {me.first_name} (@{me.username})")
    finally:
        await client.disconnect()
    print(f"Telethon session saved to: {paths.telethon_session_file}")


async def authenticate_pyrogram(paths: SessionPaths):
    if paths.pyrogram_session_file.exists():
        print(f"Using existing Pyrogram download session: {paths.pyrogram_session_file}")
        return

    try:
        from pyrogram import Client
    except ImportError as exc:
        raise RuntimeError("Pyrogram is required to create the download session") from exc

    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    phone = os.getenv("PHONE")

    print(f"Pyrogram download session: {paths.pyrogram_session_file}")
    client = Client(
        SESSION_NAME,
        api_id=int(api_id),
        api_hash=api_hash,
        phone_number=phone,
        workdir=SESSION_DIR,
    )
    await client.start()
    try:
        me = await client.get_me()
        print(f"Pyrogram authentication successful: {me.first_name} (@{me.username})")
    finally:
        await client.stop()
    print(f"Pyrogram session saved to: {paths.pyrogram_session_file}")


def main():
    parser = argparse.ArgumentParser(description="Create Telegram session files")
    parser.add_argument(
        "--backend",
        choices=("both", "telethon", "pyrogram"),
        default="both",
        help="Session backend to authenticate. Default: both.",
    )
    args = parser.parse_args()

    errors = missing_env_vars()
    if errors:
        print(f"Missing env vars: {', '.join(errors)}", file=sys.stderr)
        print("Create .env from .env.example", file=sys.stderr)
        sys.exit(1)

    paths = resolve_session_paths(SESSION_DIR, SESSION_NAME)
    os.makedirs(SESSION_DIR, exist_ok=True)

    print("Authenticating with Telegram...")
    print(f"Phone: {mask_phone(PHONE)}")

    async def run_auth():
        if args.backend in ("both", "telethon"):
            await authenticate_telethon(paths)
        if args.backend in ("both", "pyrogram"):
            await authenticate_pyrogram(paths)

    try:
        asyncio.run(run_auth())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
