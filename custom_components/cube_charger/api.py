"""Cube Charger API client.

Hier plaatsen we later de echte HTTP-calls naar de Cube Charging endpoints.
Voor nu alleen een skeleton met type hints.
"""

from __future__ import annotations
from typing import Any


class CubeApi:
    """Eenvoudige placeholder voor de Cube API client."""

    def __init__(self, base_url: str, bearer_token: str, verify_ssl: bool = True) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = bearer_token
        self.verify_ssl = verify_ssl

    async def ping(self) -> dict[str, Any]:
        """Placeholder-methode om later connectiviteit te testen."""
        return {"ok": True}
