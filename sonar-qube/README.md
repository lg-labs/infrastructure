# 

<img alt="3D" height="30%" width="60%" src="https://assets-eu-01.kc-usercontent.com/b98b0e99-a92d-0140-c108-93833c7e1e31/f284da48-cd09-4c3b-83b4-9d9787d7845c/sonar-development-workflow.png?w=2912&h=1658&auto=format&fit=crop" title="Sonar" />

# SonarQube

> 👋  **[SonarQube WebSite][4]**
>
> _For these cases using default credentials_  
> Username: `lglabs`  
> Password: `lgpass`

## 👷 A Sonar Project

Create a sonar project as `LgApp`

```shell
     curl -u lglabs:lgpass -X POST 'http://localhost:9000/api/projects/create?name=LgApp&project=lgapp' -v
```

```shell
mvn clean verify sonar:sonar \
  -Dsonar.projectKey=lgapp \
  -Dsonar.projectName='LgApp' \
  -Dsonar.host.url=http://localhost:9000 \
  -Dsonar.token=[TOKEN]
```

## ⚠️ Reset admin credentials

Read more about [Sonar API][5].

###### _Default credentials (admin:admin)_
```shell
curl -u lglabs:lgpass -X POST 'http://localhost:9000/api/users/change_password?login=lglabs&previousPassword=lgpass&password=admin' -v
curl -u lglabs:admin -X POST 'http://localhost:9000/api/users/update_login?login=lglabs&newLogin=admin' -v
```
#### Reference
1. [SonarQube][1]
2. [Configuration Project][2]
3. [Docker Compose V2 to V3(Upgrading)][3]
4. [Reset admin credentials][5]



[1]: https://docs.sonarsource.com/sonarqube/latest
[2]: https://docs.sonarsource.com/sonarqube/latest/project-administration/project-settings/
[3]: https://docs.docker.com/compose/compose-file/compose-versioning/#upgrading
[4]: http://localhost:9000 "http://localhost:9000"
[5]: https://sonarqube.inria.fr/sonarqube/web_api/api/users

[img_1]: https://assets-eu-01.kc-usercontent.com/44070fd7-e8ba-019d-7d0d-5ec61b44b46f/f284da48-cd09-4c3b-83b4-9d9787d7845c/sonar-development-workflow.png?w=2912&h=1658&auto=format&fit=crop
