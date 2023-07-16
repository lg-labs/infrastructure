docker-elk-down-vol:
	docker-compose -f ${ELK}/docker-compose.yml down --volumes

docker-elk-down:
	docker-compose -f ${ELK}/docker-compose.yml down --volumes

docker-elk-up:
	docker-compose -f ${ELK}/docker-compose.yml up -d

elk-crt:
	curl -O https://download.elastic.co/demos/kibana/gettingstarted/7.x/logs.jsonl.gz && docker cp es01:/usr/share/elasticsearch/config/certs/ca/ca.crt ./.tmp/.                                                                                                                                       0:48:39

docker-sonar-down-vol:
	docker-compose -f ${SONAR}/docker-compose.yml down --volumes

docker-sonar-down:
	docker-compose -f ${SONAR}/docker-compose.yml down --volumes

docker-sonar-up:
	docker-compose -f ${SONAR}/docker-compose.yml up -d


# ELK
elk-up: docker-elk-up
elk-down: docker-elk-down
elk-clean: docker-elk-down-vol

# SONAR
sonar-up: docker-sonar-up
sonar-down: docker-sonar-down
sonar-clean: docker-sonar-down-vol

# ALL
all-up: elk-up sonar-up
all-down: elk-down sonar-down
all-clean: elk-clean sonar-clean




# Constants
ELK = elk
SONAR = sonar-qube