# Navegador de Canal (Frontend)

## Propósito

Interfaz de usuario para explorar el contenido de un canal de Telegram desde la webapp, con listado paginado de mensajes con archivos, metadatos del canal y descarga directa.

## Requisitos

### Requisito: Ruta `/channels/[id]`

El sistema DEBE exponer una ruta `/channels/[id]` en SvelteKit que muestre el contenido completo de un canal.

#### Escenario: Carga inicial con datos

- DADO que el usuario navega a `/channels/-1001234`
- CUANDO el fetch de mensajes se completa exitosamente
- THEN se muestra el nombre del canal como título principal
- Y se muestra el contador de miembros
- Y se muestra la descripción del canal (si existe)
- Y se muestra una lista de mensajes con archivos
- Y cada mensaje muestra: nombre de archivo, fecha, tamaño y botón "Descargar"

#### Escenario: Estado de carga

- DADO que el usuario navega a `/channels/-1001234`
- CUANDO los datos aún no se reciben
- THEN se muestra un spinner o skeleton en lugar del listado
- Y los botones de paginación están deshabilitados

#### Escenario: Canal sin mensajes con media

- DADO un canal sin mensajes con archivos
- CUANDO se navega a `/channels/-1001234`
- THEN se muestra un estado vacío: "Este canal no tiene archivos disponibles"
- Y la metadata del canal sigue visible

#### Escenario: Error de sesión desconectada

- DADO que el backend retorna 502
- CUANDO se carga la página
- THEN se muestra un mensaje de error: "Conexión perdida con Telegram. Verifique que la sesión esté activa."
- Y se ofrece un botón de reintentar

#### Escenario: Error de rate limit

- DADO que el backend retorna 429
- CUANDO se carga la página
- THEN se muestra un mensaje de error: "Demasiadas solicitudes. Espere unos segundos y reintente."
- Y se ofrece un botón de reintentar

### Requisito: Paginación explícita

El sistema DEBE proporcionar botones "Anterior" y "Siguiente" para navegar entre páginas de mensajes, usando cursor-based pagination.

#### Escenario: Primera página

- DADO que el usuario está en la primera página
- CUANDO se renderiza la página
- THEN el botón "Anterior" está deshabilitado o no se muestra
- Y "Siguiente" está activo si `has_more` es `true`

#### Escenario: Navegación a página siguiente

- DADO que el usuario ve la primera página con `has_more: true`
- CUANDO hace clic en "Siguiente"
- THEN se dispara un fetch con `before={next_cursor}`
- Y se muestra un spinner durante la carga
- Y "Anterior" se habilita

#### Escenario: Última página

- DADO que el usuario está en la última página (`has_more: false`)
- CUANDO se renderiza la página
- THEN el botón "Siguiente" está deshabilitado
- Y "Anterior" está activo

### Requisito: Descarga por mensaje

El sistema DEBE permitir descargar el archivo de cada mensaje reutilizando el endpoint `POST /api/v2/downloads`.

#### Escenario: Descarga exitosa

- DADO un mensaje con archivo visible en la lista
- CUANDO el usuario hace clic en "Descargar"
- THEN se llama a `POST /api/v2/downloads?chat_id={chatId}&msg_id={msgId}`
- Y el botón muestra "Enviando..." durante la operación
- Y al completarse cambia a "Enviado" (deshabilitado)

#### Escenario: Error en descarga

- DADO un mensaje cuyo archivo ya no existe en Telegram
- CUANDO el usuario hace clic en "Descargar"
- THEN se muestra el error debajo del botón
- Y el botón vuelve a estado "Descargar" (reintentable)

### Requisito: SearchResultCard con enlace al canal

El sistema DEBE convertir el badge de canal en un enlace navegable hacia `/channels/[id]`.

#### Escenario: Badge es un link

- DADO un `SearchResult` con `categoryId` que mapea a un canal
- CUANDO se renderiza `SearchResultCard`
- THEN el badge del canal es un elemento `<a>` que navega a `/channels/{categoryId}`
- Y el badge conserva el mismo estilo visual actual

#### Escenario: Sin nombre de canal

- DADO un `SearchResult` sin `channelName`
- CUANDO se renderiza `SearchResultCard`
- THEN no se muestra ningún badge (comportamiento actual sin cambios)

### Requisito: Tipos y API layer

El sistema DEBE agregar tipos `ChannelMessage` y `ChannelInfo` en `types.ts`, y función `getChannelMessages()` en `api.ts`.

#### Escenario: Llamada API desde frontend

- DADO `apiKey` configurada
- CUANDO se invoca `getChannelMessages(apiKey, -1001234, undefined, 20)`
- THEN se hace fetch a `/api/v2/channels/-1001234/messages?apikey=...&limit=20`
- Y se retorna un objeto con `messages: ChannelMessage[]`, `hasMore: boolean`, `nextCursor: number | null`, `channel: ChannelInfo`

#### Escenario: Cursor en llamada API

- DADO un `nextCursor: 251240` de la respuesta anterior
- CUANDO se invoca `getChannelMessages(apiKey, -1001234, 251240, 20)`
- THEN la URL incluye `&before=251240`
