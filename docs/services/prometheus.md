# Prometheus

Sistema de monitoreo y alertas basado en métricas.

## Estructura

El stack se encuentra bajo `prometheus/` con su `docker-compose.yml` y configuraciones asociadas.

::: tip
Prometheus normalmente se consume desde Grafana como datasource. Levanta primero `make grafana-up` y luego configura el datasource apuntando a Prometheus.
:::
