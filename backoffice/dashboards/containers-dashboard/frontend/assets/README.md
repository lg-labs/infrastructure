# frontend/assets — vendored libraries

Sin build step. Todas las libs se sirven directas desde nginx.

| Archivo | Versión | Origen | SHA-256 (head) | Notas |
|---|---|---|---|---|
| `alpine.min.js` | 3.14.x | `https://unpkg.com/alpinejs@3` | — | reactivity layer |
| `tailwind.min.js` | 3.4.x | `https://cdn.tailwindcss.com` | — | Tailwind JIT (browser) |
| `xterm.js` + `xterm.css` | 5.3.0 | `https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/` | — | terminal emulator (exec WS) |
| `xterm-addon-fit.js` | 0.8.0 | `https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/` | — | resize addon |
| `app.js` + `app.css` | local | — | — | helpers + styling overrides |
| `mermaid.min.js` | **10.9.4** | `https://cdn.jsdelivr.net/npm/mermaid@10.9.4/dist/mermaid.min.js` | `1360dfc1fbdbf83466b8c49c778c17a23bbb15718c176356a7f4d2c95c54da07` | **Phase I** — diagramas de componentes en `/projects/<name>/topology` |

## Re-vendorear Mermaid

```bash
cd backoffice/dashboards/containers-dashboard
curl -sL https://cdn.jsdelivr.net/npm/mermaid@10.9.4/dist/mermaid.min.js \
     -o frontend/assets/mermaid.min.js
shasum -a 256 frontend/assets/mermaid.min.js   # verificar contra el SHA arriba
```

## Caché

`frontend/nginx.conf` aplica `expires 7d` a `/containers/assets/*` y `Cache-Control: public, immutable` para que el cliente no re-descargue Mermaid (≈3 MB) en cada navegación.
