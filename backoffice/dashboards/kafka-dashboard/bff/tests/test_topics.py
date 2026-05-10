"""Contract tests for /api/topics CRUD (US-1..4, US-9).

Covers the role × endpoint × status matrix from design.md §6.
"""

import pytest

from .conftest import headers_for


VALID_PAYLOAD = {
    "name": "lglabs.test.events",
    "partitions": 3,
    "replication_factor": 3,
    "cleanup_policy": "delete",
    "retention_ms": 604_800_000,
    "min_insync_replicas": 2,
    "description": "test topic for contract suite",
    "owner": "team-platform",
}


# ---------- LIST ----------

class TestListTopics:
    def test_no_auth_403(self, app_client):
        assert app_client.get("/api/topics").status_code == 403

    @pytest.mark.parametrize("role", ["admin", "operator", "support", "viewer"])
    def test_all_roles_can_list(self, app_client, role):
        r = app_client.get("/api/topics", headers=headers_for(role))
        assert r.status_code == 200
        body = r.json()
        # Internal topic hidden by default
        names = [t["name"] for t in body["items"]]
        assert "__consumer_offsets" not in names
        assert "lglabs.seed.events" in names

    def test_include_internal_flag(self, app_client):
        r = app_client.get("/api/topics?include_internal=true", headers=headers_for("admin"))
        assert r.status_code == 200
        names = [t["name"] for t in r.json()["items"]]
        assert "__consumer_offsets" in names

    def test_search_filter(self, app_client):
        r = app_client.get("/api/topics?search=seed", headers=headers_for("admin"))
        assert r.status_code == 200
        items = r.json()["items"]
        assert all("seed" in t["name"].lower() for t in items)

    def test_pagination(self, app_client):
        r = app_client.get("/api/topics?page=1&page_size=1", headers=headers_for("admin"))
        body = r.json()
        assert body["page"] == 1
        assert body["page_size"] == 1
        assert len(body["items"]) <= 1


# ---------- GET ----------

class TestGetTopic:
    def test_404_unknown(self, app_client):
        r = app_client.get("/api/topics/lglabs.does.not.exist", headers=headers_for("viewer"))
        assert r.status_code == 404
        assert r.json()["error"] == "topic_not_found"

    def test_returns_full_detail(self, app_client):
        r = app_client.get("/api/topics/lglabs.seed.events", headers=headers_for("viewer"))
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "lglabs.seed.events"
        assert body["partitions"] == 3
        assert "configs" in body
        assert "partitions_detail" in body


# ---------- CREATE ----------

class TestCreateTopic:
    def test_no_auth_403(self, app_client):
        assert app_client.post("/api/topics", json=VALID_PAYLOAD).status_code == 403

    @pytest.mark.parametrize("role", ["support", "viewer"])
    def test_readers_cannot_create(self, app_client, role):
        r = app_client.post("/api/topics", json=VALID_PAYLOAD, headers=headers_for(role))
        assert r.status_code == 403

    @pytest.mark.parametrize("role", ["admin", "operator"])
    def test_writers_can_create(self, app_client, role):
        payload = {**VALID_PAYLOAD, "name": f"lglabs.{role}.created"}
        r = app_client.post("/api/topics", json=payload, headers=headers_for(role))
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == payload["name"]
        assert body["owner"] == "team-platform"
        assert body["description"].startswith("test topic")

    def test_invalid_name_no_lglabs_prefix(self, app_client):
        bad = {**VALID_PAYLOAD, "name": "no-prefix.events"}
        r = app_client.post("/api/topics", json=bad, headers=headers_for("admin"))
        assert r.status_code == 422
        assert r.json()["error"] == "validation_error"

    def test_invalid_owner(self, app_client):
        bad = {**VALID_PAYLOAD, "name": "lglabs.bad.owner", "owner": "ghost-team"}
        r = app_client.post("/api/topics", json=bad, headers=headers_for("admin"))
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_owner"
        assert "valid_owners" in r.json()["details"]

    def test_internal_name_rejected(self, app_client):
        # Regex would reject _-prefix anyway, but test the explicit guard with
        # a name that matches lglabs.* but somehow… we instead test the regex layer:
        bad = {**VALID_PAYLOAD, "name": "_internal"}
        r = app_client.post("/api/topics", json=bad, headers=headers_for("admin"))
        assert r.status_code == 422

    def test_duplicate_topic_409(self, app_client):
        payload = {**VALID_PAYLOAD, "name": "lglabs.dup.events"}
        r1 = app_client.post("/api/topics", json=payload, headers=headers_for("admin"))
        assert r1.status_code == 201
        r2 = app_client.post("/api/topics", json=payload, headers=headers_for("admin"))
        assert r2.status_code == 409
        assert r2.json()["error"] == "topic_already_exists"

    def test_short_description_rejected(self, app_client):
        bad = {**VALID_PAYLOAD, "name": "lglabs.short.desc", "description": "tiny"}
        r = app_client.post("/api/topics", json=bad, headers=headers_for("admin"))
        assert r.status_code == 422

    def test_partitions_out_of_range(self, app_client):
        bad = {**VALID_PAYLOAD, "name": "lglabs.bad.parts", "partitions": 200}
        r = app_client.post("/api/topics", json=bad, headers=headers_for("admin"))
        assert r.status_code == 422


