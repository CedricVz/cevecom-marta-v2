/**
 * aprobacion_webhook.gs — Webhook de aprobación de Reels para Cevecom Marta
 *
 * ── CÓMO DESPLEGARLO (una sola vez) ─────────────────────────────────────────
 *
 *  1. Ve a https://script.google.com → "Nuevo proyecto"
 *  2. Borra el contenido vacío y pega TODO este archivo.
 *  3. Menú: Implementar → Nueva implementación
 *       - Tipo:              Aplicación web
 *       - Descripción:       v1
 *       - Ejecutar como:     Yo  (la cuenta que tiene acceso a la hoja)
 *       - Quién tiene acceso: Cualquier persona
 *  4. Pulsa "Implementar" → copia la URL que aparece.
 *  5. Pega esa URL en .env como APPS_SCRIPT_WEBHOOK_URL
 *
 * ── FLUJO ────────────────────────────────────────────────────────────────────
 *
 *  Email → [Sí, publicar]  → doGet?token=...&decision=aprobado
 *                            → Estado = "Aprobado"  → página de confirmación
 *
 *  Email → [No, rechazar]  → doGet?token=...&decision=rechazado
 *                            → Estado = "Rechazado" → página con form de motivo
 *                            → [Enviar motivo]
 *                            → doGet?token=...&accion=motivo&motivo=...
 *                            → Motivo_rechazo = "..."
 *
 *  publicar_instagram.py lee periódicamente las filas con Estado = "Aprobado"
 *  y las publica en Instagram.
 */

// ── Configuración ─────────────────────────────────────────────────────────────

const SHEET_ID = "1XRpSXCTzNKFpK-clG8KYWLQ_9KK9DrLUzujH0VQM21A"; // = GOOGLE_SHEETS_ID del .env

// Índices 0-based en el array de getValues() (fila de datos, sin cabecera)
const I_TEMA   = 0;   // "Tema"
const I_ESTADO = 6;   // "Estado"
const I_TOKEN  = 15;  // "Token_aprobacion"

// Columnas 1-based para getRange(fila, col)
const COL_ESTADO   = 7;   // "Estado"
const COL_DECISION = 12;  // "Decision"
const COL_MOTIVO   = 13;  // "Motivo_rechazo"


// ── Punto de entrada ──────────────────────────────────────────────────────────

function doGet(e) {
  const token    = (e.parameter.token    || "").trim();
  const decision = (e.parameter.decision || "").trim();
  const accion   = (e.parameter.accion   || "").trim();

  if (!token) {
    return _pagina(paginaError("Enlace inválido: falta el token."));
  }

  const hoja  = SpreadsheetApp.openById(SHEET_ID).getSheets()[0];
  const datos = hoja.getDataRange().getValues();

  // Buscar la fila con este token (i=0 son cabeceras, datos reales desde i=1)
  let fila = -1;
  for (let i = 1; i < datos.length; i++) {
    if (String(datos[i][I_TOKEN]).trim() === token) {
      fila = i + 1; // 1-based para getRange
      break;
    }
  }

  if (fila === -1) {
    return _pagina(paginaError(
      "Token no encontrado. Es posible que ya hayas tomado una decisión para este Reel."
    ));
  }

  const tema         = String(datos[fila - 1][I_TEMA]);
  const estadoActual = String(datos[fila - 1][I_ESTADO]).trim();

  // ── Paso 2: guardar motivo de rechazo (opcional) ─────────────────────────
  if (accion === "motivo") {
    const motivo = (e.parameter.motivo || "").trim().substring(0, 500);
    if (motivo && estadoActual === "Rechazado") {
      hoja.getRange(fila, COL_MOTIVO).setValue(motivo);
    }
    return _pagina(paginaMotivo(tema));
  }

  // ── Paso 1: registrar la decisión ────────────────────────────────────────
  if (!["aprobado", "rechazado"].includes(decision)) {
    return _pagina(paginaError("Parámetro 'decision' inválido."));
  }

  // Idempotencia: si ya se respondió, no modificar nada
  if (estadoActual === "Aprobado" || estadoActual === "Rechazado") {
    return _pagina(paginaYaRespondida(tema, estadoActual));
  }

  if (decision === "aprobado") {
    hoja.getRange(fila, COL_ESTADO).setValue("Aprobado");
    hoja.getRange(fila, COL_DECISION).setValue("Aprobado");
    return _pagina(paginaAprobado(tema));
  }

  // Rechazado: marcar + mostrar formulario de motivo
  hoja.getRange(fila, COL_ESTADO).setValue("Rechazado");
  hoja.getRange(fila, COL_DECISION).setValue("Rechazado");
  return _pagina(paginaRechazado(tema, token));
}


