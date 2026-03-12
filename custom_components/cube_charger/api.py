from __future__ import annotations
from typing import Any

class CubeApi:
    """Placeholder API client for Cube Charging.

    Replace methods with real HTTP calls to your portal.
    """

    def __init__(self, base_url: str, bearer_token: str, verify_ssl: bool = True) -> None:
        self.base_url = base_url.rstrip('/')
        self._token = bearer_token
        self.verify_ssl = verify_ssl

    async def ping(self) -> dict[str, Any]:
        """Return a minimal health payload.
        Replace with a real call when available.
        """
        return {"ok": True}
