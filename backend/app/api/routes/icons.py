"""Icon catalogue and per-device icon management.

Built on endpoints that are absent from the AWTRIX API reference and were read
from the firmware's own web interface (see app/services/awtrix/icons.py).
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import DeviceDep, client_for
from app.core.errors import AwtrixNgError
from app.services.ng.icons import IconSummary, catalogue

log = logging.getLogger(__name__)
router = APIRouter(tags=["icons"])


class Icon(BaseModel):
    id: int
    title: str
    animated: bool
    thumbnail: str
    filename: str

    @classmethod
    def of(cls, summary: IconSummary) -> "Icon":
        return cls(
            id=summary.id,
            title=summary.title,
            animated=summary.animated,
            thumbnail=summary.thumbnail,
            filename=summary.filename,
        )


class InstallResult(BaseModel):
    ok: bool
    message: str
    code: str
    filename: str | None = None


@router.get("/icons", response_model=list[Icon])
async def search_icons(
    q: Annotated[str, Query(description="Matched against the icon title")] = "",
    animated: Annotated[bool, Query(description="Animated icons only")] = True,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
) -> list[Icon]:
    """Search the LaMetric gallery.

    The gallery API has no search of its own, so awtrixng-mgr fetches the
    catalogue once and matches titles itself. Animated icons are the default:
    a moving icon says more on a 32x8 matrix than a word does.
    """
    found = await catalogue.search(q, animated_only=animated, limit=limit)
    return [Icon.of(icon) for icon in found]


@router.get("/devices/{device_id}/icons", response_model=list[str])
async def list_device_icons(device: DeviceDep) -> list[str]:
    """File names present in the device's ICONS folder."""
    client = client_for(device)
    try:
        return await client.list_icons()
    finally:
        await client.aclose()


@router.post("/devices/{device_id}/icons/{icon_id}", response_model=InstallResult)
async def install_icon(device: DeviceDep, icon_id: int) -> InstallResult:
    """Copy one LaMetric icon onto the device.

    Widgets install what they need on their own, so this is for the icon
    picker: letting someone browse and push an icon before using it.
    """
    client = client_for(device)
    try:
        await client.ensure_icon(str(icon_id))
    except AwtrixNgError as exc:
        return InstallResult(ok=False, message=exc.message, code=exc.code)
    finally:
        await client.aclose()

    return InstallResult(
        ok=True,
        message=f"Icon {icon_id} installed.",
        code="icons.installed",
        filename=f"{icon_id}.gif",
    )
