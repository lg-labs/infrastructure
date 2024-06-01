


## Connect with Cortex Prometheus

Config datasource Prometheus with **cortex**: `http://localhost:9009/api/prom`


# Grafana as Code

Some recomendations.

1. install

brew install jsonnet-bundler

brew install jsonnet


2. and install project

jb install github.com/grafana/grafonnet/gen/grafonnet-latest@main

3. and execute

jsonnet -J vendor dashboard.jsonnet

or

jsonnet -J vendor dashboard.jsonnet > provisioning/dashboards/node-exporter/dashboard.json

note!
If you have the error (file exists: ...), So, You should try it with `>|` .
* jsonnet -J vendor dashboard.jsonnet >| provisioning/dashboards/node-exporter/dashboard.json 
