# Kafka Dashboard

Microfrontend del BackOffice (`/kafka/`) para **gestión declarativa** del cluster Kafka:

- **Topics**
- **Schemas**
- **ACL-metadata**

Con SSO + roles del BackOffice y audit a `backoffice-audit-*`.

## Arrancar

```bash
make backoffice-up   # incluye kafka-dashboard
```

::: info
Este dashboard no tiene un comando `make` propio: arranca automáticamente junto al BackOffice.
:::

## Acceso

- **URL**: <http://localhost:8080/kafka/>
- Usuarios: los [4 usuarios seed del BackOffice](./index.md#usuarios-seed-uno-por-rol)

::: warning Requisitos previos
Requiere `make elk-up` y `make kafka-up` previamente (o usar `make all-up`).
:::

## Detener / Destruir

```bash
make backoffice-down    # detiene junto al BackOffice
make backoffice-clean   # destruye backoffice-kafka-dashboard-data
```
