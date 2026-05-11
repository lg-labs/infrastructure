# Introducción

**lg-labs Infrastructure** es una colección de stacks listos para usar (vía `docker compose` + `make`) que entregan a un equipo de desarrollo la infraestructura básica de observabilidad, calidad de código, mensajería, base de datos y administración con SSO.

## Filosofía

- **Un comando, un stack**: cada servicio se controla con `make <servicio>-up | -down | -clean`.
- **Cero configuración inicial**: usuarios y contraseñas seed listos para entrar.
- **Composable**: puedes levantar lo que necesites, o todo con `make all-up`.
- **Auditable**: el BackOffice envía eventos a ELK automáticamente.

## Componentes incluidos

| Stack          | Para qué sirve                                  |
| -------------- | ----------------------------------------------- |
| ELK            | Logs centralizados y búsqueda                   |
| Kafka          | Mensajería de eventos                           |
| SonarQube      | Calidad y seguridad del código                  |
| Grafana + Loki | Dashboards y logs                               |
| Splunk         | Análisis operacional                            |
| PostgreSQL     | Base de datos relacional                        |
| Prometheus     | Métricas                                        |
| BackOffice     | Portal con SSO (Keycloak) sobre todo lo anterior |

## Siguiente paso

- [Requisitos](./requirements.md)
- [Inicio rápido](./quick-start.md)
