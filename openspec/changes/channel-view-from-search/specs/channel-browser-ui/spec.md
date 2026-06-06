# Delta for channel-browser-ui

## ADDED Requirements

### Requirement: Ruta de navegación de canal

El sistema DEBE exponer la ruta SvelteKit `/channels/[id]` para mostrar metadatos del canal y mensajes con archivos. La pantalla DEBE cubrir estados de carga, vacío, error reintentable y datos cargados.

#### Scenario: Carga inicial exitosa

- DADO que el usuario navega a `/channels/-1001234`
- CUANDO la API responde con canal y mensajes
- ENTONCES se muestran título, miembros si existen, descripción si existe y lista de archivos
- Y cada fila muestra nombre de archivo, fecha, tamaño y acción de descarga

#### Scenario: Estado de carga

- DADO que el usuario abrió una página de canal
- CUANDO la respuesta aún no llegó
- ENTONCES se muestra spinner o skeleton
- Y los controles de paginación están deshabilitados

#### Scenario: Canal sin archivos

- DADO un canal sin mensajes con media descargable
- CUANDO se carga la página
- ENTONCES se muestra un estado vacío indicando que no hay archivos disponibles
- Y los metadatos del canal permanecen visibles

#### Scenario: Error reintentable

- DADO que la API retorna 429 o 502
- CUANDO se carga la página
- ENTONCES se muestra un mensaje de error claro
- Y se ofrece una acción para reintentar

### Requirement: Paginación explícita

El sistema DEBE ofrecer botones “Anterior” y “Siguiente” para navegar mensajes mediante cursor `before`. La UI DEBE mantener el historial de cursores visitados para volver a páginas anteriores sin usar offsets numéricos.

#### Scenario: Primera página

- DADO que el usuario está en la primera página
- CUANDO se renderizan los controles
- ENTONCES “Anterior” está deshabilitado o no se muestra
- Y “Siguiente” está habilitado solo si `has_more` es `true`

#### Scenario: Avanzar página

- DADO una página con `has_more: true` y `next_cursor`
- CUANDO el usuario selecciona “Siguiente”
- ENTONCES se consulta la API con `before={next_cursor}`
- Y “Anterior” queda disponible después de cargar

#### Scenario: Última página

- DADO una página con `has_more: false`
- CUANDO se renderizan los controles
- ENTONCES “Siguiente” está deshabilitado

### Requirement: Descarga directa por mensaje

El sistema DEBE permitir descargar cada mensaje visible reutilizando `POST /api/v2/downloads?chat_id={chatId}&msg_id={msgId}`. La acción DEBE mostrar estado en progreso, éxito y error por mensaje.

#### Scenario: Descarga exitosa

- DADO un mensaje con archivo visible
- CUANDO el usuario selecciona “Descargar”
- ENTONCES se llama a `POST /api/v2/downloads` con `chat_id` y `msg_id`
- Y el botón refleja progreso y éxito sin afectar otros mensajes

#### Scenario: Error de descarga

- DADO un mensaje cuyo archivo ya no está disponible
- CUANDO el usuario intenta descargarlo
- ENTONCES se muestra el error junto al mensaje
- Y la acción vuelve a quedar disponible para reintentar

### Requirement: Navegación desde resultado de búsqueda

El sistema DEBE convertir el badge de canal en `SearchResultCard` en un enlace hacia `/channels/{chatId}` cuando el resultado pueda mapearse a un canal. Cuando el resultado tenga `guid` con formato `chat_id:msg_id`, el enlace DEBE incluir `?message={msgId}` para abrir el navegador en el punto exacto encontrado. Si no hay canal disponible, DEBE conservar el comportamiento actual sin badge navegable.

#### Scenario: Badge enlazado

- DADO un resultado de búsqueda asociado a un canal conocido
- CUANDO se renderiza `SearchResultCard`
- ENTONCES el badge del canal es un enlace a `/channels/{chatId}`
- Y conserva el estilo visual actual

#### Scenario: Badge enlazado a mensaje encontrado

- DADO un resultado de búsqueda asociado a un canal conocido con `guid: -1001234:251258`
- CUANDO se renderiza `SearchResultCard`
- ENTONCES el badge del canal enlaza a `/channels/-1001234?message=251258`
- Y la página de canal solicita mensajes con `around=251258`
- Y el mensaje encontrado se muestra resaltado

#### Scenario: Resultado sin canal

- DADO un resultado sin canal mapeable
- CUANDO se renderiza `SearchResultCard`
- ENTONCES no se muestra un enlace de canal inválido

### Requirement: Tipos y capa API frontend

El sistema DEBE agregar tipos frontend para `ChannelInfo`, `ChannelMessage` y respuesta paginada, y DEBE exponer funciones de API para obtener metadatos y mensajes de canal.

#### Scenario: Consulta de mensajes sin cursor

- DADO una API key configurada
- CUANDO se invoca `getChannelMessages(apiKey, -1001234, undefined, 20)`
- ENTONCES se consulta `/api/v2/channels/-1001234/messages` con `apikey` y `limit=20`

#### Scenario: Consulta de mensajes con cursor

- DADO un `nextCursor` recibido previamente
- CUANDO se invoca `getChannelMessages` con ese cursor
- ENTONCES la URL incluye `before={nextCursor}`

#### Scenario: Consulta de mensajes alrededor de resultado

- DADO un `msgId` proveniente de un resultado de búsqueda
- CUANDO se invoca `getChannelMessages` con `around={msgId}`
- ENTONCES la URL incluye `around={msgId}` y no incluye `before`

### Requirement: Renderizado de contenido del mensaje

El sistema DEBE mostrar miniatura, texto o caption de mensajes cuando la API los provea. Si no hay miniatura o texto, la UI DEBE seguir mostrando filename, fecha, tamaño y acción de descarga.

#### Scenario: Mensaje con thumbnail y caption

- DADO un mensaje visible con `thumbnail_url` y `caption`
- CUANDO se renderiza la página del canal
- ENTONCES se muestra la miniatura autenticada
- Y se muestra el caption del mensaje junto al archivo
