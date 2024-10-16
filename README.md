# 🛠️ Tools base for developers

<img src="https://pbs.twimg.com/profile_images/1410772782238081029/VO3SPTNV_400x400.jpg" align="left" width="172px" height="172px"/>
<img align="left" width="0" height="172px" hspace="10"/>

> 👋  Welcome From **lg-labs**! Get the infrastructure basic for begin to develop your project with high level.

[![lg-labs][0]][1]
[![License][2]][3]

With the utility **lg-labs** has created this project, to help community.

For more information, check [Personal Blog][1].

# You can ...
Using `makefile`

## [Start with ELK][elk-doc]
Using `makefile` to 😀 ELK **start**.
```shell
make elk-up
```
> 👋  **[Kibana Web Site, Port:5601][kibana]**
> 
> Username: `elastic`  
> Password: `lgpass`

To stop ELK `make elk-down` or completely destroy `make elk-clean`.

😴 ELK **stop**:
```shell
make elk-down
```
⛔ ELK **destroy**:
```shell
make elk-clean
```

## [Start with SonarQube][sonar-doc]
Using `makefile` to 😀 SonarQube **start**.

```shell
make sonar-up
```

> 👋  **[SonarQube WebSite, Port:9000][sonar]** 
> 
> _For these cases using default credentials_  
> Username: `lglabs`  
> Password: `lgpass`

To stop SonarQube `make sonar-down` or completely destroy `make sonar-clean`.

😴 SonarQube **stop**:
```shell
make sonar-down
```
⛔️ SonarQube **destroy**:
```shell
make sonar-clean
```

## [Start with Grafana][grafana-doc]
Using `makefile` to 😀 Grafana **start**.

```shell
make grafana-up
```

> 👋  **[Grafana WebSite, Port:3000][grafana]**
>
> Username: `lglabs`  
> Password: `lgpass`

To stop Grafana `make grafana-down` or completely destroy `make grafana-clean`.

😴 Grafana **stop**:           
```shell
make grafana-down
```
⛔️ Grafana **destroy**:
```shell
make grafana-clean
```
## [Start with Postgres][db-doc]
Using `makefile` to 😀 Postgres **start**.

```shell
make postgres-up
```
> 👋  **[Postgres UI][postgres-ui]**
>
> Username: `lg@labx.com`  
> Password: `lgpass`
> 
Create a server connection at PgAdmin
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

> 👋  **[PostgreSQL Connection, Port:5432][postgres]**
>
> _For these cases using default credentials_  
> Url: `jdbc:postgresql://localhost:5432/postgres`  
> Username: `lglabs`  
> Password: `lgpass`

😴 Postgres **stop**:
```shell
make postgres-down
```
⛔️ Postgres **destroy**:
```shell
make postgres-clean
```

## [Start with Splunk][splunk-doc]
Using `makefile` to 😀 Splunk **start**.

```shell
make splunk-up
```

> 👋  **[Splunk WebSite, Port:9003][splunk]**
>
> _For these cases using default credentials_  
> Username: `admin`  
> Password: `lgpass2024*`
> 

😴 Splunk **stop**:
```shell
make splunk-down
```
⛔️ Splunk **destroy**:
```shell
make splunk-clean
```

## [Start with Kafka][kafka-doc]
Using `makefile` to 😀 Kafka **start**.

```shell
make kafka-up
```

> 👋  **[Kafka UI 1 WebSite, Port:9080][kafka]**
>

😴 Kafka **stop**:
```shell
make kafka-down
```
⛔️ Kafka **destroy**:
```shell
make kafka-clean
```

# All in one
Using `makefile` to **start** All.

```shell
make all-up
```

To **stop** all.
```shell
make all-down
```
⛔️ Or completely **destroy**.
```shell
make all-clean
```


## ⚖️ License

The MIT License (MIT). Please see [License][3] for more information.


[0]: https://img.shields.io/badge/LgLabs-community-blue?style=flat-square
[1]: https://lufgarciaqu.medium.com
[2]: https://img.shields.io/badge/license-MIT-green?style=flat-square
[3]: LICENSE


[kibana]: http://localhost:5601
[sonar]: http://localhost:9000
[grafana]: http://localhost:3000
[postgres]: jdbc:postgresql://localhost:5432/postgres
[splunk]: http://localhost:9003 "http://localhost:9003"
[kafka]: http://localhost:9080 "http://localhost:9080"
[postgres-ui]: http://localhost:5012 "http://localhost:5012"


[elk-doc]: elk/README.md
[db-doc]: databases/README.md
[sonar-doc]: sonar-qube/README.md
[grafana-doc]: grafana-loki/README.md
[splunk-doc]: splunk/README.md
[kafka-doc]: kafka/README.md
