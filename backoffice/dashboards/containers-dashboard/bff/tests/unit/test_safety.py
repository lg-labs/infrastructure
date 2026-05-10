"""Unit tests for denylist + redact (B.3.3)."""
from __future__ import annotations

import pytest

from app.errors import ProtectedResource
from app.safety.denylist import DENYLIST, assert_not_protected, is_protected
from app.safety.redact import REDACTED, is_secret_key, redact_env_dict, redact_env_list


# ---------- denylist ----------

@pytest.mark.parametrize(
    "name",
    [
        "lg-infra-backoffice-keycloak",
        "lg-infra-backoffice-gateway",
        "lg-infra-backoffice-proxy",
        "lg-infra-backoffice-portainer",
        "lg-infra-backoffice-containers-dashboard-bff",
        "lg-infra-backoffice-containers-dashboard-fe",
    ],
)
def test_denylist_blocks_known_backoffice_names(name: str) -> None:
    assert is_protected(name) is True
    with pytest.raises(ProtectedResource):
        assert_not_protected(name)


def test_denylist_does_not_block_other_names() -> None:
    assert is_protected("lg-infra-elk-kibana-1") is False
    assert is_protected("random-container") is False
    assert is_protected("") is False
    assert is_protected(None) is False


def test_denylist_is_immutable() -> None:
    assert isinstance(DENYLIST, frozenset)


def test_assert_not_protected_passes_for_safe_name() -> None:
    # Should not raise
    assert_not_protected("lg-infra-elk-kibana-1")
    assert_not_protected(None)


# ---------- redact ----------

@pytest.mark.parametrize(
    "key,expected",
    [
        ("DB_PASSWORD", True),
        ("MY_SECRET", True),
        ("API_TOKEN", True),
        ("PRIVATE_KEY", True),
        ("AWS_CREDENTIAL", True),
        ("password", True),
        ("Token", True),
        ("NODE_ENV", False),
        ("PORT", False),
        ("HOSTNAME", False),
        ("", False),
    ],
)
def test_secret_key_detection(key: str, expected: bool) -> None:
    assert is_secret_key(key) is expected


def test_redact_env_list_redacts_secrets() -> None:
    raw = ["NODE_ENV=production", "DB_PASSWORD=hunter2", "SECRET_KEY=topsecret", "PORT=5432"]
    out = redact_env_list(raw)

    by_key = {e["key"]: e["value"] for e in out}
    assert by_key["NODE_ENV"] == "production"
    assert by_key["PORT"] == "5432"
    assert by_key["DB_PASSWORD"] == REDACTED
    assert by_key["SECRET_KEY"] == REDACTED


def test_redact_env_list_preserves_order() -> None:
    raw = ["A=1", "TOKEN=2", "B=3"]
    out = redact_env_list(raw)
    assert [e["key"] for e in out] == ["A", "TOKEN", "B"]


def test_redact_env_list_handles_value_with_equals() -> None:
    raw = ["URL=https://x.com?token=abc&y=1"]
    out = redact_env_list(raw)
    # 'URL' is not a secret key — value preserved verbatim incl. embedded '='
    assert out == [{"key": "URL", "value": "https://x.com?token=abc&y=1"}]


def test_redact_env_list_handles_no_equals() -> None:
    raw = ["NOEQUALS"]
    out = redact_env_list(raw)
    assert out == [{"key": "NOEQUALS", "value": ""}]


def test_redact_env_dict() -> None:
    out = redact_env_dict({"DB_PASSWORD": "x", "PORT": "5432", "API_KEY": "y"})
    assert out == {"DB_PASSWORD": REDACTED, "PORT": "5432", "API_KEY": REDACTED}


def test_redact_env_list_empty() -> None:
    assert redact_env_list([]) == []
    assert redact_env_list(None) == []  # type: ignore[arg-type]
