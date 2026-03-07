#!/usr/bin/env python3
"""
Interactive Telegram authentication.
Run once to generate the .session file: docker compose run --rm torznab-auth
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PHONE = os.getenv("PHONE")
SESSION_NAME = os.getenv("SESSION_NAME", "torznab_session")
SESSION_DIR = os.getenv("SESSION_DIR", "/data")


def main():
    errors = []
    if not API_ID:
        errors.append("API_ID")
    if not API_HASH:
        errors.append("API_HASH")
    if not PHONE:
        errors.append("PHONE")
    if errors:
        print(f"Missing env vars: {', '.join(errors)}", file=sys.stderr)
        print("Create .env from .env.example", file=sys.stderr)
        sys.exit(1)

    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError

    session_path = os.path.join(SESSION_DIR, SESSION_NAME)
    os.makedirs(SESSION_DIR, exist_ok=True)

    print(f"Authenticating with Telegram...")
    print(f"Phone: {PHONE}")
    print(f"Session: {session_path}")

    client = TelegramClient(session_path, int(API_ID), API_HASH)

    async def do_auth():
        await client.connect()

        if await client.is_user_authorized():
            print("Already authenticated!")
            me = await client.get_me()
            print(f"User: {me.first_name} (@{me.username})")
            return

        print("Sending verification code...")
        await client.send_code_request(PHONE)

        code = input("Enter the code you received on Telegram: ")

        try:
            await client.sign_in(PHONE, code)
        except SessionPasswordNeededError:
            password = input("Enter your 2FA password: ")
            await client.sign_in(password=password)

        print("Authentication successful!")
        me = await client.get_me()
        print(f"User: {me.first_name} (@{me.username})")

    with client:
        client.loop.run_until_complete(do_auth())

    print(f"Session saved to: {session_path}.session")


if __name__ == "__main__":
    main()
