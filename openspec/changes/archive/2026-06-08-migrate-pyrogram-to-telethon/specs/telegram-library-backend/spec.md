# Telegram Library Backend Specification

## Purpose

Define the Telegram backend behavior required while replacing Pyrogram with Telethon and preserving product behavior.

## Requirements

### Requirement: Telethon-backed lifecycle and authentication

The system MUST use Telethon for Telegram runtime access and session creation. It MUST treat existing Pyrogram sessions as incompatible and MUST NOT overwrite them silently.

#### Scenario: Telethon session starts

- GIVEN valid Telegram API credentials and a Telethon session
- WHEN the service starts the Telegram backend
- THEN it authenticates and resolves the current account successfully

#### Scenario: Existing Pyrogram session is present

- GIVEN only an existing Pyrogram session file is present
- WHEN Telethon authentication is required
- THEN the system requires or creates a Telethon-compatible session without deleting the Pyrogram session

### Requirement: Backend-compatible Telegram operations

The system MUST preserve search, history pagination, direct message fetch, media metadata, thumbnail access, media download, stream resume, and flood-wait behavior through app-owned backend-neutral operations.

#### Scenario: Search returns media results

- GIVEN configured accessible Telegram channels
- WHEN a Torznab or API v2 search is executed
- THEN matching media messages include stable chat/message identifiers and media metadata

#### Scenario: Text match uses paired media message

- GIVEN a text-only search hit followed by a media message
- WHEN the search result is built
- THEN the media message can be fetched and used for the result

#### Scenario: Resume download from offset

- GIVEN a partially downloaded media file
- WHEN download resumes from the stored byte offset
- THEN bytes are streamed from that offset without corrupting persisted download state

#### Scenario: Telegram flood wait

- GIVEN Telegram returns a flood-wait error
- WHEN a backend operation handles it
- THEN the caller receives a retryable rate-limit response with the wait duration

### Requirement: Real-credential search gate before commits

The delivery process MUST block commits until real Telegram searches succeed with real credentials against real configured channels. Automated tests MUST NOT replace this gate.

#### Scenario: Gate passes

- GIVEN automated tests pass and real credentials/channels are configured
- WHEN real Torznab or API v2 searches return at least one valid result
- THEN a result maps to a fetchable `chat_id:msg_id` and synthetic torrent, and commits may proceed

#### Scenario: Gate fails

- GIVEN automated tests pass but real Telegram search authentication, channel access, or result mapping fails
- WHEN delivery is attempted
- THEN no commit is created until the real-search failure is resolved
