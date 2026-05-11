# BackOffice

Una sola URL con **SSO sobre Keycloak** para administrar Kafka (AKHQ), contenedores (Portainer), logs (Kibana) y el propio Keycloak Admin. Audit log automático hacia ELK.

## Arrancar

```bash
make backoffice-up
```

::: warning Requisitos previos
Requiere `make elk-up` y `make kafka-up` previamente (o usar `make all-up`).
:::

## Acceso

- **BackOffice**: <http://localhost:8080>

### Usuarios seed (uno por rol)

| Rol      | Usuario           | Password |
| -------- | ----------------- | -------- |
| Admin    | `lglabsadmin`     | `lgpass` |
| Operator | `lglabsoperator`  | `lgpass` |
| Support  | `lglabssupport`   | `lgpass` |
| Viewer   | `lglabsviewer`    | `lgpass` |

## Microfrontends

- [**Kafka Dashboard**](./kafka-dashboard.md) — gestión de topics/schemas/ACLs
- [**Containers Dashboard**](./containers-dashboard.md) — gestión del daemon Docker

## Detener

```bash
make backoffice-down
make backoffice-clean
```
