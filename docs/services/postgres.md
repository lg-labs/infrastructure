# PostgreSQL

Base de datos relacional + PgAdmin.

## Arrancar

```bash
make postgres-up
```

## Acceso a PgAdmin

- **PgAdmin**: <http://localhost:5012>
- Usuario: `lg@labx.com`
- Password: `lgpass`

## Conexión PostgreSQL

| Campo    | Valor                                          |
| -------- | ---------------------------------------------- |
| Host     | `localhost` (o `postgres` desde otro contenedor) |
| Puerto   | `5432`                                         |
| DB       | `postgres`                                     |
| Usuario  | `lglabs`                                       |
| Password | `lgpass`                                       |
| JDBC URL | `jdbc:postgresql://localhost:5432/postgres`    |

## Server pre-configurado para PgAdmin

```json
{
  "Servers": {
    "1": {
      "Name": "My PostgreSQL Server",
      "Group": "Servers",
      "Host": "postgres",
      "Port": 5432,
      "MaintenanceDB": "postgres",
      "Username": "lglabs",
      "Password": "lgpass",
      "SSLMode": "prefer",
      "UseSSHTunnel": 0
    }
  }
}
```

## Detener

```bash
make postgres-down
make postgres-clean
```
