# Checkpoint comentarios Instagram - 2026-06-18

## 1. Fecha de validacion

El modulo de comentarios publicos de Instagram fue validado en produccion el
18 de junio de 2026.

## 2. Commit de referencia

Commit desplegado y usado como referencia funcional:

```text
38b1bff refine Instagram comment reply texts
```

## 3. Configuracion funcional

Configuracion confirmada durante la prueba real:

```text
INSTAGRAM_COMMENTS_ENABLED=true
INSTAGRAM_COMMENTS_DRY_RUN=false
comments_can_publish=True
```

Cuenta validada:

```text
martasunestilista
```

## 4. Evidencias de PostgreSQL

Registro publicado:

```text
comment_id: 18372292816224134
media_id: 18008838571127505
classification: felicitacion
response_text: Muchas gracias. Nos alegra mucho que te guste.
status: published
updated_at: 2026-06-18 19:16:42 UTC
```

Registro anti-bucle:

```text
comment_id: 18065988569438293
media_id: 18008838571127505
status: ignored_own_account
updated_at: 2026-06-18 19:16:44 UTC
```

## 5. Evidencias de logs

Logs operativos confirmados durante la validacion:

```text
Comentario respondido publicamente -> comment_id=18372292816224134 classification=felicitacion
Comentario propio ignorado -> comment_id=18065988569438293
```

No hubo error de Graph API en la respuesta publica y el comentario de prueba no
fue tratado como duplicado.

## 6. Confirmacion visual

La respuesta publica fue comprobada visualmente en Instagram en la cuenta
`martasunestilista`.

El segundo webhook correspondio a la respuesta publicada por la propia cuenta.
El resultado `ignored_own_account` evito correctamente el bucle.

## 7. Conclusion

El flujo webhook -> clasificacion -> respuesta publica -> persistencia
PostgreSQL -> anti-bucle esta validado de extremo a extremo.

No requiere mas cambios salvo que aparezca un fallo nuevo reproducible.

## 8. Proximo bloque del proyecto

El siguiente bloque del proyecto es el benchmark de seis videos distintos.

Antes de generar o regenerar videos:

- revisar el checkpoint de video activo;
- revisar el catalogo de assets;
- revisar las seis piezas candidatas;
- ejecutar dry-runs antes de gastar creditos;
- no continuar regenerando obsesivamente la Fila 3.

## 9. Regla de continuidad

No volver a modificar el modulo de comentarios salvo fallo nuevo reproducible.
