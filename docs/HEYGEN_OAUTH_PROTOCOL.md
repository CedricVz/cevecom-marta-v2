# Protocolo OAuth HeyGen MCP

## Conceptos separados

El plan, la cuenta y los créditos de HeyGen indican si la cuenta puede generar vídeos y consumir créditos.

El OAuth MCP de Claude Code/Codex es la autorización local que permite a los scripts llamar a las herramientas MCP de HeyGen desde este entorno.

Un plan activo de HeyGen no garantiza que el token OAuth MCP esté vigente. Puede haber créditos disponibles y, aun así, fallar el render con un error de autenticación local.

## Protocolo antes de cada render

1. Comprobar estado MCP:

   ```cmd
   claude.cmd mcp list
   ```

2. Comprobar el servidor HeyGen:

   ```cmd
   claude.cmd mcp get heygen
   ```

3. Confirmar que HeyGen aparece como:

   ```text
   ✓ Connected
   ```

4. Confirmar que el lector local del proyecto acepta el OAuth:

   ```powershell
   $env:PYTHONIOENCODING = 'utf-8'
   @'
   from tools.generar_video import _leer_token_oauth_heygen
   _leer_token_oauth_heygen()
   print("HEYGEN_OAUTH_OK")
   '@ | python -
   ```

5. Ejecutar dry-run de la fila objetivo.

6. Renderizar solo la fila objetivo, nunca el lote completo si se está haciendo una prueba controlada.

7. Descargar el MP4 inmediatamente cuando haya `Video_preview` aprobado.

## Si aparece un error OAuth

Errores habituales:

```text
Token OAuth de HeyGen expirado
```

```text
Needs authentication
```

Qué hacer:

1. Parar renders.
2. No tocar código.
3. Renovar OAuth en Claude Code.
4. Verificar de nuevo:

   ```cmd
   claude.cmd mcp list
   claude.cmd mcp get heygen
   ```

5. Confirmar:

   ```text
   HEYGEN_OAUTH_OK
   ```

6. Reintentar la misma fila explícitamente.

7. Registrar y revisar el resultado.

## Timeout local durante render

Si un comando local agota timeout pero Sheet1 queda actualizado con `ID_heygen` y `Video_preview`, revisar la fila antes de repetir.

No relanzar el render sin comprobar la fila, porque podría duplicar consumo de créditos.

## URLs de preview

Las URLs `Video_preview` de HeyGen son firmadas y pueden caducar.

Cuando un vídeo esté aprobado visualmente, descargar el MP4 inmediatamente y guardarlo en una ruta local trazable, por ejemplo:

```text
videos_generados/aprobacion/fila_2_<video_id>.mp4
```
