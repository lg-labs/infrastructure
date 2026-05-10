/**
 * Kafka Dashboard SPA — fetch wrapper, hash router, error helpers.
 *
 * No build step. Loaded by index.html before alpine.min.js.
 * All app state lives in Alpine x-data; this file is plain ES modules-free.
 */

window.kd = (function () {
  // ---- API base ----
  // The gateway strips /kafka/, so from the browser we must include it.
  const API_BASE = "/kafka/api";

  // ---- Spanish messages for known error codes (design.md §7.2) ----
  const ERROR_MESSAGES = {
    invalid_topic_name:      "Nombre de topic inválido (debe empezar por 'lglabs.').",
    invalid_owner:           "Owner no válido. Selecciona uno del catálogo.",
    invalid_partitions:      "Número de particiones inválido. Solo se pueden incrementar.",
    invalid_rf:              "Replication factor inválido (debe ser ≤ número de brokers).",
    invalid_schema:          "El schema enviado es inválido o no se puede parsear.",
    invalid_compatibility_level: "Nivel de compatibilidad no válido.",
    internal_topic_protected:"Los topics internos (prefijo __ o _) no se pueden modificar.",
    topic_not_found:         "El topic no existe.",
    subject_not_found:       "El subject de schema no existe.",
    schema_version_not_found:"Esa versión del schema no existe.",
    topic_already_exists:    "Ya existe un topic con ese nombre.",
    incompatible_schema:     "El schema es incompatible con el nivel de compatibilidad configurado.",
    confirmation_required:   "Falta confirmación. Escribe el nombre exacto del recurso.",
    kafka_unavailable:       "El cluster de Kafka no responde.",
    registry_unavailable:    "El Schema Registry no responde.",
    registry_error:          "Error en el Schema Registry.",
    forbidden:               "No tienes permisos para esta acción.",
    validation_error:        "Datos inválidos en el formulario.",
    internal_error:          "Error interno del servidor.",
  };

  function humanizeError(payload, fallback) {
    if (!payload || typeof payload !== "object") return fallback || "Error desconocido";
    const code = payload.error || payload.code;
    return ERROR_MESSAGES[code] || payload.message || fallback || code || "Error desconocido";
  }

  // ---- Fetch wrapper ----
  async function call(method, path, { body, headers, raw } = {}) {
    const url = path.startsWith("/") ? `${API_BASE}${path}` : `${API_BASE}/${path}`;
    const opts = {
      method,
      headers: { Accept: "application/json", ...(headers || {}) },
      credentials: "same-origin",
    };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = typeof body === "string" ? body : JSON.stringify(body);
    }

    let resp;
    try {
      resp = await fetch(url, opts);
    } catch (e) {
      throw { status: 0, code: "network", message: "No se pudo contactar al servidor", raw: e };
    }

    // 204 No Content
    if (resp.status === 204) return null;

    if (raw) return resp;

    const text = await resp.text();
    let payload = null;
    try { payload = text ? JSON.parse(text) : null; } catch { /* not JSON */ }

    if (!resp.ok) {
      throw {
        status: resp.status,
        code: (payload && payload.error) || `http_${resp.status}`,
        message: humanizeError(payload, `Error ${resp.status}`),
        details: payload && payload.details,
        payload,
      };
    }
    return payload;
  }

  // ---- Toast notifications (simple, no framework) ----
  function toast(kind, message, ms = 4000) {
    const el = document.createElement("div");
    const colors = {
      success: "bg-green-600",
      error:   "bg-red-600",
      info:    "bg-slate-700",
      warn:    "bg-amber-600",
    };
    el.className = `fixed top-4 right-4 z-50 px-4 py-3 rounded shadow-lg text-white text-sm ${colors[kind] || colors.info}`;
    el.textContent = message;
    document.body.appendChild(el);
    setTimeout(() => el.classList.add("opacity-0", "transition-opacity", "duration-500"), ms - 400);
    setTimeout(() => el.remove(), ms);
  }

  // ---- Hash router ----
  // Routes: #/, #/topics, #/topics/<name>, #/schemas, #/schemas/<subject>
  function parseHash() {
    const h = (location.hash || "#/").slice(1);          // "/", "/topics", "/topics/lglabs.foo"
    const parts = h.split("/").filter(Boolean);
    if (parts.length === 0) return { view: "home" };
    if (parts[0] === "topics" && parts.length === 1) return { view: "topics" };
    if (parts[0] === "topics" && parts.length >= 2) return { view: "topic-detail", name: decodeURIComponent(parts.slice(1).join("/")) };
    if (parts[0] === "schemas" && parts.length === 1) return { view: "schemas" };
    if (parts[0] === "schemas" && parts.length >= 2) return { view: "schema-detail", subject: decodeURIComponent(parts.slice(1).join("/")) };
    return { view: "home" };
  }

  function navigate(path) {
    location.hash = path;
  }

  // ---- Number / date formatters ----
  function fmtMs(ms) {
    if (ms == null) return "—";
    const n = Number(ms);
    if (n >= 31_536_000_000) return `${(n / 31_536_000_000).toFixed(1)} años`;
    if (n >= 86_400_000)     return `${Math.round(n / 86_400_000)} días`;
    if (n >= 3_600_000)      return `${Math.round(n / 3_600_000)} h`;
    if (n >= 60_000)         return `${Math.round(n / 60_000)} min`;
    return `${n} ms`;
  }
  function fmtDate(s) {
    if (!s) return "—";
    try { return new Date(s).toLocaleString("es-ES"); } catch { return s; }
  }

  return {
    API_BASE,
    call,
    toast,
    parseHash,
    navigate,
    humanizeError,
    fmt: { ms: fmtMs, date: fmtDate },
  };
})();
