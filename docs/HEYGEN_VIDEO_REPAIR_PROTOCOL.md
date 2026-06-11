# Protocolo de QA y corrección de vídeos HeyGen

## Principio

La fuente de verdad para revisión no es el editor interno de HeyGen, sino el MP4 final exportado.

Toda corrección debe partir del archivo final que Marta o Cedric han revisado visualmente. El editor interno, la sesión de HeyGen o el prompt sirven como contexto técnico, pero la aprobación o el rechazo se decide sobre el MP4 exportado.

## Recepción de feedback de Marta

El objetivo del feedback es identificar exactamente qué corregir, dónde ocurre y si el fallo se puede reparar localmente o requiere regeneración en HeyGen.

### A) Vía rápida por email o WhatsApp

Formato obligatorio:

```text
Vídeo / Fila:
Link del vídeo:
Minuto o segundo exacto:
Qué ves mal:
Qué debería aparecer:
Prioridad:
¿Aprobarías el vídeo si corregimos solo eso? Sí/No
```

Esta vía sirve para incidencias urgentes o revisiones rápidas, siempre que Marta indique un timestamp concreto.

### B) Vía profesional con Google Form

Campos propuestos:

```text
Nombre de la persona que revisa
Vídeo / Fila
Link del vídeo
¿Apruebas el vídeo?
Timestamp del problema
Descripción del fallo
Tipo de fallo
Asset sugerido o referencia visual
Prioridad
Comentarios extra
Captura opcional
```

Nombre recomendado de hoja o pestaña:

```text
QA_Correcciones_Videos
```

## Tipos de fallo

```text
bloque negro
asset incorrecto
asset ausente
corte visual
subtítulo/texto
logo/cierre
voz/audio
avatar/lipsync
guion incorrecto
otro
```

## Estados de seguimiento

```text
Recibido
Clasificado
Reparable localmente
Necesita regeneración HeyGen
Repair_v1 creado
Enviado a revisión
Aprobado
Rechazado
```

## Criterio de decisión

Si el fallo es visual puntual y el audio está bien, intentar reparación local.

Ejemplos:

```text
bloque negro breve
asset ausente en un tramo concreto
corte visual puntual
plano de apoyo reemplazable
logo/cierre corregible por postproducción
```

Si falla avatar, voz, lipsync, guion o estructura completa, regenerar solo esa fila en HeyGen.

Ejemplos:

```text
avatar mal sincronizado
voz incorrecta
guion incompleto o cambiado
orden narrativo roto
subtítulos nativos imposibles de corregir localmente
fallo visual extendido en muchas escenas
```

## Flujo recomendado

1. Recibir feedback con timestamp.
2. Clasificar tipo de fallo.
3. Revisar el MP4 final exportado.
4. Decidir si es reparación local o regeneración HeyGen.
5. Guardar versión original antes de editar.
6. Crear `repair_v1` si aplica.
7. Enviar `repair_v1` a revisión.
8. Si `repair_v1` no resuelve el problema, preparar regeneración controlada solo de esa fila.

## Convención de archivos

```text
videos_generados/aprobacion/fila_<n>_<video_id>_original.mp4
videos_generados/reparaciones/fila_<n>_<video_id>_repair_v1.mp4
videos_generados/regenerados/fila_<n>_<nuevo_video_id>_regenerated_v2.mp4
```

No sobrescribir el MP4 aprobado o rechazado. Cada intento debe conservar trazabilidad.
