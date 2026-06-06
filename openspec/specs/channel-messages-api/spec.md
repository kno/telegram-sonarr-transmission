# API de Mensajes de Canal

## Propósito

Exponer los mensajes con archivos de un canal de Telegram como un endpoint REST paginado, reutilizando la semántica de cursor basada en `message_id`. Permite que el frontend navegue el contenido de un canal sin depender de Torznab.

## Requisitos

### Requisito: GET `/api/v2/channels/{chatId}/messages`

El sistema DEBE exponer un endpoint `GET /api/v2/channels/{chatId}/messages` autenticado vía API key que retorne mensajes con media de un canal de Telegram.

**Parámetros de request:**
| Parámetro | Tipo | Default | Máximo | Descripción |
|-----------|------|---------|--------|-------------|
| `chatId` (path) | `int` | — | — | ID numérico del canal Telegram |
| `before` (query) | `int?` | — | — | Cursor: message_id del último mensaje de la página anterior |
| `limit` (query) | `int` | 20 | 50 | Cantidad de mensajes por página |

**Respuesta 200 OK:**
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

**Errores:**
| Código | Condición |
|--------|-----------|
| 401 | API key inválida o ausente |
| 404 | Canal no encontrado o sin acceso |
| 422 | `chatId` no es entero válido, o `limit` > 50 |
| 429 | Rate limit de Telegram (flood-wait) |
| 502 | Sesión Pyrogram desconectada |

#### Escenario: Paginación hacia atrás (happy path)

- DADO un canal con más de 20 mensajes con media
- CUANDO se solicita `GET /api/v2/channels/-1001234/messages?limit=20`
- THEN se retornan 20 mensajes ordenados por `date` descendente
- Y `has_more` es `true`
- Y `next_cursor` es el `message_id` del último mensaje

#### Escenario: Paginación con cursor

- DADO que se recibió `next_cursor: 251240`
- CUANDO se solicita `GET /api/v2/channels/-1001234/messages?before=251240&limit=20`
- THEN se retornan hasta 20 mensajes anteriores a `251240`

#### Escenario: Sin más mensajes

- DADO un canal con menos de 20 mensajes con media
- CUANDO se solicitan mensajes con `limit=20`
- THEN `has_more` es `false`
- Y `next_cursor` es `null`

#### Escenario: Canal inexistente

- DADO un `chatId` que no corresponde a ningún canal accesible
- CUANDO se solicita `GET /api/v2/channels/-1009999/messages`
- THEN se retorna HTTP 404
- Y el cuerpo incluye `detail` con mensaje descriptivo

#### Escenario: Rate limit de Telegram

- DADO que Telegram responde con flood-wait
- CUANDO se solicita mensajes del canal
- THEN se retorna HTTP 429
- Y el cuerpo incluye `detail` con `"Rate limit exceeded. Intente de nuevo en N segundos."`

#### Escenario: Sesión desconectada

- DADO que la sesión Pyrogram no está iniciada o falló al reconectar
- CUANDO se solicita mensajes del canal
- THEN se retorna HTTP 502
- Y el cuerpo incluye `detail` con `"Conexión con Telegram perdida. Reintente."`

#### Escenario: `limit` excede máximo

- DADO un request con `limit=100`
- CUANDO se envía la solicitud
- THEN se retorna HTTP 422 (validation error de FastAPI)

### Requisito: Semáforo de concurrencia

El sistema DEBE limitar a 2 las llamadas concurrentes a `get_chat_history()` mediante un `asyncio.Semaphore(2)` para proteger contra flood-wait de Telegram.

#### Escenario: Tercera request concurrente

- DADO que 2 requests a `get_chat_history()` están en curso
- CUANDO llega una tercera request al mismo canal
- THEN la tercera request espera hasta que una de las primeras dos libere el semáforo

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
