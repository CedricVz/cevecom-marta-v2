# HeyGen stack KB

Fecha: 2026-06-12

## Resumen ejecutivo

En este proyecto, HeyGen Video Agent queda clasificado como herramienta de prototipo, no como motor confiable para video final controlado.

La razon es practica: Video Agent interpreta creativamente un prompt amplio. Puede producir borradores utiles, pero no garantiza control fino sobre guion, duracion, composicion, subtitulos, assets, cierre o audio.

## Piezas del stack

### HeyGen Video Agent

Video Agent recibe un prompt amplio y assets adjuntos. Decide composicion, estructura visual, uso de B-roll, subtitulos, ritmo, cierres y parte de la edicion.

Conviene usarlo cuando:

- necesitamos un borrador rapido;
- queremos explorar estilo, ritmo o direccion creativa;
- el coste de una salida imperfecta es aceptable;
- hay QA humana antes de aprobar.

No conviene usarlo cuando:

- el guion hablado debe ser inmutable;
- los assets deben aparecer exactamente en escenas/timestamps concretos;
- los subtitulos deben tener control de texto, timing y estilo;
- el cierre/logo debe quedar exactamente definido;
- un fallo implica re-render caro o entrega urgente.

### API directa / CLI

La API directa de HeyGen permite integraciones mas programaticas. Segun la documentacion publica de HeyGen Developers, la API V3 permite crear videos con campos explicitos como `type`, `avatar_id`, `engine`, `script` y `voice_id`.

La CLI usa API key y consume balance API. HeyGen documenta que MCP y API/CLI no usan el mismo pool de facturacion: MCP descuenta del plan web/premium credits, mientras Skills/API directa descuentan del balance API.

### MCP

El MCP conecta herramientas como Claude/Codex con HeyGen via OAuth. Es comodo para operar desde el agente, subir assets y lanzar procesos, pero sigue dependiendo de las herramientas disponibles en el MCP y del estado del token OAuth.

Uso recomendado aqui:

- verificar conexion antes de cualquier render;
- subir assets reutilizables;
- consultar sesiones o videos;
- ejecutar pruebas controladas solo cuando el flujo este aprobado.

Uso no recomendado:

- renders a ciegas;
- follow-up sin coste estimado;
- correcciones iterativas sin QA/captura de creditos.

### Assets

Los assets son medios reutilizables en HeyGen: videos, imagenes o logo. En este proyecto se usan como `asset_id` dentro de `files`.

Reglas aprendidas:

- los assets deben estar normalizados a 9:16 real cuando se usen en Reels;
- no basta con pedir "portrait 9:16" en prompt;
- si un asset esta codificado como landscape, square, con rotacion o SAR/DAR raro, HeyGen puede recortarlo o colocarlo mal;
- el logo debe tratarse como asset visual, no como texto ni narracion.

## Riesgos detectados en Marta

- Interpreta creativamente aunque el prompt sea estricto.
- Cambia duracion: Fila 3 paso a 63.5363s en el ultimo render.
- Puede anadir narracion no solicitada.
- Puede leer o transformar instrucciones tecnicas como si fueran texto hablado.
- Puede duplicar textos/subtitulos o convertir notas de escena en overlays.
- Puede generar bandas negras, placeholders, bloques vacios o huecos visuales.
- Puede alterar guion/audio en follow-up.
- El follow-up de Fila 3 corrigio el bloque negro, pero altero el audio con narracion tecnica.
- El follow-up consumio 17 premium credits en la prueba medida.
- El resultado final puede quedar visualmente lejos de lo aprobado aunque el render tecnicamente complete.

## Regla operativa

Video Agent se puede usar para prototipos y borradores.

No se debe considerar motor final confiable para entregables controlados de Marta sin QA estricta, descarga inmediata del MP4 final y aprobacion humana.

Para produccion, separar responsabilidades:

- guion hablado bloqueado;
- avatar/voz bloqueados;
- assets/B-roll preseleccionados y normalizados;
- subtitulos controlados;
- logo/cierre controlados;
- revision visual/audio antes de marcar como aprobado.

## Fuentes utiles

- HeyGen Developers: https://developers.heygen.com/
- HeyGen MCP: https://developers.heygen.com/ (seccion "MCP")
- HeyGen CLI/API: https://developers.heygen.com/ (secciones "CLI" y "API reference")
- Organizacion GitHub HeyGen-Official: https://github.com/HeyGen-Official

Nota: a fecha de esta revision, la organizacion publica `HeyGen-Official` aparece archivada y sin repos publicos visibles. No debe asumirse que haya SDKs oficiales mantenidos en GitHub sin verificar de nuevo.
