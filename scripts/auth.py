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

    import asyncio
    from pyrogram import Client

    session_path = os.path.join(SESSION_DIR, SESSION_NAME)
    os.makedirs(SESSION_DIR, exist_ok=True)

    print("Authenticating with Telegram...")
    print(f"Phone: {PHONE}")
    print(f"Session: {session_path}")

    client = Client(
        session_path,
        api_id=int(API_ID),
        api_hash=API_HASH,
        phone_number=PHONE,
    )

    async def do_auth():
        await client.start()
        try:
            me = await client.get_me()
            print("Authentication successful!")
            print(f"User: {me.first_name} (@{me.username})")
        finally:
            await client.storage.save()
            await client.storage.close()

    asyncio.run(do_auth())

    print(f"Session saved to: {session_path}.session")


if __name__ == "__main__":
    main()
