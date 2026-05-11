# Apache Kafka

Broker de eventos con UI de inspección.

## Arrancar

```bash
make kafka-up
```

## Acceso

- **Kafka UI**: <http://localhost:9080>

## Detener

```bash
make kafka-down
make kafka-clean
```

## Gestión avanzada

Para gestión declarativa de **topics**, **schemas** y **ACL-metadata** con SSO y RBAC, ver el [Kafka Dashboard](/backoffice/kafka-dashboard) del BackOffice.
