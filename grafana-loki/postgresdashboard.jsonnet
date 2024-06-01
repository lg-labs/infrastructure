local g = import 'github.com/grafana/grafonnet/gen/grafonnet-latest/main.libsonnet';

g.dashboard.new('DB Order')
+ g.dashboard.withDescription('Dashboard for data from Order System')
+ g.dashboard.withPanels([
  g.panel.timeSeries.new('Total memory (GB)')
  + g.panel.timeSeries.queryOptions.withTargets([
  ])
  + g.panel.timeSeries.standardOptions.withUnit('decbytes')
  + g.panel.timeSeries.gridPos.withW(24)
  + g.panel.timeSeries.gridPos.withH(8),
])
