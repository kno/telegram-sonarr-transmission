# Propuesta: Vista de canal desde resultados de búsqueda

## Propósito

Cuando una búsqueda en Torznab devuelve solo un episodio de una serie, el usuario no puede explorar el canal de Telegram completo para ver qué otros archivos están disponibles. Esto obliga a abrir Telegram externamente o a hacer búsquedas separadas. El cambio permite navegar desde un resultado de búsqueda hasta el canal origen, ver su listado de mensajes con archivos, y descargar directamente desde allí.

## Alcance

### Incluye
- Enlace en SearchResultCard para navegar al canal origen
- Endpoint GET `/api/v2/channels/{chatId}/messages` con paginación cursor-based
- Ruta frontend `/channels/[id]` con listado de mensajes y metadatos del canal
- Botón de descarga por mensaje (reusa POST `/api/v2/downloads`)
- Metadatos del canal: nombre, miembros, descripción
- Paginación explícita (anterior/siguiente)

### Excluye
- Búsqueda dentro del canal (futuro, no requerido)
- Foto del canal (difiere implementación, requeriría manejo de binary)
- Infinite scroll (paginación explícita es más simple y robusta)
- WebSocket para mensajes en tiempo real
- Sincronización automática si la sesión Pyrogram se desconecta (manejo básico con error sí)

## Capacidades

### Nuevas Capacidades
- `channel-messages-api`: Endpoint REST paginado que expone mensajes de un canal de Telegram con metadata y filtros
- `channel-browser-ui`: Interfaz de navegación de canal con listado de mensajes, metadatos y descarga directa

### Capacidades Modificadas
- Ninguna (no existen specs previas en `openspec/specs/`)

## Enfoque

1. **Backend**: Nueva función `get_channel_messages()` en `app/telegram_client.py` que envuelve `get_chat_history()` con semaphore (max 2) y parámetros `chat_id`, `before` (message_id), `limit` (default 20, max 50)
2. **API**: Nuevo endpoint GET en `app/api_v2/` — `channels/{chatId}/messages` + endpoint para metadata del canal
3. **Frontend API**: Nueva función `getChannelMessages()` en `frontend/src/lib/api.ts`
4. **Frontend types**: Nuevo type `ChannelMessage` en `frontend/src/lib/types.ts`
5. **SearchResultCard**: Channel badge pasa de `<span>` a `<a>` tipo Link hacia `/channels/[id]`
6. **Nueva ruta**: `frontend/src/routes/channels/[id]/+page.svelte` — lista mensajes con paginación, muestra metadatos, botón de descarga por mensaje

## Áreas Afectadas

| Archivo | Impacto | Descripción |
|---------|---------|-------------|
| `app/telegram_client.py` | Modificado | Nueva función `get_channel_messages()` |
| `app/api_v2/router.py` | Modificado | Nuevas rutas GET channels/{chatId}/messages y channels/{chatId} |
| `frontend/src/lib/api.ts` | Modificado | Nueva función `getChannelMessages()` |
| `frontend/src/lib/types.ts` | Modificado | Nuevos tipos `ChannelMessage`, `ChannelInfo` |
| `frontend/src/lib/components/SearchResultCard.svelte` | Modificado | Canal navegable como link |
| `frontend/src/routes/channels/[id]/+page.svelte` | Nuevo | Página de browsing de canal |
| `frontend/src/routes/channels/+page.svelte` | Modificado | Si aplica, links a canales individuales |

## Riesgos

| Riesgo | Probabilidad | Mitigación |
|--------|-------------|------------|
| Flood-wait de Telegram en canales grandes (+10K msgs) | Media | Semaphore + límite default 20 + responder con error 429 manejable |
| Sesión Pyrogram expirada o desconectada | Baja | Error 502 con mensaje claro; reconexión automática en próxima request |
| Mensajes sin media (solo texto, stickers) | Alta | Filtrar en backend; el endpoint solo devuelve mensajes con `media_info` |
| Mensaje eliminado de Telegram entre resultado y visita | Baja | El endpoint omite el mensaje faltante sin error |

## Rollback

- Revertir commits en `app/api_v2/` y `app/telegram_client.py`
- Revertir cambios en frontend (`api.ts`, `types.ts`, `SearchResultCard.svelte`, nueva ruta)
- Sin migración de datos ni cambios en esquemas persistentes

## Dependencias

- Pyrogram `get_chat_history()` y `get_chat()` — APIs existentes, no requieren nuevos permisos
- Conexión activa de Telegram (no requiere nueva autenticación)

## Criterios de Éxito

- [ ] Click en badge de canal desde resultado de búsqueda navega a `/channels/[id]`
- [ ] La página de canal muestra nombre, miembros, descripción y lista de mensajes con archivos
- [ ] Paginación funciona: cursor por `message_id`, botones siguiente/anterior
- [ ] Cada mensaje con archivo tiene botón de descarga funcional (reusa API existente)
- [ ] Rate-limit de Telegram no bloquea la UI (spinner + error message)
- [ ] Tests: cobertura >80% en nuevo endpoint y función de mensajes
- [ ] Sin regresión en búsqueda existente ni en descargas
