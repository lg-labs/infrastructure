"""Contract tests for /api/health and /api/whoami."""

from .conftest import headers_for


def test_health_ok_with_fake_kafka_alive(app_client):
    r = app_client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["kafka"] == "ok"
    assert body["sqlite"] == "ok"


def test_health_degraded_when_kafka_down(app_client, fake_kafka):
    fake_kafka.alive = False
    r = app_client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "degraded"
    assert body["kafka"] == "degraded"


def test_health_is_public_no_auth(app_client):
    # No identity headers — must still respond
    r = app_client.get("/api/health")
    assert r.status_code == 200


def test_whoami_echoes_identity(app_client):
    r = app_client.get("/api/whoami", headers=headers_for("admin"))
    assert r.status_code == 200
    body = r.json()
    assert body["user"] == "lglabsadmin"
    assert body["groups"] == "admin"
