/**
 * Containers Dashboard SPA — fetch wrapper, hash router, error helpers.
 *
 * No build step. Loaded by index.html before alpine.min.js.
 * All app state lives in Alpine x-data; this file is plain JS, no modules.
 */

window.cd = (function () {
  // ---- API base ----
  // Gateway strips /containers/, but from the browser we must include it.
  const API_BASE = "/containers/api";

  // ---- Spanish messages for known error codes (design.md §7.2) ----
  const ERROR_MESSAGES = {
    invalid_query:               "Parámetros de consulta inválidos.",
    invalid_payload:             "Datos inválidos en la petición.",
    invalid_shell:               "El shell debe ser sh, bash o ash.",
    builtin_network_protected:   "Las redes built-in (bridge/host/none) no se pueden borrar.",
    container_not_found:         "Container no encontrado.",
    image_not_found:             "Imagen no encontrada.",
    volume_not_found:            "Volumen no encontrado.",
    network_not_found:           "Red no encontrada.",
    confirmation_required:       "Falta la confirmación. Escribe el nombre exacto del recurso.",
    container_running:           "El container está corriendo. Páralo primero o usa ?force=true.",
    already_running:              "El container ya está corriendo.",
    already_stopped:              "El container ya está parado.",
    image_in_use:                "La imagen está en uso por uno o más containers.",
    volume_in_use:               "El volumen está montado por un container.",
    network_in_use:              "La red tiene containers conectados.",
    protected_resource:          "Este recurso está protegido por la denylist del BackOffice (no se puede modificar desde aquí).",
    docker_unavailable:          "El daemon de Docker no responde.",
    forbidden:                   "No tienes permisos para esta acción.",
    validation_error:            "Datos inválidos en el formulario.",
    internal_error:              "Error interno del servidor.",
    network:                     "No se pudo contactar al servidor.",
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
      throw { status: 0, code: "network", message: ERROR_MESSAGES.network, raw: e };
    }

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

  // ---- Toast notifications ----
  function toast(kind, message, ms = 4500) {
    const el = document.createElement("div");
    const colors = {
      success: "bg-green-600",
      error:   "bg-red-600",
      info:    "bg-slate-700",
      warn:    "bg-amber-600",
    };
    el.className = `fixed top-4 right-4 z-50 px-4 py-3 rounded shadow-lg text-white text-sm max-w-md ${colors[kind] || colors.info}`;
    el.textContent = message;
    document.body.appendChild(el);
    setTimeout(() => el.classList.add("opacity-0", "transition-opacity", "duration-500"), ms - 400);
    setTimeout(() => el.remove(), ms);
  }

  // ---- Hash router ----
  // Routes:
  //   #/                         home (summary)
  //   #/containers               containers list
  //   #/containers/<id>          container detail (default tab: overview)
  //   #/containers/<id>/<tab>    container detail with tab (overview|logs|stats|inspect)
  //   #/                          projects list (landing — Phase I)
  //   #/projects/<name>           project detail (Phase I) — tabs: overview|topology|networks|volumes
  //   #/home                      daemon home/summary
  //   #/containers                containers list
  //   #/containers/<id>           container detail (tabs: overview|logs|stats|inspect)
  //   #/containers/<id>/exec      exec shell (admin)
  //   #/images                    images list
  //   #/volumes                   volumes list
  //   #/networks                  networks list
  function parseHash() {
    const h = (location.hash || "#/").slice(1);
    const parts = h.split("/").filter(Boolean);
    if (parts.length === 0) return { view: "home" };
    if (parts[0] === "home") return { view: "home" };
    if (parts[0] === "projects" && parts.length === 1) return { view: "projects" };
    if (parts[0] === "projects" && parts.length >= 2) {
      const name = decodeURIComponent(parts[1]);
      const allowed = ["overview", "topology", "networks", "volumes"];
      const tab = (parts[2] && allowed.includes(parts[2])) ? parts[2] : "topology";
      return { view: "project-detail", name, tab };
    }
    if (parts[0] === "containers" && parts.length === 1) return { view: "containers" };
    if (parts[0] === "containers" && parts.length >= 2) {
      const id = decodeURIComponent(parts[1]);
      // Exec is its own top-level view, not a tab (it owns the full body).
      if (parts[2] === "exec") return { view: "container-exec", id };
      const tab = (parts[2] && ["overview", "logs", "stats", "inspect"].includes(parts[2])) ? parts[2] : "overview";
      return { view: "container-detail", id, tab };
    }
    if (parts[0] === "images")   return { view: "images" };
    if (parts[0] === "volumes")  return { view: "volumes" };
    if (parts[0] === "networks") return { view: "networks" };
    return { view: "home" };
  }

  function navigate(path) {
    location.hash = path;
  }

  // ---- Formatters ----
  function fmtBytes(n) {
    if (n == null) return "—";
    const b = Number(n);
    if (Number.isNaN(b)) return "—";
    if (b < 1024)              return `${b} B`;
    if (b < 1024 ** 2)         return `${(b / 1024).toFixed(1)} KB`;
    if (b < 1024 ** 3)         return `${(b / 1024 ** 2).toFixed(1)} MB`;
    return `${(b / 1024 ** 3).toFixed(2)} GB`;
  }
  function fmtMb(mb) {
    if (mb == null) return "—";
    const m = Number(mb);
    if (Number.isNaN(m)) return "—";
    if (m < 1024) return `${m.toFixed(1)} MB`;
    return `${(m / 1024).toFixed(2)} GB`;
  }
  function fmtDate(s) {
    if (!s) return "—";
    try { return new Date(s).toLocaleString("es-ES"); } catch { return s; }
  }
  function fmtPct(p) {
    if (p == null) return "—";
    return `${Number(p).toFixed(1)}%`;
  }

  return {
    API_BASE,
    call,
    toast,
    parseHash,
    navigate,
    humanizeError,
    fmt: { bytes: fmtBytes, mb: fmtMb, date: fmtDate, pct: fmtPct },
  };
})();
