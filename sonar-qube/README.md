# 

<img alt="3D" height="30%" width="60%" src="https://assets-eu-01.kc-usercontent.com/44070fd7-e8ba-019d-7d0d-5ec61b44b46f/f284da48-cd09-4c3b-83b4-9d9787d7845c/sonar-development-workflow.png?w=2912&h=1658&auto=format&fit=crop" title="Sonar" />

# SonarQube

> 👋  **[SonarQube WebSite][4]**
>
> _For these cases using default credentials_  
> Username: `admin`  
> Password: `admin`

```shell
mvn clean verify sonar:sonar \
  -Dsonar.projectKey=MyProject \
  -Dsonar.projectName='MyProject' \
  -Dsonar.host.url=http://localhost:9000 \
  -Dsonar.token=[TOKEN]
```


#### Reference
1. [SonarQube][1]
2. [Configuration Project][2]
2. [Docker Compose V2 to V3(Upgrading)][3]



[1]: https://docs.sonarsource.com/sonarqube/latest
[2]: https://docs.sonarsource.com/sonarqube/latest/project-administration/project-settings/
[3]: https://docs.docker.com/compose/compose-file/compose-versioning/#upgrading
[4]: http://localhost:9000 "http://localhost:9000"

[img_1]: https://assets-eu-01.kc-usercontent.com/44070fd7-e8ba-019d-7d0d-5ec61b44b46f/f284da48-cd09-4c3b-83b4-9d9787d7845c/sonar-development-workflow.png?w=2912&h=1658&auto=format&fit=crop
