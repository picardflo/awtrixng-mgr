"""Domain errors.

Every message reaching the UI carries a stable ``code``. The frontend
translates the code; the English ``message`` stays as a fallback so the API
remains readable on its own, from ``/api/docs`` or from curl.

Adding a language must never require touching the backend.
"""

from typing import Any


class AwtrixNgError(Exception):
    """Base error. ``message`` is English, ``code`` is what gets translated."""

    code: str = "error.unknown"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.params: dict[str, Any] = params or {}


class UnsafeUrlError(AwtrixNgError):
    """URL rejected by the outbound guardrails."""

    code = "error.unsafe_url"


class DeviceUnreachableError(AwtrixNgError):
    """The display did not answer, or answered something unexpected."""

    code = "error.device_unreachable"


class DeviceRejectedError(AwtrixNgError):
    """The firmware understood the request and refused it — HTTP 422.

    AWTRIX 3 had no equivalent: it ignored in silence whatever it did not
    understand, so a typo in a payload key simply produced a display that was
    subtly wrong. NG answers with the offending field by name, which is worth
    a distinct error so the field can reach the user instead of being
    flattened into "the device is unreachable".
    """

    code = "error.device_rejected"

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        code: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, params={**(params or {}), "field": field})
        self.field = field


class ConnectorError(AwtrixNgError):
    """An upstream service failed. Must never bring the scheduler down."""

    code = "error.connector"