# ---------- UPDATE ----------

class TestUpdateTopic:
    def _seed(self, app_client, name="lglabs.update.target"):
        payload = {**VALID_PAYLOAD, "name": name}
        r = app_client.post("/api/topics", json=payload, headers=headers_for("admin"))
        assert r.status_code == 201
        return name

    def test_readers_cannot_update(self, app_client):
        name = self._seed(app_client)
        r = app_client.patch(f"/api/topics/{name}", json={"retention_ms": 60_000_000}, headers=headers_for("viewer"))
        assert r.status_code == 403

    def test_increase_partitions_ok(self, app_client):
        name = self._seed(app_client)
        r = app_client.patch(f"/api/topics/{name}", json={"partitions": 6}, headers=headers_for("operator"))
        assert r.status_code == 200
        assert r.json()["partitions"] == 6

    def test_decrease_partitions_rejected(self, app_client):
        name = self._seed(app_client)
        r = app_client.patch(f"/api/topics/{name}", json={"partitions": 1}, headers=headers_for("admin"))
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_partitions"

    def test_alter_configs(self, app_client):
        name = self._seed(app_client)
        r = app_client.patch(
            f"/api/topics/{name}",
            json={"retention_ms": 86_400_000, "cleanup_policy": "compact"},
            headers=headers_for("admin"),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["configs"]["retention.ms"] == "86400000"
        assert body["configs"]["cleanup.policy"] == "compact"

    def test_update_owner_invalid(self, app_client):
        name = self._seed(app_client)
        r = app_client.patch(f"/api/topics/{name}", json={"owner": "ghost"}, headers=headers_for("admin"))
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_owner"


# ---------- DELETE ----------

class TestDeleteTopic:
    def _seed(self, app_client, name="lglabs.delete.target"):
        payload = {**VALID_PAYLOAD, "name": name}
        app_client.post("/api/topics", json=payload, headers=headers_for("admin"))
        return name

    def test_readers_cannot_delete(self, app_client):
        name = self._seed(app_client)
        r = app_client.delete(f"/api/topics/{name}",
                              headers={**headers_for("support"), "X-Confirm-Resource": name})
        assert r.status_code == 403

    def test_missing_confirm_header_409(self, app_client):
        name = self._seed(app_client)
        r = app_client.delete(f"/api/topics/{name}", headers=headers_for("admin"))
        assert r.status_code == 409
        assert r.json()["error"] == "confirmation_required"

    def test_wrong_confirm_value_409(self, app_client):
        name = self._seed(app_client)
        r = app_client.delete(
            f"/api/topics/{name}",
            headers={**headers_for("admin"), "X-Confirm-Resource": "wrong"},
        )
        assert r.status_code == 409

    def test_delete_internal_protected(self, app_client):
        r = app_client.delete(
            "/api/topics/__consumer_offsets",
            headers={**headers_for("admin"), "X-Confirm-Resource": "__consumer_offsets"},
        )
        assert r.status_code == 403
        assert r.json()["error"] == "internal_topic_protected"

    def test_delete_ok_with_confirm(self, app_client):
        name = self._seed(app_client)
        r = app_client.delete(
            f"/api/topics/{name}",
            headers={**headers_for("admin"), "X-Confirm-Resource": name},
        )
        assert r.status_code == 204
        # And it's gone
        r2 = app_client.get(f"/api/topics/{name}", headers=headers_for("viewer"))
        assert r2.status_code == 404


# ---------- EXPORT (US-9) ----------

class TestExportTopic:
    def test_readers_cannot_export(self, app_client):
        r = app_client.get("/api/topics/lglabs.seed.events/export", headers=headers_for("viewer"))
        assert r.status_code == 403

    def test_writer_can_export(self, app_client):
        r = app_client.get("/api/topics/lglabs.seed.events/export", headers=headers_for("operator"))
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")
        assert 'attachment; filename="lglabs.seed.events.json"' in r.headers["content-disposition"]
        body = r.json()
        assert body["topic"]["name"] == "lglabs.seed.events"
        assert "acl_metadata_associated" in body
        assert "schemas_associated" in body