// ── Páginas HTML ──────────────────────────────────────────────────────────────

function _pagina(html) {
  return HtmlService
    .createHtmlOutput(html)
    .setTitle("Cevecom Marta — Aprobación de Reels")
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

function _base(icono, colorCabecera, titulo, cuerpo) {
  return `<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: Arial, Helvetica, sans-serif;
      background: #f2f2f2;
      display: flex;
      min-height: 100vh;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .card {
      background: #fff;
      border-radius: 10px;
      box-shadow: 0 2px 14px rgba(0,0,0,.1);
      max-width: 460px;
      width: 100%;
      overflow: hidden;
    }
    .cabecera {
      background: ${colorCabecera};
      padding: 30px 28px 26px;
      text-align: center;
    }
    .icono  { font-size: 52px; margin-bottom: 10px; }
    .titulo { color: #fff; font-size: 20px; font-weight: 700; }
    .cuerpo { padding: 28px; }
    .tema {
      background: #f8f9fa;
      border-radius: 6px;
      padding: 14px 16px;
      margin-bottom: 20px;
      color: #1a1a2e;
      font-size: 15px;
      font-weight: 700;
    }
    .msg { color: #555; font-size: 14px; line-height: 1.65; }
    textarea {
      width: 100%;
      border: 1px solid #ddd;
      border-radius: 6px;
      padding: 12px;
      font-size: 14px;
      font-family: inherit;
      resize: vertical;
      margin: 16px 0 12px;
    }
    .btn {
      display: block;
      width: 100%;
      padding: 13px;
      background: #0055cc;
      color: #fff;
      font-size: 15px;
      font-weight: 700;
      border: none;
      border-radius: 6px;
      cursor: pointer;
    }
    .pie {
      padding: 14px 28px;
      background: #f8f9fa;
      border-top: 1px solid #eee;
      text-align: center;
      color: #bbb;
      font-size: 11px;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="cabecera">
      <div class="icono">${icono}</div>
      <div class="titulo">${titulo}</div>
    </div>
    <div class="cuerpo">${cuerpo}</div>
    <div class="pie">Cevecom Marta · Sistema automatizado de contenido</div>
  </div>
</body>
</html>`;
}

function paginaAprobado(tema) {
  return _base(
    "✅", "#28a745", "¡Reel aprobado!",
    `<div class="tema">${tema}</div>
     <p class="msg">
       Perfecto. El vídeo se publicará en Instagram automáticamente.<br><br>
       Recibirás la URL de la publicación cuando esté en el aire.
     </p>`
  );
}

function paginaRechazado(tema, token) {
  const urlBase = ScriptApp.getService().getUrl();
  return _base(
    "❌", "#dc3545", "Reel rechazado",
    `<div class="tema">${tema}</div>
     <p class="msg">
       Hemos registrado que no apruebas este Reel.<br><br>
       Si quieres indicar el motivo para que podamos mejorarlo, escríbelo aquí
       (opcional):
     </p>
     <form action="${urlBase}" method="get">
       <input type="hidden" name="token"  value="${token}">
       <input type="hidden" name="accion" value="motivo">
       <textarea name="motivo" rows="4"
         placeholder="Ej: El gancho no engancha, quiero un enfoque más directo al problema…"
       ></textarea>
       <button type="submit" class="btn">Enviar motivo</button>
     </form>`
  );
}

function paginaMotivo(tema) {
  return _base(
    "📝", "#6c757d", "Motivo registrado",
    `<div class="tema">${tema}</div>
     <p class="msg">
       Gracias. Hemos guardado el motivo del rechazo para mejorar el próximo Reel.
     </p>`
  );
}

function paginaYaRespondida(tema, estado) {
  const emoji = estado === "Aprobado" ? "✅" : "❌";
  return _base(
    emoji, "#6c757d", "Ya respondiste",
    `<div class="tema">${tema}</div>
     <p class="msg">
       Ya habías marcado este Reel como <strong>${estado}</strong>.<br>
       No se ha modificado nada.
     </p>`
  );
}

function paginaError(mensaje) {
  return _base(
    "⚠️", "#e0a800", "Algo ha ido mal",
    `<p class="msg">${mensaje}</p>`
  );
}
