"""Contract tests for /api/_owners and /api/summary."""

from .conftest import headers_for


def test_owners_requires_auth(app_client):
    r = app_client.get("/api/_owners")
    assert r.status_code == 403


def test_owners_viewer_can_read(app_client):
    r = app_client.get("/api/_owners", headers=headers_for("viewer"))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    ids = {o["id"] for o in body["items"]}
    assert ids == {"team-platform", "team-data"}


def test_summary_requires_auth(app_client):
    r = app_client.get("/api/summary")
    assert r.status_code == 403


def test_summary_excludes_internal_topics_from_count(app_client):
    r = app_client.get("/api/summary", headers=headers_for("support"))
    assert r.status_code == 200
    body = r.json()
    # Fake repo seeds 1 internal + 1 lglabs.* topic
    assert body["topics_total"] == 1
    assert body["topics_internal_hidden"] == 1
    assert body["brokers_alive"] == 3
    assert body["components"]["kafka"] == "ok"
