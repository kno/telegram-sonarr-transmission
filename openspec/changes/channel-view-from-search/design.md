# Diseño: Vista de canal desde resultados de búsqueda

## Enfoque técnico

Se agregará un navegador de canal sobre la API v2 existente, sin modificar Torznab ni Transmission RPC. El backend expondrá metadatos y mensajes paginados del canal usando Pyrogram; el frontend consumirá esos endpoints desde una nueva ruta SvelteKit `/channels/[id]`. La descarga por mensaje reutilizará `POST /api/v2/downloads?chat_id={chatId}&msg_id={msgId}`, por lo que no se introduce un nuevo flujo de descarga ni persistencia adicional.

## Arquitectura de componentes

### Backend

| Componente | Cambio | Responsabilidad |
|------------|--------|-----------------|
| `app/telegram_client.py` | Modificar | Agregar `get_channel_messages(chat_id, before=None, limit=20)` con `asyncio.Semaphore(2)` y `client.get_chat_history()` |
| `app/media.py` | Modificar | Extender `get_media()`/`extract_media_info()` para soportar `document`, `video`, `audio` y `photo` descargables |
| `app/api_v2/router.py` | Modificar | Agregar `GET /channels/{chatId}`, `GET /channels/{chatId}/messages` y endpoint de thumbnail con auth existente |
| `app/channels.py` | Usar | Validar que `chatId` pertenezca a canales conocidos mediante `get_category_by_chat()` |

### Frontend

| Componente | Cambio | Responsabilidad |
|------------|--------|-----------------|
| `frontend/src/routes/channels/[id]/+page.svelte` | Crear | Header del canal, listado, estados y paginación |
| `frontend/src/lib/api.ts` | Modificar | Agregar `getChannelInfo()`, `getChannelMessages()` y helper de descarga por `chat_id/msg_id` si se separa de Torznab |
| `frontend/src/lib/types.ts` | Modificar | Agregar `ChannelInfo`, `ChannelMessage`, `ChannelMessagesResponse`; extender `Channel` con `chatId` |
| `SearchResultCard.svelte` | Modificar | Convertir el badge de canal en enlace a `/channels/{chatId}` manteniendo estilo actual |
| `search/+page.svelte` | Modificar | Pasar `chatId` al card desde `channelsStore` |

## Decisiones de arquitectura

| Decisión | Alternativa | Rationale |
|----------|-------------|-----------|
| Semáforo nuevo `_channel_messages_semaphore = asyncio.Semaphore(2)` en `telegram_client.py` | Reusar `_search_semaphore` de `app/torznab/search.py` | Evita acoplar browsing con búsqueda Torznab y mantiene límites separados para operaciones distintas. |
| Validar `chatId` contra `channels.json` antes de consultar Telegram | Consultar cualquier `chatId` recibido | Reduce exposición accidental y permite 404 claro para canales no configurados. |
| Cursor `before` basado en `message_id` del último mensaje devuelto | Offset numérico de página | Telegram ya ordena por mensajes descendentes; `before` evita paginación inestable en canales activos. |
| Skeleton/spinner simple | Infinite scroll | El alcance excluye infinite scroll y la paginación explícita es más predecible ante flood-wait. |
| Extender `Channel.chatId` y cargar canales desde API v2 donde sea necesario | Resolver `chatId` desde Torznab caps | Caps solo expone categorías; la API v2 ya devuelve `chatId`, por lo que se evita inferencia frágil. |

## Flujo de datos

```text
Resultado de búsqueda
  └─ SearchResultCard(channelName, chatId)
       └─ <a href="/channels/{chatId}">
            └─ /channels/[id]/+page.svelte
                 ├─ getChannelMessages(apiKey, chatId, before?, limit)
                 └─ POST /api/v2/downloads?chat_id={chatId}&msg_id={message_id}
```

```text
GET /api/v2/channels/{chatId}/messages
  └─ validar API key
  └─ validar chatId conocido
  └─ get_channel_messages(chatId, before, limit)
       └─ semaphore max 2
       └─ Pyrogram get_messages(around) opcional + get_chat_history(offset_id=around|before)
       └─ filtrar media descargable
  └─ JSON: messages, has_more, next_cursor, channel
```

## Contratos de API

### `GET /api/v2/channels/{chatId}`

Parámetros: `apikey` obligatorio. `chatId` entero de Telegram.

Respuesta 200:

```json
{
  "id": -1001234,
  "title": "Mi Canal Series",
  "username": "miseries",
  "participants_count": 1200,
  "description": "Series en HD actualizadas"
}
```

### `GET /api/v2/channels/{chatId}/messages`

