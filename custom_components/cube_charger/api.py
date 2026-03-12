
from __future__ import annotations
import aiohttp
from typing import Any, Optional

class CubeApi:
    def __init__(self, base_url: str, bearer_token: str, verify_ssl: bool=True):
        self.base_url = base_url.rstrip("/")
        self._token = bearer_token
        self.verify_ssl = verify_ssl

    def _headers(self) -> dict[str, str]:
        return {"Accept": "application/json", "Authorization": f"Bearer {self._token}"}

    async def list_chargeboxes(self) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/v1/CubeCharging/chargebox/details"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=self._headers(), ssl=self.verify_ssl, timeout=20) as r:
                r.raise_for_status()
                data = await r.json()
                return data if isinstance(data, list) else []

    async def remote_start(self, chargebox_id: str, connector_id: int, idtag: str) -> dict[str, Any]:
        url = f"{self.base_url}/api/v1/CubeCharging/chargebox/remote-start"
        payload = {"chargeBoxId": chargebox_id, "connectorId": connector_id, "idTag": idtag}
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, headers=self._headers(), ssl=self.verify_ssl, timeout=20) as r:
                r.raise_for_status()
                return await r.json()

    async def remote_stop(self, chargebox_id: str, *, transaction_id: int | None = None, connector_id: int | None = None) -> dict[str, Any]:
        """Stop an active session. Requires chargeBoxId + (transactionId or connectorId)."""
        if transaction_id is None and connector_id is None:
            raise ValueError("remote_stop requires transaction_id or connector_id")
        url = f"{self.base_url}/api/v1/CubeCharging/chargebox/remote-stop"
        payload: dict[str, Any] = {"chargeBoxId": chargebox_id}
        if transaction_id is not None:
            payload["transactionId"] = int(transaction_id)
        else:
            payload["connectorId"] = int(connector_id)  # type: ignore[arg-type]
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, headers=self._headers(), ssl=self.verify_ssl, timeout=20) as r:
                r.raise_for_status()
                return await r.json()

    async def active_transactions(self, chargebox_id: str, offset: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/v1/CubeCharging/chargebox/transactions/active"
        params = {"chargeBoxId": chargebox_id, "offset": offset, "limit": limit}
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, headers=self._headers(), ssl=self.verify_ssl, timeout=20) as r:
                r.raise_for_status()
                data = await r.json()
                return data if isinstance(data, list) else []

    async def history_transactions(
        self,
        start_iso: Optional[str] = None,
        end_iso: Optional[str] = None,
        chargebox_id: Optional[str] = None,
        offset: int = 0,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/v1/CubeCharging/chargebox/transactions/history"
        params = {"offset": offset, "limit": limit}
        if start_iso: params["startDate"] = start_iso
        if end_iso: params["endDate"] = end_iso
        if chargebox_id: params["chargeBoxId"] = chargebox_id
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, headers=self._headers(), ssl=self.verify_ssl, timeout=30) as r:
                r.raise_for_status()
                data = await r.json()
                return data if isinstance(data, list) else []
