docker-elk-down-vol:
	docker-compose -f ${ELK}/docker-compose.yml down --volumes

docker-elk-down:
	docker-compose -f ${ELK}/docker-compose.yml down

docker-elk-up:
	docker-compose -f ${ELK}/docker-compose.yml up -d

elk-crt:
	curl -O https://download.elastic.co/demos/kibana/gettingstarted/7.x/logs.jsonl.gz && docker cp es01:/usr/share/elasticsearch/config/certs/ca/ca.crt ./.tmp/.                                                                                                                                       0:48:39

docker-sonar-down-vol:
	docker-compose -f ${SONAR}/docker-compose.yml down --volumes

docker-sonar-down:
	docker-compose -f ${SONAR}/docker-compose.yml down

docker-sonar-up:
	docker-compose -f ${SONAR}/docker-compose.yml up -d

docker-grafana-down-vol:
	docker-compose -f ${GRAFANA}/docker-compose.yml down --volumes

docker-grafana-down:
	docker-compose -f ${GRAFANA}/docker-compose.yml down

docker-grafana-up:
	docker-compose -f ${GRAFANA}/docker-compose.yml up -d

docker-postgres-down-vol:
	docker-compose -f ${POSTGRES}/docker-compose.yml down --volumes

docker-postgres-down:
	docker-compose -f ${POSTGRES}/docker-compose.yml down

docker-postgres-up:
	docker-compose -f ${POSTGRES}/docker-compose.yml up -d

docker-splunk-down-vol:
	docker-compose -f ${SPLUNK}/docker-compose.yml down --volumes

docker-splunk-down:
	docker-compose -f ${SPLUNK}/docker-compose.yml down

docker-splunk-up:
	docker-compose -f ${SPLUNK}/docker-compose.yml up -d

zookeeper-down:
	docker-compose -f ${KAFKA}/common.yml -f ${KAFKA}/zookeeper.yml down
kafka-cluster-down:
	docker-compose -f ${KAFKA}/common.yml -f ${KAFKA}/kafka_cluster.yml down
kafka-init-down:
	docker-compose -f ${KAFKA}/common.yml -f ${KAFKA}/init_kafka.yml down
kafka-mngr-down:
	docker-compose -f ${KAFKA}/common.yml -f ${KAFKA}/kafka_mngr.yml down
zookeeper-down-vol:
	docker-compose -f ${KAFKA}/common.yml -f ${KAFKA}/zookeeper.yml down --volumes
kafka-cluster-down-vol:
	docker-compose -f ${KAFKA}/common.yml -f ${KAFKA}/kafka_cluster.yml down --volumes
kafka-init-down-vol:
	docker-compose -f ${KAFKA}/common.yml -f ${KAFKA}/init_kafka.yml down --volumes
kafka-mngr-down-vol:
	docker-compose -f ${KAFKA}/common.yml -f ${KAFKA}/kafka_mngr.yml down --volumes
zookeeper-up:
	docker-compose -f ${KAFKA}/common.yml -f ${KAFKA}/zookeeper.yml up -d
kafka-cluster-up:
	docker-compose -f ${KAFKA}/common.yml -f ${KAFKA}/kafka_cluster.yml up -d
kafka-init-up:
	docker-compose -f ${KAFKA}/common.yml -f ${KAFKA}/init_kafka.yml up -d
kafka-mngr-up:
	docker-compose -f ${KAFKA}/common.yml -f ${KAFKA}/kafka_mngr.yml up -d

# ELK
elk-up: docker-elk-up
elk-down: docker-elk-down
elk-clean: docker-elk-down-vol

# SONAR
sonar-up: docker-sonar-up
sonar-down: docker-sonar-down
sonar-clean: docker-sonar-down-vol

# GRAFANA
grafana-up: docker-grafana-up
grafana-down: docker-grafana-down
grafana-clean: docker-grafana-down-vol

# DB - POSTGRES
postgres-up: docker-postgres-up
postgres-down: docker-postgres-down
postgres-clean: docker-postgres-down-vol

# DB - POSTGRES
postgres-up: docker-postgres-up
postgres-down: docker-postgres-down
postgres-clean: docker-postgres-down-vol

# Splunk
splunk-up: docker-splunk-up
splunk-down: docker-splunk-down
splunk-clean: docker-splunk-down-vol

# Kafka
kafka-up: zookeeper-up kafka-cluster-up kafka-init-up kafka-mngr-up
kafka-down:  zookeeper-down kafka-cluster-down kafka-init-down kafka-mngr-down
kafka-clean: zookeeper-down-vol kafka-cluster-down-vol kafka-init-down-vol kafka-mngr-down-vol

# ALL
all-up: elk-up sonar-up grafana-up postgres-up kafka-up
all-down: elk-down sonar-down grafana-down postgres-down kafka-down
all-clean: elk-clean sonar-clean grafana-clean postgres-clean kafka-clean

# Constants
ELK = elk
SONAR = sonar-qube
GRAFANA = grafana-loki
PROMETHUEUS= prometheus
DB = databases
POSTGRES = ${DB}/postgres
SPLUNK = splunk
KAFKA = kafka
