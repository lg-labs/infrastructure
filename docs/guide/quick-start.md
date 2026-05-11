# Inicio rápido

## 1. Clona el repositorio

```bash
git clone https://github.com/lg-labs/infrastructure.git
cd infrastructure
```

## 2. Levanta lo que necesitas

::: code-group

```bash [Todo]
make all-up
```

```bash [Solo ELK]
make elk-up
```

```bash [Solo Kafka]
make kafka-up
```

```bash [BackOffice (requiere ELK + Kafka)]
make elk-up && make kafka-up && make backoffice-up
```

:::

## 3. Accede a las UIs

| Servicio           | URL                                             | Usuario          | Password       |
| ------------------ | ----------------------------------------------- | ---------------- | -------------- |
| Kibana             | <http://localhost:5601>                         | `elastic`        | `lgpass`       |
| SonarQube          | <http://localhost:9000>                         | `lglabs`         | `lgpass`       |
| Grafana            | <http://localhost:3000>                         | `lglabs`         | `lgpass`       |
| PgAdmin            | <http://localhost:5012>                         | `lg@labx.com`    | `lgpass`       |
| Splunk             | <http://localhost:9003>                         | `admin`          | `lgpass2024*`  |
| Kafka UI           | <http://localhost:9080>                         | —                | —              |
| BackOffice         | <http://localhost:8080>                         | `lglabsadmin`    | `lgpass`       |

## 4. Detener o limpiar

```bash
make all-down    # parar
make all-clean   # destruir volúmenes
```

::: tip
Cada stack tiene su propio set de comandos (`<servicio>-up`, `-down`, `-clean`).
Ver [Makefile](./makefile.md) para la lista completa.
:::
