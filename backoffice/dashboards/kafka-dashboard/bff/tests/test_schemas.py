"""Contract tests for /api/schemas/* (Phase D).

The Schema Registry is replaced by an in-memory FakeRegistryRepo (conftest.py).
"""

import pytest

from .helpers import headers_for


# ---------- LIST ----------

def test_schemas_requires_auth(app_client):
    r = app_client.get("/api/schemas")
    assert r.status_code == 403


@pytest.mark.parametrize("role", ["admin", "operator", "support", "viewer"])
def test_schemas_list_all_roles_can_read(app_client, role):
    r = app_client.get("/api/schemas", headers=headers_for(role))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(it["subject"] == "lglabs.smoke.events-value" for it in body["items"])
    seed = next(it for it in body["items"] if it["subject"] == "lglabs.smoke.events-value")
    assert seed["latest_version"] == 1
    assert seed["schema_type"] == "AVRO"
    assert seed["compatibility_level"] == "BACKWARD"


# ---------- GET SUBJECT ----------

def test_get_subject_lists_all_versions(app_client):
    r = app_client.get("/api/schemas/lglabs.smoke.events-value", headers=headers_for("viewer"))
    assert r.status_code == 200
    body = r.json()
    assert body["subject"] == "lglabs.smoke.events-value"
    assert body["compatibility_level"] == "BACKWARD"
    assert len(body["versions"]) == 1
    v = body["versions"][0]
    assert v["version"] == 1
    assert v["schema_type"] == "AVRO"
    assert "Smoke" in v["schema"]


def test_get_subject_unknown_returns_404(app_client):
    r = app_client.get("/api/schemas/does.not.exist", headers=headers_for("viewer"))
    assert r.status_code == 404
    assert r.json()["error"] == "subject_not_found"


# ---------- GET VERSION ----------

