"""Confirmation header enforcement (design §6.5).

Mutating endpoints (except start) require the client to echo the resource name
in `X-Confirm-Resource` to prevent accidental clicks. Mismatch / missing → 409.
"""
from __future__ import annotations

from fastapi import Request

from ..errors import ConfirmationRequired

CONFIRM_HEADER = "x-confirm-resource"


def assert_confirm_resource(request: Request, expected: str) -> None:
    """Raise ConfirmationRequired (409) unless the header echoes ``expected``.

    Comparison is case-sensitive on the resource name (Docker is case-sensitive).
    """
    given = request.headers.get(CONFIRM_HEADER)
    if not given or given != expected:
        raise ConfirmationRequired(expected)
