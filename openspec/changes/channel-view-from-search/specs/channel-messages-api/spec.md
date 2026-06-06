# Delta for channel-messages-api

## ADDED Requirements

### Requirement: Mensajes paginados de canal

El sistema DEBE exponer `GET /api/v2/channels/{chatId}/messages`, autenticado con API key, para retornar mensajes con media descargable de un canal conocido. La respuesta DEBE incluir `messages`, `has_more`, `next_cursor` y metadatos del canal. El parámetro `limit` DEBE tener default 20 y máximo 50; `before` DEBE actuar como cursor basado en `message_id` y `around` DEBE permitir cargar una página que incluya un mensaje encontrado.

#### Scenario: Primera página con más resultados

- DADO un canal conocido con más de 20 mensajes con media descargable
- CUANDO se solicita `GET /api/v2/channels/-1001234/messages?limit=20`
- ENTONCES se retornan 20 mensajes ordenados de más nuevo a más antiguo
- Y `has_more` es `true` y `next_cursor` es el `message_id` del último mensaje retornado

#### Scenario: Página con cursor

- DADO que la página anterior devolvió `next_cursor: 251240`
- CUANDO se solicita `GET /api/v2/channels/-1001234/messages?before=251240&limit=20`
- ENTONCES se retornan hasta 20 mensajes anteriores a `251240`

#### Scenario: Página alrededor de mensaje encontrado

- DADO que una búsqueda devolvió `guid: -1001234:251258`
- CUANDO se solicita `GET /api/v2/channels/-1001234/messages?around=251258&limit=20`
- ENTONCES la respuesta incluye el mensaje `251258` si sigue disponible y tiene media descargable
- Y la paginación `before` permanece disponible para páginas más antiguas

#### Scenario: Sin más resultados

- DADO un canal conocido con menos mensajes con media que el `limit`
- CUANDO se solicitan sus mensajes
- ENTONCES `has_more` es `false`
- Y `next_cursor` es `null`

### Requirement: Validación y errores del endpoint

El sistema DEBE validar API key, `chatId`, `limit` y disponibilidad de Telegram. Los errores DEBEN mapearse a HTTP 401 para API key inválida, 404 para canal desconocido o inaccesible, 422 para parámetros inválidos, 429 para flood-wait y 502 para sesión Telegram desconectada.

#### Scenario: Canal desconocido

- DADO un `chatId` que no corresponde a un canal configurado o accesible
- CUANDO se solicita `GET /api/v2/channels/-1009999/messages`
- ENTONCES se retorna HTTP 404 con `detail` descriptivo

#### Scenario: Rate limit de Telegram

- DADO que Telegram responde con flood-wait al listar mensajes
- CUANDO se solicita el endpoint de mensajes
- ENTONCES se retorna HTTP 429 con un mensaje reintentable

#### Scenario: Límite inválido

- DADO un request con `limit=100`
- CUANDO se envía la solicitud
- ENTONCES se retorna HTTP 422

### Requirement: Filtrado de media descargable y concurrencia

El sistema DEBE retornar solo mensajes con media descargable y DEBE omitir texto puro, stickers u otros mensajes no descargables. El sistema DEBE limitar a 2 las llamadas concurrentes de browsing de canal hacia Telegram para reducir riesgo de flood-wait.

#### Scenario: Mensajes no descargables omitidos

- DADO un canal con mensajes de texto, stickers, documentos y videos
- CUANDO se solicitan mensajes del canal
- ENTONCES solo los mensajes con media descargable aparecen en `messages`

#### Scenario: Tercera solicitud concurrente

- DADO que 2 solicitudes de browsing de canal están consultando Telegram
- CUANDO llega una tercera solicitud
- ENTONCES la tercera espera hasta que una consulta anterior libere capacidad

### Requirement: Metadatos del canal

El sistema DEBE incluir metadatos del canal en la respuesta de mensajes y DEBERÍA exponer `GET /api/v2/channels/{chatId}` para obtenerlos sin listar mensajes. Los metadatos DEBEN incluir `id` y `title`, y PUEDEN incluir `username`, `participants_count` y `description`.

#### Scenario: Endpoint dedicado de metadatos

- DADO un canal conocido
- CUANDO se solicita `GET /api/v2/channels/-1001234`
- ENTONCES se retorna HTTP 200 con `id`, `title` y metadatos opcionales disponibles

### Requirement: Contenido textual y miniaturas de mensajes

El sistema DEBE incluir `text`, `caption` y `thumbnail_url` en cada DTO de mensaje. `thumbnail_url` DEBE apuntar a un endpoint autenticado que descargue únicamente el thumbnail disponible del mensaje, no el archivo completo.

#### Scenario: Mensaje con caption y thumbnail

- DADO un mensaje con media descargable, caption y thumbnail de Telegram
- CUANDO se solicitan mensajes del canal
- ENTONCES el DTO incluye `caption`, `text` si existe y `thumbnail_url`

#### Scenario: Endpoint de thumbnail

- DADO un mensaje con thumbnail disponible
- CUANDO se solicita `GET /api/v2/channels/{chatId}/messages/{msgId}/thumbnail`
- ENTONCES se retorna el archivo de miniatura
- Y no se descarga el archivo de media completo
