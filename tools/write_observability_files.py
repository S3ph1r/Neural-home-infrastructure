
import os

DOCKER_COMPOSE = r"""version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--web.enable-lifecycle'
    ports:
      - "9090:9090"
    restart: unless-stopped
    networks:
      - monitoring

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
    restart: unless-stopped
    networks:
      - monitoring

  node-exporter:
    image: prom/node-exporter:latest
    container_name: node-exporter
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.rootfs=/rootfs'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
    restart: unless-stopped
    networks:
      - monitoring

  redis-exporter:
    image: oliver006/redis_exporter:latest
    container_name: redis-exporter
    environment:
      - REDIS_ADDR=redis://192.168.1.100:6379
    ports:
      - "9121:9121"
    restart: unless-stopped
    networks:
      - monitoring

volumes:
  prometheus_data:
  grafana_data:

networks:
  monitoring:
    driver: bridge
"""

PROMETHEUS_YML = r"""global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']

  - job_name: 'orchestrator'
    metrics_path: '/metrics'
    static_configs:
      - targets: ['192.168.1.20:8000']
"""

DASHBOARD_YML = r"""apiVersion: 1

providers:
  - name: 'Neural-Home Dashboards'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    editable: true
    options:
      path: /etc/grafana/provisioning/dashboards
"""

GPU_DASHBOARD_JSON = r"""
{
  "annotations": {
    "list": [
      {
        "builtIn": 1,
        "datasource": "-- Grafana --",
        "enable": true,
        "hide": true,
        "iconColor": "rgba(0, 211, 255, 1)",
        "name": "Annotations & Alerts",
        "type": "dashboard"
      }
    ]
  },
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 0,
  "id": null,
  "links": [],
  "liveNow": false,
  "panels": [
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "thresholds"
          },
          "mappings": [
            {
              "options": {
                "0": {
                  "color": "red",
                  "index": 0,
                  "text": "BUSY / COOLDOWN"
                },
                "1": {
                  "color": "green",
                  "index": 1,
                  "text": "READY"
                }
              },
              "type": "value"
            }
          ],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "red",
                "value": null
              },
              {
                "color": "green",
                "value": 1
              }
            ]
          }
        },
        "overrides": []
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 0
      },
      "id": 2,
      "options": {
        "colorMode": "background",
        "graphMode": "none",
        "justifyMode": "auto",
        "orientation": "auto",
        "reduceOptions": {
          "calcs": [
            "lastNotNull"
          ],
          "fields": "",
          "values": false
        },
        "textMode": "auto_inline",
        "wideLayout": true
      },
      "pluginVersion": "8.4.3",
      "targets": [
        {
          "datasource": "Prometheus",
          "expr": "neural_home_gpu_status",
          "refId": "A"
        }
      ],
      "title": "GPU Availability",
      "type": "stat"
    }
  ],
  "schemaVersion": 35,
  "style": "dark",
  "tags": [],
  "templating": {
    "list": []
  },
  "time": {
    "from": "now-6h",
    "to": "now"
  },
  "timepicker": {},
  "timezone": "",
  "title": "GPU Status",
  "uid": "gpu-stat-001",
  "version": 1,
  "weekStart": ""
}
"""

DATASOURCES_YML = r"""apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    orgId: 1
    url: http://prometheus:9090
    basicAuth: false
    isDefault: true
    editable: true
"""

base_dir = os.path.expanduser("~/Projects/neural-home-repo/infrastructure/observability")
dash_prov_dir = os.path.join(base_dir, "grafana/provisioning/dashboards")
data_prov_dir = os.path.join(base_dir, "grafana/provisioning/datasources")
os.makedirs(dash_prov_dir, exist_ok=True)
os.makedirs(data_prov_dir, exist_ok=True)

with open(os.path.join(base_dir, "docker-compose.yml"), "w") as f:
    f.write(DOCKER_COMPOSE)

with open(os.path.join(base_dir, "prometheus.yml"), "w") as f:
    f.write(PROMETHEUS_YML)

with open(os.path.join(dash_prov_dir, "dashboards.yml"), "w") as f:
    f.write(DASHBOARD_YML)

with open(os.path.join(dash_prov_dir, "gpu_dashboard.json"), "w") as f:
    f.write(GPU_DASHBOARD_JSON)

with open(os.path.join(data_prov_dir, "datasources.yml"), "w") as f:
    f.write(DATASOURCES_YML)

print("Files written successfully.")
