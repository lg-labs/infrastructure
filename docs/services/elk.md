# ELK Stack

Elasticsearch + Logstash + Kibana, todo orquestado con `docker compose`.

## Arrancar

```bash
make elk-up
```

## Acceso

- **Kibana**: <http://localhost:5601>
- Usuario: `elastic`
- Password: `lgpass`

## Detener

```bash
make elk-down     # detiene
make elk-clean    # destruye volúmenes
```

## Casos de uso

- Centralizar logs de aplicaciones
- Auditoría del BackOffice (`backoffice-audit-*`)
- Búsqueda full-text sobre datos de operación