Parámetros: `apikey`, `before?: int`, `around?: int`, `limit: int = 20` con `le=50`.

Respuesta 200 usa nombres snake_case del spec backend:

```json
{
  "messages": [{
    "message_id": 251258,
    "date": "2025-06-01T14:30:00Z",
    "filename": "Show.S02E03.720p.mkv",
    "file_size": 1073741824,
    "mime_type": "video/x-matroska",
    "media_group_id": null,
    "text": null,
    "caption": "Mensaje original",
    "thumbnail_url": "/api/v2/channels/-1001234/messages/251258/thumbnail"
  }],
  "has_more": true,
  "next_cursor": 251258,
  "channel": { "id": -1001234, "title": "Mi Canal Series" }
}
```

Mapeo de errores: `401` API key inválida; `404` canal desconocido/sin acceso; `422` validación FastAPI; `429` flood-wait; `502` cliente Telegram no inicializado/desconectado.

### `GET /api/v2/channels/{chatId}/messages/{msgId}/thumbnail`

Parámetros: `apikey` obligatorio. Retorna el archivo de miniatura disponible para el mensaje. La implementación descarga solo el objeto thumbnail de Telegram, no el archivo de media completo.

## Paginación, deep-link y filtrado de media

`before` siempre significa “traer mensajes más antiguos que este `message_id`”. La primera página omite `before`. `around` se usa para abrir desde un resultado de búsqueda: el backend pide el mensaje exacto con `get_messages()` y luego completa la página con `get_chat_history(offset_id=around)`. `next_cursor` será el `message_id` del último mensaje devuelto cuando `has_more=true`.

El filtro debe reutilizar la semántica existente de `extract_media_info()`, ampliada a `audio` y `photo` si exponen `file_size`/`mime_type`. Se excluyen texto puro, stickers y GIFs/stickers sin archivo compatible con `download_media`/`get_messages`. Si un mensaje no tiene filename, se permite `filename=null`; la descarga ya usa fallback `unknown`.

## Árbol de UI y estado

```text
/channels/[id]/+page.svelte
  ├─ ChannelHeader(title, participants_count, description)
  ├─ ErrorBanner + Reintentar
  ├─ LoadingSkeleton/Spinner
  ├─ EmptyState
  ├─ MessageList
  │   └─ MessageRow(filename, size, date, download button)
  └─ PaginationControls(Anterior, Siguiente)
```

Estado local con runes: `loading`, `error`, `channel`, `messages`, `pageStack`, `nextCursor`, `hasMore`, `downloadingByMessage`. `pageStack` guarda cursores visitados para habilitar “Anterior” sin inventar offset numérico.

## Estrategia de pruebas

Backend con pytest estricto antes de implementar: pruebas unitarias de `get_channel_messages()` mockeando `client.get_chat_history()` como async iterator y `client.get_chat()` con `AsyncMock`; pruebas de router con `httpx.AsyncClient` para happy path, 404, 429, 502, 422 y auth. Actualizar `tests/conftest.py` para incluir `get_chat_history` en `mock_telegram_client`.

Frontend con Vitest/jsdom: tests de `api.ts` verificando URLs, `before`, parsing y mensajes por status; tests de componentes para `SearchResultCard` como `<a>`, estados de `/channels/[id]`, paginación y descarga.

## Orden de implementación

1. Tests backend para contratos y helpers de media.
2. Implementar `get_channel_messages()` y metadatos de canal.
3. Implementar endpoints API v2 y mapeo de errores.
4. Tests frontend de API/types/card.
5. Agregar tipos y funciones en `api.ts`.
6. Crear `/channels/[id]` con estados, paginación y descarga.
7. Verificación completa: `python3 -m pytest --cov=app --cov-report=term-missing` y `cd frontend && npm run test && npm run build`.

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Flood-wait por browsing repetido | Semáforo dedicado, `limit` máximo 50 y 429 con mensaje reintentable. |
| Cursor incorrecto por mensajes filtrados | Usar el último mensaje devuelto como cursor y cubrir con tests de páginas consecutivas. |
| `chatId` no disponible en resultados de búsqueda | Extender `Channel` con `chatId` y obtener canales desde API v2 para alimentar el mapa de búsqueda. |
| Media no compatible con descarga existente | Centralizar detección en `app/media.py` y probar document/video/audio/photo. |
| Sesión Telegram caída | Traducir `RuntimeError`/errores de conexión a 502 y mostrar reintento en UI. |

## Migración / rollout

No requiere migración de datos ni cambios de esquema persistente. Rollout reversible eliminando endpoints nuevos y ruta frontend.
