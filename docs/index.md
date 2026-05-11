---
layout: home

hero:
  name: lg-labs Infrastructure
  text: Tools base para desarrolladores
  tagline: Stack listo para producir — ELK, Kafka, SonarQube, Grafana, Splunk, Postgres y un BackOffice con SSO sobre Keycloak.
  image:
    src: https://pbs.twimg.com/profile_images/1410772782238081029/VO3SPTNV_400x400.jpg
    alt: lg-labs
  actions:
    - theme: brand
      text: Empezar
      link: /guide/introduction
    - theme: alt
      text: Ver servicios
      link: /services/

features:
  - icon: 🔎
    title: ELK Stack
    details: Elasticsearch, Logstash y Kibana listos para indexar y visualizar logs.
    link: /services/elk
  - icon: 📊
    title: Grafana + Loki
    details: Observabilidad completa con dashboards y agregación de logs.
    link: /services/grafana
  - icon: 🧪
    title: SonarQube
    details: Análisis estático de calidad de código y vulnerabilidades.
    link: /services/sonarqube
  - icon: 🗄️
    title: PostgreSQL
    details: Base de datos relacional con PgAdmin pre-configurado.
    link: /services/postgres
  - icon: 🚌
    title: Apache Kafka
    details: Broker de eventos con UI integrada para inspección.
    link: /services/kafka
  - icon: 🪵
    title: Splunk
    details: Indexación y análisis de datos operacionales.
    link: /services/splunk
  - icon: 🛡️
    title: BackOffice con SSO
    details: Una sola URL con Keycloak para Kafka, contenedores, logs y administración.
    link: /backoffice/
  - icon: ⚙️
    title: Makefile-first
    details: Un solo comando para levantar, parar o destruir cualquier componente.
    link: /guide/makefile
---
