"""Contract tests for ACL-metadata endpoints (design.md §3.5)."""

from __future__ import annotations

from .helpers import headers_for


def _payload(**overrides):
    base = {
        "principal": "User:team-payments",
        "host": "*",
        "operation": "READ",
        "resource_type": "TOPIC",
        "resource_name": "lglabs.orders.",
        "pattern_type": "PREFIXED",
        "permission_type": "ALLOW",
        "note": "smoke entry",
    }
    base.update(overrides)
    return base


# ---------- LIST / GET ----------

def test_acl_list_empty(app_client):
    r = app_client.get("/api/acl-metadata", headers=headers_for("viewer"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 50}


def test_acl_list_filters_and_pagination(app_client):
    # seed 3 entries
    for op in ("READ", "WRITE", "DESCRIBE"):
        r = app_client.post("/api/acl-metadata",
                            json=_payload(operation=op),
                            headers=headers_for("admin"))
        assert r.status_code == 201, r.text

    # filter by operation-agnostic principal substring
    r = app_client.get("/api/acl-metadata?principal=team-payments",
                       headers=headers_for("support"))
    assert r.status_code == 200
    assert r.json()["total"] == 3

    # filter that matches nothing
    r = app_client.get("/api/acl-metadata?principal=nope",
                       headers=headers_for("support"))
    assert r.json()["total"] == 0

    # page_size = 2 → first page has 2, second has 1
    r1 = app_client.get("/api/acl-metadata?page=1&page_size=2",
                        headers=headers_for("viewer"))
    r2 = app_client.get("/api/acl-metadata?page=2&page_size=2",
                        headers=headers_for("viewer"))
    assert len(r1.json()["items"]) == 2
    assert len(r2.json()["items"]) == 1


def test_acl_get_by_id(app_client):
    cr = app_client.post("/api/acl-metadata", json=_payload(),
                         headers=headers_for("admin"))
    assert cr.status_code == 201, cr.text
    created = cr.json()
    r = app_client.get(f"/api/acl-metadata/{created['id']}",
                       headers=headers_for("viewer"))
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_acl_get_unknown_404(app_client):
    r = app_client.get("/api/acl-metadata/00000000-0000-0000-0000-000000000000",
                       headers=headers_for("admin"))
    assert r.status_code == 404
    assert r.json()["error"] == "acl_metadata_not_found"


# ---------- CREATE ----------

def test_acl_create_201_and_persists(app_client):
    r = app_client.post("/api/acl-metadata", json=_payload(),
                        headers=headers_for("admin"))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["principal"] == "User:team-payments"
    assert body["created_by"] == "lglabsadmin"
    assert "id" in body and len(body["id"]) == 36

    r2 = app_client.get(f"/api/acl-metadata/{body['id']}",
                        headers=headers_for("admin"))
    assert r2.status_code == 200


def test_acl_create_duplicate_409(app_client):
    p = _payload()
    r1 = app_client.post("/api/acl-metadata", json=p, headers=headers_for("admin"))
    assert r1.status_code == 201
    r2 = app_client.post("/api/acl-metadata", json=p, headers=headers_for("admin"))
    assert r2.status_code == 409
    assert r2.json()["error"] == "acl_metadata_duplicate"


def test_acl_create_invalid_principal_422(app_client):
    # field_validator runs before our domain validator → 422 RequestValidation
    r = app_client.post("/api/acl-metadata",
                        json=_payload(principal="nobody"),
                        headers=headers_for("admin"))
    assert r.status_code == 422
    assert r.json()["error"] == "validation_error"


def test_acl_create_empty_resource_422(app_client):
    r = app_client.post("/api/acl-metadata",
                        json=_payload(resource_name="   "),
                        headers=headers_for("admin"))
    assert r.status_code == 422


def test_acl_create_invalid_operation_422(app_client):
    r = app_client.post("/api/acl-metadata",
                        json=_payload(operation="HACK"),
                        headers=headers_for("admin"))
    assert r.status_code == 422


# ---------- UPDATE ----------

def test_acl_update_replaces_fields(app_client):
    created = app_client.post("/api/acl-metadata", json=_payload(),
                              headers=headers_for("admin")).json()
    new = _payload(note="changed", principal="Group:operators")
    r = app_client.put(f"/api/acl-metadata/{created['id']}", json=new,
                       headers=headers_for("admin"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["note"] == "changed"
    assert body["principal"] == "Group:operators"
    # created_at/by stay the same
    assert body["created_by"] == created["created_by"]


def test_acl_update_unknown_404(app_client):
    r = app_client.put("/api/acl-metadata/00000000-0000-0000-0000-000000000000",
                       json=_payload(), headers=headers_for("admin"))
    assert r.status_code == 404


def test_acl_update_into_duplicate_409(app_client):
    a = app_client.post("/api/acl-metadata", json=_payload(operation="READ"),
                        headers=headers_for("admin")).json()
    b = app_client.post("/api/acl-metadata", json=_payload(operation="WRITE"),
                        headers=headers_for("admin")).json()
    # try updating b to collide with a
    r = app_client.put(f"/api/acl-metadata/{b['id']}",
                       json=_payload(operation="READ"),
                       headers=headers_for("admin"))
    assert r.status_code == 409
    assert r.json()["error"] == "acl_metadata_duplicate"
    assert a["id"] != b["id"]


# ---------- DELETE ----------

def test_acl_delete_requires_confirm_header(app_client):
    created = app_client.post("/api/acl-metadata", json=_payload(),
                              headers=headers_for("admin")).json()

    r1 = app_client.delete(f"/api/acl-metadata/{created['id']}",
                           headers=headers_for("admin"))
    assert r1.status_code == 409
    assert r1.json()["error"] == "confirmation_required"

    r2 = app_client.delete(
        f"/api/acl-metadata/{created['id']}",
        headers={**headers_for("admin"), "X-Confirm-Resource": "wrong"},
    )
    assert r2.status_code == 409

    r3 = app_client.delete(
        f"/api/acl-metadata/{created['id']}",
        headers={**headers_for("admin"), "X-Confirm-Resource": created["id"]},
    )
    assert r3.status_code == 204


def test_acl_delete_unknown_404(app_client):
    fake = "00000000-0000-0000-0000-000000000000"
    r = app_client.delete(
        f"/api/acl-metadata/{fake}",
        headers={**headers_for("admin"), "X-Confirm-Resource": fake},
    )
    assert r.status_code == 404


# ---------- Authz (BFF defense-in-depth) ----------

def test_acl_role_matrix_create(app_client):
    p = _payload()
    # admin: 201 ; operator/support/viewer: 403 ; anon: 403
    assert app_client.post("/api/acl-metadata", json=p,
                           headers=headers_for("admin")).status_code == 201
    for r in ("operator", "support", "viewer", None):
        resp = app_client.post("/api/acl-metadata", json=_payload(operation="ALL"),
                               headers=headers_for(r))
        assert resp.status_code == 403, f"role={r} got {resp.status_code}: {resp.text}"


def test_acl_role_matrix_read(app_client):
    # All authenticated roles can list and get
    created = app_client.post("/api/acl-metadata", json=_payload(),
                              headers=headers_for("admin")).json()
    for r in ("admin", "operator", "support", "viewer"):
        rl = app_client.get("/api/acl-metadata", headers=headers_for(r))
        rg = app_client.get(f"/api/acl-metadata/{created['id']}",
                            headers=headers_for(r))
        assert rl.status_code == 200
        assert rg.status_code == 200


def test_acl_role_matrix_update_delete(app_client):
    created = app_client.post("/api/acl-metadata", json=_payload(),
                              headers=headers_for("admin")).json()
    aid = created["id"]
    for role in ("operator", "support", "viewer"):
        ru = app_client.put(f"/api/acl-metadata/{aid}", json=_payload(note="x"),
                            headers=headers_for(role))
        assert ru.status_code == 403
        rd = app_client.delete(
            f"/api/acl-metadata/{aid}",
            headers={**headers_for(role), "X-Confirm-Resource": aid},
        )
        assert rd.status_code == 403


# ---------- Summary integration ----------

def test_summary_acl_count_increases(app_client):
    s0 = app_client.get("/api/summary", headers=headers_for("admin")).json()
    assert s0["acl_metadata_total"] == 0
    app_client.post("/api/acl-metadata", json=_payload(),
                    headers=headers_for("admin"))
    s1 = app_client.get("/api/summary", headers=headers_for("admin")).json()
    assert s1["acl_metadata_total"] == 1


# ---------- Topic export wiring ----------

def test_topic_export_includes_matching_acls(app_client):
    # Create a topic via API (uses fake kafka repo)
    topic = "lglabs.orders.events"
    payload = {
        "name": topic,
        "partitions": 3,
        "replication_factor": 1,
        "configs": {},
        "owner": "team-platform",
        "description": "phase E export wiring test",
        "environment": "dev",
    }
    rt = app_client.post("/api/topics", json=payload, headers=headers_for("admin"))
    assert rt.status_code == 201, rt.text

    # Two ACLs that should match `lglabs.orders.events`:
    # 1) PREFIXED on 'lglabs.orders.'
    # 2) LITERAL  on the exact topic
    app_client.post("/api/acl-metadata", json=_payload(
        resource_name="lglabs.orders.", pattern_type="PREFIXED", operation="READ",
    ), headers=headers_for("admin"))
    app_client.post("/api/acl-metadata", json=_payload(
        resource_name=topic, pattern_type="LITERAL", operation="WRITE",
        principal="Group:operators",
    ), headers=headers_for("admin"))
    # And one that should NOT match (different prefix)
    app_client.post("/api/acl-metadata", json=_payload(
        resource_name="lglabs.payments.", pattern_type="PREFIXED",
        operation="ALL", principal="User:team-billing",
    ), headers=headers_for("admin"))

    r = app_client.get(f"/api/topics/{topic}/export", headers=headers_for("admin"))
    assert r.status_code == 200, r.text
    body = r.json()
    assoc = body["acl_metadata_associated"]
    assert len(assoc) == 2
    ops = {a["operation"] for a in assoc}
    assert ops == {"READ", "WRITE"}
