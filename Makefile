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

# ALL
all-up: elk-up sonar-up grafana-up postgres-up
all-down: elk-down sonar-down grafana-down postgres-down
all-clean: elk-clean sonar-clean grafana-clean postgres-clean




# Constants
ELK = elk
SONAR = sonar-qube
GRAFANA = grafana-loki
PROMETHUEUS= prometheus
DB = databases
POSTGRES = ${DB}/postgresql
