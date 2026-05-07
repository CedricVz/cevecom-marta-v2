# Módulo 0 — Generador de calendario mensual

## Qué hace

Genera 12 propuestas de Reels para el mes siguiente usando Claude, las muestra para revisión y las escribe en Google Sheets con `Estado="Pendiente"` para que el Módulo 1 las procese automáticamente.

---

## Cuándo ejecutarlo

**Una vez al mes**, la última semana del mes en curso. Ejemplo: el 25 de mayo para planificar junio.

---

## Cómo ejecutarlo

### Caso básico (mes siguiente por defecto)
```powershell
python tools/generar_calendario.py
```

### Especificando mes y año
```powershell
python tools/generar_calendario.py --mes 6 --anyo 2026
```

### Evitando repetir temas anteriores
```powershell
python tools/generar_calendario.py --mes 6 --anyo 2026 --publicados temas_anteriores.json
```

El archivo `--publicados` debe ser un JSON con una lista de strings:
```json
["¿Por qué tu piel pierde luminosidad con la edad?", "El secreto para una piel perfecta sin filtros"]
```

---

## Flujo interactivo

1. El script genera las 12 propuestas y las muestra en pantalla.
2. Se pide confirmación: `¿Apruebas este calendario y lo escribes en Sheets? [s/N]`
3. **Si respondes `s`**: las 12 filas se escriben en Sheets con `Estado=Pendiente`.
4. **Si respondes `N`** (o cualquier otra cosa): no se escribe nada. Puedes volver a ejecutar para obtener nuevas propuestas.

---

## Ajustes después de aprobar

Si quieres cambiar algún tema después de aprobar:

1. Abre Google Sheets directamente.
2. Edita los campos `Tema`, `Tratamiento`, `Audiencia`, `Tono` o `Fecha_deseada` de las filas con `Estado=Pendiente`.
3. El Módulo 1 leerá los valores actualizados en su próxima ejecución.

---

## Qué genera en Sheets

Cada fila incluye:

| Campo | Valor |
|---|---|
| `Tema` | Título gancho del Reel |
| `Tratamiento` | Servicio del centro |
| `Audiencia` | Público objetivo |
| `Tono` | Tono narrativo |
| `Look_ID` | `97175217da0f41edb57bd1aecd543792` (avatar fijo) |
| `Fecha_deseada` | Fecha de publicación sugerida |
| `Estado` | `Pendiente` |

El resto de columnas (`Guion`, `Video_preview`, `Estado`, etc.) las rellena el Módulo 1.

---

## Flujo mensual completo

```
[~25 del mes anterior]
python tools/generar_calendario.py --mes X --anyo YYYY
  → Marta/Cedric revisan y aprueban
  → 12 filas en Sheets con Estado=Pendiente

[Días siguientes — pipeline diario o manual]
cmd /c "python tools\leer_pendientes.py | python tools\generar_guion.py | python tools\generar_video.py | python tools\enviar_aprobacion.py"
  → Para cada fila Pendiente: genera guión → vídeo → email a Marta

[Marta aprueba en el email]
  → Estado cambia a Aprobado

[Publicación]
python tools/publicar_instagram.py
  → Publica los vídeos aprobados en Instagram
```

---

## Errores comunes

| Error | Causa | Solución |
|---|---|---|
| `ANTHROPIC_API_KEY` faltante | No está en `.env` | Añadir la clave de console.anthropic.com |
| `SpreadsheetNotFound` | ID de Sheets incorrecto o sin acceso | Verificar `GOOGLE_SHEETS_ID` y permisos de la service account |
| `Claude no devolvió un array JSON válido` | Respuesta inesperada de Claude | Volver a ejecutar |
| Token OAuth de HeyGen expirado | Solo afecta al Módulo 1, no a este script | Abrir Claude Code para renovarlo |