def test_get_version_latest_no_diff_for_v1(app_client):
    r = app_client.get(
        "/api/schemas/lglabs.smoke.events-value/versions/1",
        headers=headers_for("viewer"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 1
    assert body["diff_with_previous"] is None


def test_get_version_unknown_returns_404(app_client):
    r = app_client.get(
        "/api/schemas/lglabs.smoke.events-value/versions/99",
        headers=headers_for("viewer"),
    )
    assert r.status_code == 404


# ---------- REGISTER ----------

def test_register_requires_writer(app_client):
    body = {"schema": '{"type":"string"}', "schema_type": "AVRO"}
    r = app_client.post(
        "/api/schemas/lglabs.smoke.events-value/versions",
        json=body,
        headers=headers_for("viewer"),
    )
    assert r.status_code == 403


@pytest.mark.parametrize("role", ["admin", "operator"])
def test_register_writers_can_register(app_client, role):
    body = {
        "schema": '{"type":"record","name":"Smoke","fields":[{"name":"id","type":"string"},{"name":"ts","type":"long"}]}',
        "schema_type": "AVRO",
    }
    r = app_client.post(
        "/api/schemas/lglabs.smoke.events-value/versions",
        json=body,
        headers=headers_for(role),
    )
    assert r.status_code == 200
    out = r.json()
    assert out["version"] == 2
    assert isinstance(out["id"], int)


def test_register_incompatible_returns_409_verbatim(app_client, fake_registry):
    """Per design §A5, the BFF re-emits SR's incompatible_schema verbatim."""
    fake_registry.force_incompatible = True
    body = {"schema": '{"type":"int"}', "schema_type": "AVRO"}
    r = app_client.post(
        "/api/schemas/lglabs.smoke.events-value/versions",
        json=body,
        headers=headers_for("admin"),
    )
    assert r.status_code == 409
    env = r.json()
    assert env["error"] == "incompatible_schema"
    assert env["details"]["subject"] == "lglabs.smoke.events-value"
    assert "fake incompatible schema" in env["details"]["sr_message"]


def test_register_invalid_schema_returns_400(app_client, fake_registry):
    fake_registry.force_invalid_schema = True
    body = {"schema": "{not valid", "schema_type": "AVRO"}
    r = app_client.post(
        "/api/schemas/lglabs.smoke.events-value/versions",
        json=body,
        headers=headers_for("admin"),
    )
    assert r.status_code == 400
    env = r.json()
    assert env["error"] == "invalid_schema"
    assert env["details"]["sr_error_code"] == 42201


def test_register_validation_empty_schema(app_client):
    r = app_client.post(
        "/api/schemas/lglabs.smoke.events-value/versions",
        json={"schema": "", "schema_type": "AVRO"},
        headers=headers_for("admin"),
    )
    assert r.status_code == 422


# ---------- COMPATIBILITY ----------

def test_set_compatibility_requires_writer(app_client):
    r = app_client.put(
        "/api/schemas/lglabs.smoke.events-value/config",
        json={"compatibility_level": "FORWARD"},
        headers=headers_for("support"),
    )
    assert r.status_code == 403


def test_set_compatibility_admin_can_change(app_client):
    r = app_client.put(
        "/api/schemas/lglabs.smoke.events-value/config",
        json={"compatibility_level": "FULL"},
        headers=headers_for("admin"),
    )
    assert r.status_code == 200
    assert r.json()["compatibility_level"] == "FULL"

    # Verify it was persisted
    r2 = app_client.get("/api/schemas/lglabs.smoke.events-value", headers=headers_for("viewer"))
    assert r2.json()["compatibility_level"] == "FULL"


def test_set_compatibility_invalid_level_rejected_by_pydantic(app_client):
    r = app_client.put(
        "/api/schemas/lglabs.smoke.events-value/config",
        json={"compatibility_level": "BOGUS"},
        headers=headers_for("admin"),
    )
    # Pydantic literal validation → 422 (request validation), not 400
    assert r.status_code == 422


# ---------- EXPORT ----------

def test_export_requires_writer(app_client):
    r = app_client.get(
        "/api/schemas/lglabs.smoke.events-value/export",
        headers=headers_for("viewer"),
    )
    assert r.status_code == 403


def test_export_writer_gets_full_dump(app_client):
    r = app_client.get(
        "/api/schemas/lglabs.smoke.events-value/export",
        headers=headers_for("admin"),
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    cd = r.headers.get("content-disposition", "")
    assert 'filename="lglabs.smoke.events-value.json"' in cd
    body = r.json()
    assert body["subject"] == "lglabs.smoke.events-value"
    assert body["compatibility_level"] == "BACKWARD"
    assert len(body["versions"]) >= 1


# ---------- SUMMARY + HEALTH integration ----------

def test_summary_includes_schemas_count(app_client):
    r = app_client.get("/api/summary", headers=headers_for("viewer"))
    assert r.status_code == 200
    body = r.json()
    assert body["schemas_total"] >= 1
    assert body["components"]["registry"] == "ok"


def test_health_reports_registry_ok_via_fake(app_client):
    r = app_client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["registry"] == "ok"


# ---------- DIFF ----------

def test_get_v2_includes_diff_with_v1(app_client):
    """Register a v2 then verify GET /versions/2 returns a non-empty diff."""
    body_v2 = {
        "schema": '{"type":"record","name":"Smoke","fields":[{"name":"id","type":"string"},{"name":"ts","type":"long"}]}',
        "schema_type": "AVRO",
    }
    r = app_client.post(
        "/api/schemas/lglabs.smoke.events-value/versions",
        json=body_v2,
        headers=headers_for("admin"),
    )
    assert r.status_code == 200

    r2 = app_client.get(
        "/api/schemas/lglabs.smoke.events-value/versions/2",
        headers=headers_for("viewer"),
    )
    assert r2.status_code == 200
    diff = r2.json()["diff_with_previous"]
    assert diff is not None
    assert "ts" in diff       # the new field shows up
    assert "+" in diff        # unified diff marker
