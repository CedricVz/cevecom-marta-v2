# Checkpoint vídeo Marta Suñé — junio 2026

Fecha del checkpoint: 2026-06-14

## 1. Estado general

* El sistema genera vídeos con HeyGen.
* El primer vídeo válido, correspondiente a Sheet1 Fila 2, fue aprobado visualmente por Cedric.
* Sheet1 Fila 3 fue rechazada y marcada como:
  `Rechazado - regenerar`
* No se continuará intentando edición quirúrgica de vídeos rechazados.
* Si Marta rechaza un vídeo, se generará una nueva versión desde cero utilizando su feedback.
* La regeneración puede consumir créditos adicionales y debe comunicarse de forma transparente.

## 2. Vídeo aprobado

Sheet1 Fila 2:

* video_id aprobado:
  `3afd794bb30e40ea99c362a744cd5783`
* archivo local:
  `videos_generados/aprobacion/fila_2_3afd794bb30e40ea99c362a744cd5783.mp4`
* resultado:
  aprobado visualmente por Cedric;
* aprendizaje:
  los assets normalizados y la sustitución de `entrada del salón` por `cabina final grande` funcionaron.

## 3. Fila 3 rechazada

Estado actual de Sheet1 Fila 3:

* Estado:
  `Rechazado - regenerar`
* ID conservado para trazabilidad:
  `a94cb7b7d3064beaa7a57f146d8d656f`
* Motivo:
  no respeta instrucciones ni contrato visual;
* conserva `Video_preview`;
* debe regenerarse desde cero;
* no usar follow-up, repair_v1 ni Ruta B.

## 4. Experimentos descartados para producción

No utilizables:

* reparación local `repair_v1`:
  no corrigió el fallo y eliminó subtítulos;
* follow-up HeyGen:
  corrigió un fallo visual, pero añadió narración no solicitada, modificó duración y consumió 17 premium credits;
* Ruta B con `create_video_from_avatar`:
  generó avatar/voz sin Video Agent, pero la voz no se entendía correctamente ni se parecía suficientemente a Marta; consumió 18 premium credits;
* ninguno de estos métodos forma parte del flujo productivo actual.

## 5. Flujo que SÍ se utilizará para el benchmark

Usar temporalmente el flujo normal con:

* HeyGen Video Agent;
* avatar y voz actuales;
* assets solicitados por Marta;
* assets normalizados aprobados;
* validación anti-markup;
* QA humana obligatoria.

No usar durante el benchmark:

* `create_video_from_avatar`;
* follow-up como corrección principal;
* reparación local;
* API directa;
* `HEYGEN_API_KEY`;
* edición quirúrgica de vídeos rechazados.

## 6. Contrato visual acordado

### HeyGen sí debe producir

* avatar/look principal;
* voz definida;
* guion hablado exacto;
* B-roll solicitado por Marta y aprobado;
* subtítulos nativos simples;
* formato vertical 9:16.

### HeyGen no debe producir

* bandas doradas;
* cajas de texto;
* títulos grandes;
* textos decorativos;
* kinetic typography;
* doble subtítulo;
* frases adicionales;
* narración adicional;
* cierre hablado;
* otro look de Marta;
* pantallas negras;
* placeholders;
* bloques vacíos;
* logo;
* ficha final;
* outro creativo.

### Subtítulos

* simples;
* limpios;
* sincronizados;
* máximo dos líneas;
* centrados en la zona inferior;
* sin bandas, cajas ni duplicaciones.

### Logo final

Estado actual:

* el contrato visual ya está aplicado localmente en `tools/generar_video.py`;
* ese cambio todavía no está commiteado en este checkpoint;
* el logo fue retirado del `files_payload` de HeyGen;
* HeyGen no debe generar el cierre.

Después de aprobar el vídeo principal, añadir en postproducción:

* fondo negro sólido;
* logo centrado;
* aproximadamente 2 segundos;
* sin avatar;
* sin Marta al fondo;
* sin B-roll;
* sin subtítulos nuevos;
* sin texto ni narración adicional.

## 7. Benchmark acordado

Objetivo:

Generar los primeros 6 vídeos para medir el rendimiento real del flujo.

Clasificación por vídeo:

* Aprobado;
* Corrección menor;
* Rechazado.

Reglas:

* no dedicar un día completo a reparar un solo vídeo;
* máximo un intento razonable de corrección;
* si no puede corregirse de forma controlada, se regenera desde cero;
* registrar duración, video_id, consumo cuando sea medible, fallo y decisión;
* no marcar aprobado sin QA humana.

Criterio orientativo:

* 4 o más de 6 utilizables: el flujo puede continuar con QA;
* 2 o menos de 6 utilizables: replantear el motor de producción;
* 3 de 6: revisar patrones antes de decidir.

## 8. Próximo paso exacto

Después de actualizar/reiniciar Claude Code:

1. comprobar:

   * `git status --short`
   * `git log --oneline -5`
   * `claude.cmd mcp list`
2. confirmar si HeyGen sigue `✓ Connected`;
3. revisar el cambio local pendiente en `tools/generar_video.py`:

   * logo retirado de `files_payload`;
   * logo/outro/final slate prohibidos en HeyGen;
   * subtítulos simples reforzados;
4. ejecutar `py_compile`;
5. ejecutar dry-run de Fila 3;
6. revisar diff;
7. hacer commit manual desde terminal si Cedric aprueba el cambio;
8. identificar las seis filas del benchmark;
9. esperar aprobación de Cedric antes de renderizar.

## 9. Estado del repositorio

Verificación inicial:

```powershell
git status --short
git log --oneline -8
git rev-list --left-right --count origin/main...HEAD
```

Resultado registrado:

* `HEAD`: `dc6e226 docs define HeyGen controlled video generation strategy`
* `origin/main`: `4846bc1 docs add HeyGen video repair protocol`
* commits locales pendientes de push:
  2
* relación `origin/main...HEAD`:
  `0	2`

Últimos commits locales:

```text
dc6e226 docs define HeyGen controlled video generation strategy
bd3db43 guard against narrated markup in HeyGen prompts
4846bc1 docs add HeyGen video repair protocol
df4ede5 docs add HeyGen OAuth render protocol
584d6c7 replace generic salon asset with approved cabin context
86d1544 update Marta HeyGen asset ids with normalized videos
97a350e update heygen generation to respect Marta scene notes
47fd58a docs update marta june project checkpoint
```

Archivos modificados:

```text
 M tools/generar_video.py
```

Archivos no trackeados:

```text
?? tools/auditar_assets_catalog.py
?? tools/normalizar_assets_9x16.py
```

Los scripts:

* `tools/auditar_assets_catalog.py`
* `tools/normalizar_assets_9x16.py`

deben mantenerse intactos y no entrar accidentalmente en este checkpoint salvo decisión explícita.

## 10. Documentación existente relevante

Referencias:

* `CLAUDE.md`
* `docs/HEYGEN_OAUTH_PROTOCOL.md`
* `docs/HEYGEN_VIDEO_REPAIR_PROTOCOL.md`
* `docs/knowledge/HEYGEN_STACK_KB.md`
* `docs/architecture/VIDEO_GENERATION_DECISION.md`
* `docs/NEXT_STEPS_JUNIO_2026.md`
