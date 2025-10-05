<img alt="3D" height="200px" width="100%" src="https://images.contentstack.io/v3/assets/bltefdd0b53724fa2ce/blt9c5291cc47b39d26/5c11ee02a6ed043c0dbb01d1/elk-stack-elastic-soup.svg" title="ELK" />

<!-- TOC -->
* [In part one of this two-part series](#in-part-one-of-this-two-part-series)
  * [File structure](#file-structure)
* [Elasticsearch](#elasticsearch)
  * [Setup and Elasticsearch node](#setup-and-elasticsearch-node)
  * [Docker-compose.yml (‘es01’ container)](#docker-composeyml-es01-container)
  * [Elastic Docker Hub](#elastic-docker-hub)
  * [Docker Compose](#docker-compose)
    * [(Optional) Troubleshooting Virtual Memory misconfigurations](#optional-troubleshooting-virtual-memory-misconfigurations)
* [Kibana](#kibana)
* [Metricbeat](#metricbeat)
* [Filebeat](#filebeat)
      * [How use the first way?](#how-use-the-first-way)
      * [How use the first way?](#how-use-the-first-way-1)
* [Logstash](#logstash)
* [References](#references)
<!-- TOC -->

# In part one of this two-part series
## File structure

├── .env

├── docker-compose.yml

├── filebeat.yml

├── logstash.conf

└── metricbeat.yml


# Elasticsearch
## Setup and Elasticsearch node


<pre>
We also see that we're standing up a container labeled “setup” with some bash magic to specify our cluster nodes.   
This allows us to call the elasticsearch-certutil, passing the server names in yml format in order to create the CA 
cert and node certs. If you wanted to have more than one Elasticsearch node in your stack, this is where you would  
add the server name to allow the cert creation.
</pre>


## Docker-compose.yml (‘es01’ container)

This will be the **single-node** cluster of **Elasticsearch** that we’re using for testing.


Notice we’ll be using the CA cert and node certificates that were generated. 
<pre>
You will also notice that we’re storing the Elasticsearch data in a volume outside of the container by specifying 
-esdata01:/usr/share/elasticsearch/data The two primary reasons for this are performance and data persistence. 
If we were to leave the data directory inside the container, we would see a significant degradation in the performance 
of our Elasticsearch node, as well as lose data anytime we needed to change the configuration of the container within 
our docker-compose file.
</pre>

## Elastic Docker Hub

If you want to see the images outside of Docker Desktop, you can always find them in the [official Elastic Docker Hub][1].

## Docker Compose

```shell
  docker-compose up -d
```

### (Optional) Troubleshooting Virtual Memory misconfigurations
When starting up the Elasticsearch node for the first time on the Virtual Memory configuration and receive an error message

The key takeaway here is **max virtual memory** areas vm.max_map_count **[65530]** is too low, increase to at least **[262144]**.

Ultimately, the command `sysctl -w vm.max_map_count=262144` needs to be run where the containers are being hosted.

How fix this problem? [more details here!][3]

_So far so good, but let's test._

![ My directory is “elastic-elk”!][img]

Remember, the name of the set of containers is based on the folder from which the docker-compose.yml is running.

For example, my directory is “elastic-elk” but the **container name** is defined as **"es01".**

```shell
  docker cp es01:/usr/share/elasticsearch/config/certs/ca/ca.crt ./.tmp/.
```
Once the certificate is downloaded, run a curl command to query the Elasticsearch node:

```shell
  curl --cacert ./.tmp/ca.crt -u elastic:lgpass https://localhost:9200
```
![ Success!][img1]

**Success! 🎉**

# Kibana

Notice in our `environment` section that we’re specifying `ELASTICSEARCH_HOSTS=https://es01:9200 `  
We’re able to specify the container name here for our _**ES01**_ **Elasticsearch container** since we’re utilizing 
the Docker default networking.

Let's load up Kibana and see if we can access it.
![ Kibana Container!][img2]

The containers are green. We should now be able to reach [`http://localhost:5601`][4]

![ Success!][img3]


# Metricbeat

_Metricbeat to help us keep an eye on things._

Our Metricbeat is dependent on **ES01** and Kibana nodes being healthy before starting.  

The notable configurations here are in the [metricbeat.yml][5] file. We have enabled **four modules**  
for gathering metrics including: 
1. Elasticsearch
2. Kibana
3. Logstash
4. Docker

Note: For Logstash, Filebeat, and Metricbeat, the configuration files are using bind mounts. Bind mounts for files will  
retain the same permissions and ownership within the container that they have on the host system. Be sure to set   
permissions such that the files will be readable and, ideally, not writeable by the container’s user. You will receive   
an error in the container otherwise. **Removing the write permissions on your host may suffice**.

Once we verify Metricbeat is up.

![ Metricbeat!][img4]

Into Kibana and navigate to [“Stack Monitoring”][6] to see how things look. 

_Don't forget to set up your out-of-the-box rules!_

![ Stack Monitoring!][img5]
![ Stack Monitoring!][img6]

Metricbeat is also configured for monitoring the container’s host through [`/var/run/docker.sock`][7] **Checking Elastic 
Observability** allows you to see metrics coming in from your host.

![ Stack Monitoring!][img7]


# Filebeat

Now that the cluster is stable and monitored with Metricbeat, let’s look at Filebeat for log ingestion. Here, our 
Filebeat will be utilized in two different ways:

**First**, we set a bind mount to map the folder `“filebeat_ingest_data”` into the container. If this folder doesn't exist on your host, it will be created when the container spins up.

**Second** and last, map in `/var/lib/docker/containers` and `/var/run/docker.sock` which, _combined_ with the `filebeat.autodiscover` section and hints-based autodiscover, allows Filebeat to pull in the logs for all the containers.

#### How use the first way?
If you’d like to test the Logs Stream viewer within Elastic Observability for your custom logs, you can easily **drop** any file with a _**.log** extension_ into `/filebeat_ingest_data/` and the logs will be read into the default **Filebeat Datastream**.

#### How use the first way?
These logs will also be found in the Logs Stream viewer mentioned.

# Logstash

The Logstash configuration is very similar to the Filebeat configuration. Again we’re using a bind mount and mapping a folder called `/logstash_ingest_data/` from the host into the Logstash container. Here, you can test out some of the many input plugins and filter plugins by modifying the logstash.yml file. Then drop your data into the /logstash_ingest_data/ folder. 

You may need to restart your Logstash container after modifying the `logstash.yml` file.

Note, the Logstash output index name is `"logstash-%{+YYYY.MM.dd}"`. To see the data, you will need to create a Data View for the `“logstash-*”` pattern, as seen below.

# Common issues
### _issue 1:_
> ...Exiting: error loading config file: config file ("metricbeat.yml") must be owned by the user identifier (uid=0) or root
**Solution:** Change the permissions of the file `metricbeat.yml` to be read-only for the owner.

```shell
  sudo chown root:wheel metricbeat.yml
  sudo chmod 644 metricbeat.yml
```
### _ssue 2:_
> ...Exiting: error loading config file: config file ("filebeat.yml") must be owned by the user identifier (uid=0) or root
**Solution:** Change the permissions of the file `filebeat.yml` to be read-only for the owner.
```shell
  sudo chown root:wheel filebeat.yml
  sudo chmod 644 filebeat.yml
```

# References
1. [Getting started with the Elastic Stack and Docker-Compose][1]
2. [Official Elastic Docker Hub][2]


[1]: https://www.elastic.co/es/blog/getting-started-with-the-elastic-stack-and-docker-compose
[2]: https://www.docker.elastic.co/
[3]: https://www.elastic.co/es/blog/getting-started-with-the-elastic-stack-and-docker-compose#:~:text=Docker%20Hub.-,Troubleshooting,-Virtual%20Memory%20misconfigurations
[4]: http://localhost:5601
[5]: metricbeat.yml
[6]: http://localhost:5601/app/monitoring
[7]: /var/run/docker.sock

[img]: https://github.com/lg-labs/infrastructure/assets/105936384/d2876bc3-44d5-4623-a5e8-f9e6be8ab54b "elastic-elk"
[img1]: https://github.com/lg-labs/infrastructure/assets/105936384/133240ee-5114-4fe4-a3ec-1871ebad9df4
[img2]: https://github.com/lg-labs/infrastructure/assets/105936384/06cf8548-c8c3-489f-a779-dadf0f55db6d
[img3]: https://github.com/lg-labs/infrastructure/assets/105936384/be2a96ad-e79d-4689-aac5-57baaeb4f045 
[img4]: https://github.com/lg-labs/infrastructure/assets/105936384/350dffc6-8d1a-4d0c-90c5-f211f5818063
[img5]: https://github.com/lg-labs/infrastructure/assets/105936384/76c4a508-dfb8-44a3-8f9d-0a0f9ce8fe86
[img6]: https://github.com/lg-labs/infrastructure/assets/105936384/e6d01435-579e-4b77-8a5f-63ca97acab79
[img7]: https://github.com/lg-labs/infrastructure/assets/105936384/2007b629-56c7-418a-a531-100446fce044
