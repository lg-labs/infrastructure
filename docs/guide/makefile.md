# Makefile

El proyecto se opera íntegramente desde un `Makefile`. Cada stack expone tres comandos: **up**, **down** y **clean**.

## Patrón común

```bash
make <servicio>-up       # arranca contenedores
make <servicio>-down     # los detiene (mantiene volúmenes)
make <servicio>-clean    # detiene y borra volúmenes (destructivo)
```

## Comandos por servicio

| Stack         | up                  | down                  | clean                  |
| ------------- | ------------------- | --------------------- | ---------------------- |
| ELK           | `make elk-up`       | `make elk-down`       | `make elk-clean`       |
| SonarQube     | `make sonar-up`     | `make sonar-down`     | `make sonar-clean`     |
| Grafana+Loki  | `make grafana-up`   | `make grafana-down`   | `make grafana-clean`   |
| PostgreSQL    | `make postgres-up`  | `make postgres-down`  | `make postgres-clean`  |
| Splunk        | `make splunk-up`    | `make splunk-down`    | `make splunk-clean`    |
| Kafka         | `make kafka-up`     | `make kafka-down`     | `make kafka-clean`     |
| BackOffice    | `make backoffice-up`| `make backoffice-down`| `make backoffice-clean`|

## Comandos globales

```bash
make all-up      # levanta todos los stacks
make all-down    # los detiene
make all-clean   # los destruye (volúmenes incluidos)
```

## Utilidades Docker

```bash
make docker-kill    # detiene y elimina TODOS los contenedores en ejecución
make docker-prune   # limpia sistema docker (volúmenes incluidos)
```

::: warning
`docker-kill` y `*-clean` son destructivos. Úsalos con cuidado en entornos compartidos.
:::
