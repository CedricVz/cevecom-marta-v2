# Decision de arquitectura: generacion de video

Fecha: 2026-06-12

## Contexto

El flujo actual con `tools/generar_video.py` usa HeyGen Video Agent mediante MCP. El sistema construye un prompt grande, adjunta assets por `asset_id`, fija avatar/voz/brand kit y espera a que HeyGen cree el video.

El resultado ha sido util para prototipos, pero no suficientemente confiable para entregables finales controlados:

- Fila 3 genero bloque negro.
- La reparacion local no preservo subtitulos ni corrigio el fallo.
- El follow-up de HeyGen corrigio el fallo visual, pero anadio narracion tecnica no solicitada.
- El nuevo render base completo tampoco siguio las instrucciones acordadas.

Decision: no seguir probando prompts a ciegas.

## Ruta A - Prototipo rapido

Motor: HeyGen Video Agent.

Uso:

- borradores;
- exploracion creativa;
- primeras versiones para entender tono;
- piezas donde se acepta variacion editorial.

Ventajas:

- rapido de operar;
- puede combinar avatar, voz, assets y edicion en un solo prompt;
- util cuando se busca una propuesta inicial.

Limitaciones:

- interpreta instrucciones;
- no garantiza timing exacto;
- no garantiza uso exacto de assets;
- puede modificar duracion;
- puede crear subtitulos/overlays inesperados;
- puede introducir fallos visuales;
- follow-up puede consumir creditos y alterar guion/audio.

Regla:

No usar esta ruta para entregables finales sin QA estricta. Si se usa, siempre:

- dry-run previo;
- render solo de la fila objetivo;
- descarga inmediata del MP4;
- revision humana;
- no marcar como aprobado automaticamente.

## Ruta B - Produccion controlada

Motor objetivo: pipeline con mas control programatico.

Principios:

- guion hablado bloqueado;
- avatar/voz bloqueados;
- B-roll controlado;
- subtitulos controlados;
- logo/cierre controlados;
- QA humana antes de actualizar cualquier estado como aprobado.

Requisitos minimos:

1. Texto hablado separado de instrucciones visuales.
2. Validacion dura de texto narrable antes de render.
3. Assets normalizados a 1080x1920 real, SAR 1:1, sin rotacion rara.
4. Lista de assets por escena/timestamp, no solo prompt generico.
5. Subtitulos generados desde texto/timestamps controlados cuando sea posible.
6. Cierre/logo aplicado por compositor controlado o API que acepte escena/capa explicita.
7. Export local descargado y auditado con ffprobe/frames antes de enviar a Marta.

## Estado de `tools/generar_video.py`

Partes que dependen de Video Agent:

- `_preparar_video_agent_payload()` construye un prompt unico para Video Agent.
- `_files_para_video_agent()` adjunta B-roll y logo como `asset_id`.
- `crear_video_heygen_mcp()` llama `create_video_agent`.
- `esperar_video_heygen_mcp()` consulta `get_video_agent_session` y luego `get_video`.
- El script delega composicion, escena, subtitulos, cierre, uso de B-roll y duracion en Video Agent.

Partes que generan imprevisibilidad:

- Un prompt unico mezcla guion, reglas visuales, notas de Marta, politica de subtitulos, B-roll y cierre.
- Las notas de escenas de Marta pueden contener instrucciones de texto/overlays que se reinterpretan por prompt.
- Los assets se entregan como disponibles, pero HeyGen decide como y cuando usarlos.
- Los subtitulos nativos quedan en manos de HeyGen.
- El logo/cierre depende de instrucciones textuales, no de una capa/timeline controlada.
- La duracion objetivo es una sugerencia, no un contrato.

Cambios necesarios para una prueba controlada de Fila 3 sin depender de decisiones editoriales de Video Agent:

- No usar `create_video_agent` como editor final.
- Generar o usar un clip de avatar con guion/voz bloqueados.
- Construir timeline externo con segmentos: avatar, B-roll, subtitulos y cierre.
- Forzar assets por tramo con duracion/timestamp definidos.
- Quemar o renderizar subtitulos desde una fuente controlada.
- Aplicar logo/cierre en compositor controlado.
- Validar resultado localmente con frames, duracion, audio y ausencia de bloques negros.

## Herramientas/referencias a evaluar sin instalar aun

HeyGen:

- HeyGen Developers: API reference, Video Generation, Avatars, Voices, Video Agent, MCP.
- HeyGen MCP para operaciones OAuth/web-plan cuando convenga.
- HeyGen API directa para pruebas mas programaticas si se acepta usar balance API separado.

Video/composicion:

- ffmpeg/ffprobe para inspeccion, normalizacion, recortes, concat, audio y subtitulos quemados.
- Remotion para timeline React controlado si se quiere compositor programatico.
- MoviePy o PyAV si se prefiere prototipo Python.

QA visual/audio:

- ffprobe para duracion, streams, resolucion, SAR/DAR, codec y fps.
- extraccion de frames por timestamp para revision humana.
- deteccion simple de frames negros con ffmpeg `blackdetect` o analisis de luminancia.
- Whisper/local STT o OpenAI transcription para comprobar que no aparece narracion tecnica.

Documentacion/herramientas para Codex:

- documentacion oficial HeyGen Developers antes de tocar integraciones;
- changelog/API reference de HeyGen antes de asumir campos disponibles;
- docs internas del repo: `docs/HEYGEN_OAUTH_PROTOCOL.md`, `docs/HEYGEN_VIDEO_REPAIR_PROTOCOL.md` y este documento.

## Propuesta de siguiente paso

No regenerar Fila 3 con prompts.

Preparar una prueba tecnica pequena de Ruta B:

1. Definir timeline fijo de Fila 3 con guion, B-roll y cierre.
2. Verificar si HeyGen API directa permite obtener solo avatar/voz con script bloqueado sin Video Agent editorial.
3. Si no, usar el mejor MP4 base de avatar y componer B-roll/subtitulos/logo fuera de Video Agent.
4. Auditar salida localmente antes de cualquier nuevo gasto.

Resultado esperado: decidir con datos si Marta necesita un pipeline de video controlado o si Video Agent queda solo para bocetos.
