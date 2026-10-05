"""Transport towards an AWTRIX NG display.

The only layer in the project that speaks HTTP to a display. The abstraction
stays deliberately thin: a future MqttTransport would implement the same
protocol, but nothing is built for it today.

Three things differ from the AWTRIX 3 transport this replaces, all measured:

- **`Content-Type: application/json` is mandatory.** Sending a body without
  it answers 415, where AWTRIX 3 accepted anything.
- **An empty body is no longer a deletion.** AWTRIX 3 deleted a Custom App by
  posting nothing to it; NG has `DELETE`, so `json=None` loses its old second
  meaning and the ambiguity goes with it.
- **422 is a real answer, not a failure.** The firmware names the field it
  refused — `{"error": {"code": "validationFailed", "message": "unknown key
  \\"color\\"", "field": "color"}}`. Flattening that into "the device is
  unreachable" would throw away the one thing worth showing the user, so it
  gets its own exception carrying the field.
"""

import logging
from typing import Any, Protocol

import httpx

from app.core.errors import DeviceRejectedError, DeviceUnreachableError
from app.core.http import build_client

log = logging.getLogger(__name__)


class NgTransport(Protocol):
    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any: ...

    async def request(
        self, method: str, path: str, *, json: Any = None, params: dict[str, Any] | None = None
    ) -> Any: ...

    async def post_file(
        self,
        path: str,
        *,
        field: str,
        filename: str,
        content: bytes,
        content_type: str,
        params: dict[str, Any] | None = None,
    ) -> Any: ...

    async def aclose(self) -> None: ...


class HttpTransport:
    """HTTP REST transport — the only one implemented today."""

    #: Every route of the firmware API hangs off this. Kept in one place so a
    #: future /api/v2 is a one-line change rather than a grep.
    PREFIX = "/api/v1"

    def __init__(
        self,
        host: str,
        port: int = 80,
        *,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._base = f"http://{host}:{port}"
        # NG ships with authEnabled false; a display only needs credentials
        # once its owner turns authentication on.
        auth = (username, password or "") if username else None
        self._client = build_client(base_url=self._base, auth=auth)

    # -- Requests --------------------------------------------------------------

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return await self.request("GET", path, params=params)

    async def request(
        self, method: str, path: str, *, json: Any = None, params: dict[str, Any] | None = None
    ) -> Any:
        url = f"{self.PREFIX}{path}"
        kwargs: dict[str, Any] = {"params": params}
        if json is not None:
            # Explicit rather than relying on httpx: the 415 this avoids is
            # silent-looking, the request simply never takes effect.
            kwargs["json"] = json
            kwargs["headers"] = {"Content-Type": "application/json"}

        try:
            response = await self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise self._unreachable(exc) from exc

        return self._parse(response, url)

    async def post_file(
        self,
        path: str,
        *,
        field: str,
        filename: str,
        content: bytes,
        content_type: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Multipart upload. The field is `file`, where AWTRIX 3 used `image`."""
        url = f"{self.PREFIX}{path}"
        try:
            response = await self._client.post(
                url, params=params, files={field: (filename, content, content_type)}
            )
        except httpx.HTTPError as exc:
            raise self._unreachable(exc) from exc
        return self._parse(response, url)

    # -- Responses -------------------------------------------------------------

    def _parse(self, response: httpx.Response, url: str) -> Any:
        if response.status_code == 401:
            raise self._auth_failed()

        if response.status_code == 422:
            raise self._rejected(response, url)

        if response.status_code >= 400:
            raise DeviceUnreachableError(
                f"HTTP {response.status_code} on {url}.",
                code="device.http_error",
                params={"path": url, "status": response.status_code},
            )

        if not response.content:
            # DELETE and some PUTs answer with nothing at all.
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise DeviceUnreachableError(
                f"Non-JSON response on {url}: is this really an AWTRIX NG display?",
                code="device.not_awtrix_ng",
                params={"path": url},
            ) from exc

    @staticmethod
    def _rejected(response: httpx.Response, url: str) -> DeviceRejectedError:
        """Turn the firmware's own validation error into ours, field included.

        A 422 whose body is not the expected shape still has to come out as a
        rejection rather than as an unreachable device: the request got there,
        it was understood, and it was refused.
        """
        detail: dict[str, Any] = {}
        try:
            body = response.json()
            if isinstance(body, dict) and isinstance(body.get("error"), dict):
                detail = body["error"]
        except ValueError:
            pass

        field = detail.get("field")
        message = detail.get("message") or "the display refused the request"
        return DeviceRejectedError(
            f"The display refused {url}: {message}"
            + (f" (field {field})" if field else ""),
            field=field,
            code="device.rejected",
            params={"path": url, "reason": message},
        )

    def _unreachable(self, exc: Exception) -> DeviceUnreachableError:
        # Several httpx errors, ConnectTimeout among them, stringify to "".
        # Falling back to the class name keeps the message informative.
        reason = str(exc) or type(exc).__name__
        return DeviceUnreachableError(
            f"{self._base} is unreachable: {reason}",
            code="device.unreachable",
            params={"target": self._base, "reason": reason},
        )

    @staticmethod
    def _auth_failed() -> DeviceUnreachableError:
        return DeviceUnreachableError(
            "Authentication rejected: check the username and password.",
            code="device.auth_failed",
        )

    async def aclose(self) -> None:
        await self._client.aclose()
