# Containers Dashboard

Microfrontend del BackOffice (`/containers/`) para gestionar el **daemon Docker del host**:

- Containers, images, volumes, networks
- Logs/stats live
- Exec shell (admin)
- Remove (admin)

Todo bajo **SSO + roles** del BackOffice y **audit** a `backoffice-audit-*`.

## Projects view (Phase I)

Descubre **Compose stacks** vía labels y renderiza un **diagrama de topología** con **Mermaid** (services, depends_on, networks, volumes).

## Arrancar

```bash
make backoffice-up   # incluye containers-dashboard
```

## Acceso

- **URL**: <http://localhost:8080/containers/>
- Usuarios: los [4 usuarios seed del BackOffice](./index.md#usuarios-seed-uno-por-rol)
- Coexiste con Portainer en `/portainer/`.

::: warning Seguridad
El BFF tiene `docker.sock:rw` (mismo nivel que Portainer); mitigado vía **denylist + RBAC + audit**.
:::

::: warning Requisitos previos
Requiere `make elk-up` previamente.
:::

## Detener / Destruir

```bash
make backoffice-down    # detiene junto al BackOffice
make backoffice-clean   # destruye backoffice-containers-dashboard-data
```
