# Delta for Channel Messages API

## MODIFIED Requirements

### Requirement: GET `/api/v2/channels/{chatId}/messages`

The system MUST expose an API-key-authenticated `GET /api/v2/channels/{chatId}/messages` endpoint returning media messages from a Telegram channel through the configured Telegram backend, without leaking Pyrogram-specific session or error assumptions.
(Previously: the endpoint explicitly reported a disconnected Pyrogram session.)

Request parameters remain: `chatId` path integer; `before` optional cursor; `limit` default 20, max 50. Response 200 MUST keep `messages`, `has_more`, `next_cursor`, and `channel` fields with stable message metadata. Errors MUST remain 401, 404, 422, 429, and 502; 502 MUST mean the Telegram backend connection is unavailable.

#### Scenario: Backward pagination

- GIVEN a channel with more than 20 media messages
- WHEN `GET /api/v2/channels/-1001234/messages?limit=20` is requested
- THEN 20 messages are returned by descending date
- AND `has_more` is true and `next_cursor` is the last returned `message_id`

#### Scenario: Cursor pagination

- GIVEN `next_cursor: 251240` was returned
- WHEN `GET /api/v2/channels/-1001234/messages?before=251240&limit=20` is requested
- THEN up to 20 messages older than `251240` are returned

#### Scenario: No more messages

- GIVEN a channel with fewer than 20 media messages
- WHEN messages are requested with `limit=20`
- THEN `has_more` is false and `next_cursor` is null

#### Scenario: Inaccessible channel

- GIVEN a `chatId` with no accessible channel
- WHEN `GET /api/v2/channels/-1009999/messages` is requested
- THEN HTTP 404 is returned with descriptive `detail`

#### Scenario: Telegram rate limit

- GIVEN Telegram returns flood-wait
- WHEN channel messages are requested
- THEN HTTP 429 is returned with `detail` including the retry seconds

#### Scenario: Telegram backend disconnected

- GIVEN the Telegram backend is not started or reconnect failed
- WHEN channel messages are requested
- THEN HTTP 502 is returned with `detail` indicating Telegram connection loss

#### Scenario: `limit` exceeds maximum

- GIVEN a request with `limit=100`
- WHEN the request is sent
- THEN HTTP 422 is returned

### Requirement: Semáforo de concurrencia

The system MUST limit channel history retrieval to 2 concurrent Telegram backend calls to reduce flood-wait risk.
(Previously: concurrency was tied to Pyrogram `get_chat_history()` calls.)

#### Scenario: Third concurrent request

- GIVEN 2 channel history requests are in progress
- WHEN a third request arrives
- THEN it waits until one active request releases the semaphore
