# Next Steps — Junio 2026

Documento operativo tras la reunión con Marta. No sustituye al código ni a Sheets; sirve para ordenar decisiones antes de tocar producción.

## Prioridad técnica

1. Corregir agente de DMs para no dar citas fantasma.
   - No confirmar disponibilidad.
   - No inventar horarios.
   - Derivar reservas a WhatsApp: `656 376 435`.
   - Respuesta base: “Para reservar cita, escríbenos por WhatsApp al 656 376 435 y Marta o el equipo te ayudan directamente.”

2. Actualizar vector/conocimiento sobre Botox capilar.
   - Añadir criterio correcto de Marta.
   - No prometer eliminación total de encrespado/frizz.
   - Revisar si requiere nuevos documentos en OpenAI/vector store.

3. Auditar assets Drive → metadata técnica → HeyGen `asset_id`.
   - Reconciliar archivo real en Drive.
   - Revisar metadata real: width, height, SAR, DAR, rotation, duration, codec.
   - Confirmar si el `asset_id` de HeyGen corresponde al archivo actual o a una subida antigua.

4. Clasificar assets seguros/problemáticos.
   - `portrait_real_seguro`: vertical real, SAR 1:1, sin rotación problemática.
   - `portrait_por_metadata`: se ve vertical por rotación/SAR/DAR, pero es riesgoso para HeyGen.
   - `landscape_real`: requiere reencuadre o versión Canva/ffmpeg.
   - `desconocido`: no verificable aún.

5. Preparar workflow Canva o ffmpeg solo para assets problemáticos.
   - No convertir todo a ciegas.
   - Usar normalización técnica sin cambio visual cuando el problema sea metadata.
   - Usar Canva/reencuadre manual solo si el contenido es realmente landscape o el crop automático corta información importante.

6. Subir assets portrait/normalizados y obtener nuevos `asset_id` solo cuando corresponda.
   - No reemplazar IDs hasta tener revisión visual.
   - Guardar trazabilidad: label original, Drive URL, asset_id antiguo, asset_id nuevo, estrategia usada.

7. Actualizar `ASSET_CATALOG`.
   - Añadir metadata mínima útil: width, height, SAR, DAR, rotation, duration, orientation_status, source_url, heygen_asset_id, fecha de revisión.
   - Mantener keywords y labels estables para no romper selección de B-roll.

8. Generar próximos vídeos respetando guion y notas de Marta.
   - Usar dry-run assets y prompt antes de gastar créditos.
   - No ejecutar pipeline completo sin seleccionar filas explícitas.

9. Crear knowledge base técnica.
   - Estructura propuesta:
     - `docs/knowledge/README.md`
     - `docs/knowledge/HEYGEN.md`
     - `docs/knowledge/META.md`
     - `docs/knowledge/OPENAI.md`
     - `docs/knowledge/RAILWAY.md`
     - `docs/knowledge/GOOGLE_SHEETS.md`
     - `docs/knowledge/CANVA_ASSETS.md`
   - Cada archivo debe incluir: fuentes oficiales, uso en este proyecto, decisiones, errores aprendidos, comandos útiles, fecha de última revisión y mantenimiento.

10. Preparar propuesta de renovación 6 meses.
    - Mantenimiento del sistema.
    - Mejora continua del agente.
    - Actualización de knowledge base.
    - Generación de contenidos.
    - Soporte mensual.
    - Optimización del flujo de reservas y DMs.

## Reglas de seguridad actuales

- No generar vídeos HeyGen sin dry-run aprobado.
- No enviar emails de aprobación hasta revisión visual.
- No publicar automáticamente.
- No ejecutar pipeline completo.
- No actualizar `Guiones_Marta` sin instrucción explícita.
- No hacer commit hasta revisión.
