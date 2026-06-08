# API de Mensajes de Canal

## Propósito

Exponer los mensajes con archivos de un canal de Telegram como un endpoint REST paginado, reutilizando la semántica de cursor basada en `message_id`. Permite que el frontend navegue el contenido de un canal sin depender de Torznab.

## Requisitos

### Requirement: GET `/api/v2/channels/{chatId}/messages`

The system MUST expose an API-key-authenticated `GET /api/v2/channels/{chatId}/messages` endpoint returning media messages from a Telegram channel through the configured Telegram backend, without leaking Pyrogram-specific session or error assumptions.
(Previously: the endpoint explicitly reported a disconnected Pyrogram session.)

**Request parameters:**
| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `chatId` (path) | `int` | — | — | Numeric Telegram channel ID |
| `before` (query) | `int?` | — | — | Cursor: message_id of the last message on the previous page |
| `limit` (query) | `int` | 20 | 50 | Number of messages per page |

**Response 200 OK:**
```json
{
  "messages": [
    {
      "message_id": 251258,
      "date": "2025-06-01T14:30:00Z",
      "filename": "Show.S02E03.720p.mkv",
      "file_size": 1073741824,
      "mime_type": "video/x-matroska",
      "media_group_id": null
    }
  ],
  "has_more": true,
  "next_cursor": 251240,
  "channel": {
    "id": -1001234,
    "title": "Mi Canal Series",
    "username": "miseries",
    "participants_count": 1200,
    "description": "Series en HD actualizadas"
  }
}
```

**Errors:**
| Code | Condition |
|------|-----------|
| 401 | Invalid or missing API key |
| 404 | Channel not found or inaccessible |
| 422 | `chatId` not a valid integer, or `limit` > 50 |
| 429 | Telegram rate limit (flood-wait) |
| 502 | Telegram backend connection unavailable |

#### Scenario: Backward pagination (happy path)

- GIVEN a channel with more than 20 media messages
- WHEN `GET /api/v2/channels/-1001234/messages?limit=20` is requested
- THEN 20 messages are returned sorted by descending `date`
- AND `has_more` is `true`
- AND `next_cursor` is the `message_id` of the last message

#### Scenario: Cursor pagination

- GIVEN `next_cursor: 251240` was returned
- WHEN `GET /api/v2/channels/-1001234/messages?before=251240&limit=20` is requested
- THEN up to 20 messages older than `251240` are returned

#### Scenario: No more messages

- GIVEN a channel with fewer than 20 media messages
- WHEN messages are requested with `limit=20`
- THEN `has_more` is `false`
- AND `next_cursor` is `null`

#### Scenario: Inaccessible channel

- GIVEN a `chatId` with no accessible channel
- WHEN `GET /api/v2/channels/-1009999/messages` is requested
- THEN HTTP 404 is returned with descriptive `detail`

#### Scenario: Telegram rate limit

- GIVEN Telegram returns flood-wait
- WHEN channel messages are requested
- THEN HTTP 429 is returned with `detail` indicating retry duration in seconds

#### Scenario: Telegram backend disconnected

- GIVEN the Telegram backend is not started or reconnect failed
- WHEN channel messages are requested
- THEN HTTP 502 is returned with `detail` indicating Telegram connection loss

#### Scenario: `limit` exceeds maximum

- GIVEN a request with `limit=100`
- WHEN the request is sent
- THEN HTTP 422 is returned (FastAPI validation error)

### Requirement: Concurrency semaphore

The system MUST limit channel history retrieval to 2 concurrent Telegram backend calls to reduce flood-wait risk.
(Previously: concurrency was tied to Pyrogram `get_chat_history()` calls.)

#### Scenario: Third concurrent request

- GIVEN 2 channel history requests are in progress
- WHEN a third request arrives
- THEN it waits until one active request releases the semaphore

### Requisito: Filtro solo media

El sistema DEBE filtrar los mensajes del canal para retornar solo aquellos que contengan media descargable (documento, video, audio, foto como archivo).

#### Escenario: Mensaje sin media es omitido

- DADO un canal con mensajes de texto, stickers, y un documento
- CUANDO se solicitan mensajes
- THEN el mensaje de texto y el sticker NO aparecen en la respuesta
- Y el documento SÍ aparece

### Requisito: Metadatos del canal

El sistema DEBE exponer metadatos del canal en la respuesta de mensajes y opcionalmente en un endpoint dedicado `GET /api/v2/channels/{chatId}`.

#### Escenario: Endpoint dedicado

- DADO un canal existente
- CUANDO se solicita `GET /api/v2/channels/-1001234`
- THEN se retorna `{id, title, username?, participants_count?, description?}`
- Y el campo `description` se trunca a 500 caracteres si excede
