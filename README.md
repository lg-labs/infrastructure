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

## Start with ELK

```shell
make elk-up
```
> 👋  **[Kibana Web Site, Port:5601][kibana]**
> 
> Username: `elastic`  
> Password: `lgpass`

To stop ELK `make elk-down` or completely destroy `make elk-clean`.

## Start with SonarQube
Using `makefile`

```shell
make sonar-up
```

> 👋  **[SonarQube WebSite, Port:9000][sonar]** 
> 
> _For these cases using default credentials_  
> Username: `admin`  
> Password: `admin`

To stop SonarQuebe `make sonar-down` or completely destroy `make sonar-clean`.


## Start with Grafana
Using `makefile`

```shell
make grafana-up
```

> 👋  **[Grafana WebSite, Port:3000][grafana]**
>
> Username: `admin`  
> Password: `lgpass`

To stop Grafana `make grafana-down` or completely destroy `make grafana-clean`.

## All in one
Using `makefile`

```shell
make all-up
```

To stop all `make all-down` or completely destroy `make all-clean`.


## ⚖️ License

The MIT License (MIT). Please see [License][3] for more information.


[0]: https://img.shields.io/badge/LgLabs-community-blue?style=flat-square
[1]: https://lufgarciaqu.medium.com
[2]: https://img.shields.io/badge/license-MIT-green?style=flat-square
[3]: LICENSE



[kibana]: http://localhost:5601
[sonar]: http://localhost:9000
[grafana]: http://localhost:3000

