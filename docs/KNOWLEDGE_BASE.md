# Base de conocimiento - Marta Sune

Fecha de referencia: 2026-06-19

## Vector Store actual

- Nombre: `Marta Sune ClonIA (Estilista)`.
- Proposito: base de conocimiento para el agente de DMs de Marta Estetica.
- Uso actual: OpenAI Responses API con herramienta `file_search`.
- Estado: `completed`.
- Fecha aproximada de creacion: `2026-04-23T16:31:36Z`.
- Archivos indexados: 11.
- Archivos fallidos: 0.
- Metadatos visibles: no hay metadatos de version o vigencia.

## Alcance

El Vector Store contiene informacion orientada a responder consultas de clientes sobre tratamientos, precios, preguntas frecuentes, contacto, recomendaciones y reservas. No debe usarse como repositorio tecnico interno ni como CRM.

## Inventario de archivos cargados

Informacion confirmada:

- El Vector Store existe, esta en estado `completed` y tiene 11 archivos indexados.
- Los 11 archivos listados abajo estaban asociados al Vector Store en la auditoria.
- No se detectaron archivos fallidos.

Informacion inferida por nombre del archivo:

- La categoria de cada documento se deduce por filename y por senales de busqueda, no por validacion editorial completa.
- La columna `notes` puede indicar proposito aparente, no aprobacion final de contenido.

Datos pendientes de validacion con Marta:

- Propietario real de cada fuente.
- Version.
- Fecha efectiva.
- Vigencia de precios, horarios, contacto y politicas.
- Si cada fuente debe seguir activa o archivarse.

| filename | category | source_owner | version | effective_date | review_status | public_or_internal | active_or_archived | notes |
|---|---|---|---|---|---|---|---|---|
| `botox_capilar.md` | Tratamiento capilar / correccion de criterio | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | Revisar antes de tocar Vector Store | Publico para clientes | Activo con riesgo | Posible solapamiento con `Tratamiento Botox.pdf`; contiene criterio seguro sobre frizz/encrespado. |
| `Foto Rejuvenecimiento..pdf` | Tratamiento estetico | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | Pendiente revision de vigencia | Publico para clientes | Activo provisional | Documento de fotorejuvenecimiento; revisar fecha, precios y contraindicaciones. |
| `DIRECCIÓN.pdf` | Contacto / ubicacion | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | Pendiente revision de vigencia | Publico para clientes | Activo provisional | Validar direccion, web, telefono, WhatsApp y horario. |
| `LISTA DE PRECIOS – MARTHA SUÑÉ (FORMATO TEXTO).pdf` | Precios / tarifas | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | Pendiente revision prioritaria | Publico para clientes | Activo provisional | Riesgo alto si las tarifas no estan actualizadas; requiere fecha efectiva. |
| `Tratamiento Botox.pdf` | Tratamiento Botox | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | Revisar antes de tocar Vector Store | Publico para clientes | Activo con riesgo | Posible solapamiento o contradiccion con `botox_capilar.md`; revisar alcance: capilar, estetico o ambos. |
| `HAYFU.pdf` | Tratamiento HIFU / HAYFU | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | Pendiente revision de vigencia | Publico para clientes | Activo provisional | Normalizar nombre si corresponde a HIFU; revisar precios, duracion y recomendaciones. |
| `Maderoterapia.pdf` | Tratamiento corporal | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | Pendiente revision de vigencia | Publico para clientes | Activo provisional | Revisar sesiones, recomendaciones, contraindicaciones y precios. |
| `FAQ–MARTHASUÑÉ(LISTOPARAIA).docx` | FAQ general | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | Pendiente revision de vigencia | Publico para clientes | Activo provisional | Fuente general de preguntas frecuentes; revisar si contiene reservas, horarios o criterios antiguos. |
| `Tratamiento Criolipolisis.pdf` | Tratamiento corporal | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | Pendiente revision de vigencia | Publico para clientes | Activo provisional | Revisar recomendaciones, resultados esperables, contraindicaciones y precios. |
| `Drenaje Linfatico.pdf` | Tratamiento corporal | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | Pendiente revision de vigencia | Publico para clientes | Activo provisional | Revisar beneficios, casos no adecuados y precios. |
| `Tratamiento EM Slim.pdf` | Tratamiento corporal | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | PENDIENTE DE VALIDACION | Pendiente revision de vigencia | Publico para clientes | Activo provisional | Revisar descripcion, numero de sesiones, expectativas y precios. |

## Riesgos por tipo de informacion

- Tratamientos: cubiertos parcialmente, pero sin version formal.
- Precios: cubiertos por una lista de precios, con riesgo alto si no esta fechada.
- Preguntas frecuentes: cubiertas por FAQ, pendiente revisar vigencia.
- Horarios: aparecen en prompt y probablemente en FAQ/contacto, pero requieren fuente fechada.
- Reservas: el codigo deriva a WhatsApp, pero la base debe evitar textos que sugieran agenda disponible.
- Politicas: no hay documento claro de cancelaciones, privacidad o condiciones.
- Contacto: cubierto parcialmente, pendiente validacion de vigencia.
- Recomendaciones: cubiertas por documentos de tratamientos, pendiente revision.
- Documentos internos: no detectados por nombre, pendiente auditoria de contenido completo si se necesita certeza.
- Contratos / informacion economica privada: no detectados por nombre, pendiente verificacion de contenido si se requiere.
- Documentacion tecnica: no debe estar en este Vector Store.

Faltan o deben validarse expresamente:

- Politica de reservas.
- Politica de cancelacion.
- Horarios vigentes.
- Contacto vigente.
- Precios vigentes.
- Fechas efectivas.
- Versiones.
- Metadatos de vigencia.

## Solapamiento Botox

Antes de modificar el Vector Store hay que revisar conjuntamente:

- `botox_capilar.md`.
- `Tratamiento Botox.pdf`.

Objetivo de revision:

1. Confirmar si ambos hablan del mismo tratamiento.
2. Confirmar si uno reemplaza al otro.
3. Confirmar si existe contradiccion sobre frizz, encrespado, alisado o resultados garantizados.
4. Definir cual queda activo.
5. Archivar o retirar la fuente antigua solo cuando la fuente nueva este validada e indexada.

## Proceso futuro de actualizacion

1. Validar contenido con Marta.
2. Asignar version y fecha.
3. Identificar documento reemplazado.
4. Subir nueva fuente.
5. Verificar indexacion.
6. Retirar fuente antigua.
7. Realizar prueba controlada.
8. Registrar el cambio en este documento.

## Registro minimo por cambio futuro

Cada cambio de conocimiento deberia registrar:

- Fecha.
- Responsable.
- Documento nuevo.
- Documento reemplazado.
- Motivo.
- Version.
- Fecha efectiva.
- Resultado de indexacion.
- Prueba controlada realizada.
- Riesgos residuales.
