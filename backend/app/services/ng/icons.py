"""Icons: the LaMetric catalogue, and installing them on a display.

The good news of the AWTRIX NG migration is that this file barely changed. The
icon identifier is still the file name without its extension, so every icon
chosen on the previous project still resolves. Only the two device routes moved,
and they are now part of the published API instead of being read out of the
firmware's web UI:

    GET  /api/v1/files?dir=/ICONS            lists what is installed
    POST /api/v1/files?dir=/ICONS            installs one, multipart,
                                             field "file" (was "image")

LaMetric serves the file at
`https://developer.lametric.com/content/apps/icon_thumbs/<id>`. Animated icons
come as GIF and are stored untouched; still ones come as **PNG**, which the
firmware cannot read at all, so they are converted to a single-frame GIF.

One format on the device, therefore one extension, therefore `icon_filename`
needs no cases.

NG raised the ceiling to 41x8 pixels, from 32x8. Nothing here enforces it: the
gallery's icons are 8x8 and the limit only matters for a file a user supplies.
"""

import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.core.errors import AwtrixNgError
from app.core.http import build_client

log = logging.getLogger(__name__)

CATALOGUE_URL = "https://developer.lametric.com/api/v2/icons"
ICON_URL = "https://developer.lametric.com/content/apps/icon_thumbs/{icon_id}"

#: Every thumbnail URL in the gallery follows this, checked against all 71 858
#: of them. Derived rather than stored: keeping the string cost 8 MB of
#: resident memory for something an integer already determines.
THUMBNAIL_URL = (
    "https://developer.lametric.com/content/apps/icon_thumbs/{icon_id}_icon_thumb_sm.png"
)

#: The catalogue only pages; it has no search, so the app fetches it and
#: searches titles itself.
PAGE_SIZE = 2000

#: A guard against an upstream change looping forever, not a cap on the
#: gallery. It was 12, which stopped at 24 000 of the 71 858 icons — two
#: thirds of the gallery were invisible in the picker, and the only way to use
#: one of them was to know its number and type it in. Found when "Fuel ani"
#: (55274, page 26) could not be searched for.
MAX_PAGES = 48

#: Pages fetched at once. Sequentially the whole gallery took 24 seconds,
#: which is a long time to stare at an empty icon picker; six at a time brings
#: it under five. Not unbounded: thirty-six simultaneous requests at someone
#: else's free service is not neighbourly.
CONCURRENT_PAGES = 6


@dataclass(frozen=True, slots=True)
class IconSummary:
    id: int
    title: str
    #: True for an animated GIF. LaMetric calls these "movie".
    animated: bool

    @property
    def filename(self) -> str:
        return f"{self.id}.{'gif' if self.animated else 'jpg'}"

    @property
    def thumbnail(self) -> str:
        """Preview image, for the picker. Served by LaMetric, never redistributed."""
        return THUMBNAIL_URL.format(icon_id=self.id)


def _summarise(entry: dict) -> IconSummary | None:
    try:
        return IconSummary(
            id=int(entry["id"]),
            title=str(entry.get("title") or entry["id"]),
            animated=entry.get("type") == "movie",
        )
    except (KeyError, TypeError, ValueError):
        return None


class LametricCatalogue:
    """The LaMetric gallery, fetched once and searched locally."""

    def __init__(self) -> None:
        self._icons: list[IconSummary] | None = None

    async def load(self, client: httpx.AsyncClient | None = None) -> list[IconSummary]:
        if self._icons is not None:
            return self._icons

        own = client is None
        http = client or build_client()
        icons: list[IconSummary] = []
        try:
            # The first page alone, before fanning out: a gallery that fits
            # in one page must cost one request, not a whole wave of them.
            first = await self._page(http, 1)
            icons.extend(icon for entry in first if (icon := _summarise(entry)))

            if len(first) >= PAGE_SIZE:
                for start in range(2, MAX_PAGES + 1, CONCURRENT_PAGES):
                    wave = range(start, min(start + CONCURRENT_PAGES, MAX_PAGES + 1))
                    pages = await asyncio.gather(*(self._page(http, n) for n in wave))
                    for entries in pages:
                        icons.extend(icon for entry in entries if (icon := _summarise(entry)))
                    # A short page is the last one. The rest of the wave came
                    # back empty and cost one round trip, which is the price of
                    # not walking the gallery one page at a time.
                    if any(len(entries) < PAGE_SIZE for entries in pages):
                        break
        except (httpx.HTTPError, ValueError) as exc:
            if not icons:
                raise AwtrixNgError(
                    f"Could not reach the LaMetric icon gallery: {exc or type(exc).__name__}",
                    code="icons.catalogue_unreachable",
                ) from exc
            log.warning("icon catalogue partially loaded: %s", exc)
        finally:
            if own:
                await http.aclose()

        self._icons = icons
        log.info(
            "loaded %d LaMetric icons (%d animated)",
            len(icons),
            sum(1 for i in icons if i.animated),
        )
        return icons

    @staticmethod
    async def _page(client: httpx.AsyncClient, page: int) -> list[dict]:
        """One page, or nothing. A single bad page must not lose the rest."""
        response = await client.get(CATALOGUE_URL, params={"page": page, "page_size": PAGE_SIZE})
        if response.status_code >= 400:
            return []
        return (response.json() or {}).get("data") or []

    async def search(
        self, query: str, *, animated_only: bool = True, limit: int = 60
    ) -> list[IconSummary]:
        """Search titles. Animated by default: on a 32x8 matrix a moving icon
        carries meaning that a word cannot fit."""
        icons = await self.load()
        needle = query.strip().lower()
        found = [
            icon
            for icon in icons
            if (not animated_only or icon.animated) and (not needle or needle in icon.title.lower())
        ]
        found.sort(key=lambda icon: _rank(icon, needle))
        return found[:limit]

    def forget(self) -> None:
        self._icons = None


def _rank(icon: IconSummary, needle: str) -> tuple[int, int, str]:
    """Order search results the way someone looking for an icon expects.

    Exact title first, then titles that start with the query, then the rest;
    within a tier the shortest title wins. Without the length tier, searching
    "rain" answers "RAINBOW APPLE LOGO" before "Rain".
    """
    title = icon.title.lower()
    if title == needle:
        tier = 0
    elif title.startswith(needle):
        tier = 1
    else:
        tier = 2
    return tier, len(icon.title), title


#: One catalogue per process. It is immutable upstream data.
catalogue = LametricCatalogue()


async def download(icon_id: int, client: httpx.AsyncClient) -> tuple[bytes, bool]:
    """Fetch an icon from LaMetric. Returns (bytes, animated)."""
    try:
        response = await client.get(ICON_URL.format(icon_id=icon_id))
    except httpx.HTTPError as exc:
        raise AwtrixNgError(
            f"Could not download icon {icon_id}: {exc or type(exc).__name__}",
            code="icons.download_failed",
            params={"icon": icon_id},
        ) from exc

    if response.status_code >= 400:
        raise AwtrixNgError(
            f"Icon {icon_id} does not exist in the LaMetric gallery.",
            code="icons.not_found",
            params={"icon": icon_id},
        )

    content_type = response.headers.get("content-type", "")
    return response.content, content_type.startswith("image/gif")


def icon_filename(icon_id: int) -> str:
    """Always .gif — stills are converted on the way in (see `to_gif`)."""
    return f"{icon_id}.gif"


def to_gif(payload: bytes) -> bytes:
    """Turn a still icon into the one format the device reads.

    The firmware takes 8x8 JPG and GIF up to 32x8, and nothing else; the
    gallery hands out PNG for everything that is not animated. Without this,
    a perfectly good icon is downloaded, stored, and never drawn.

    Transparency is flattened onto black rather than kept: AWTRIX GIFs carry
    none, and the matrix behind the icon is black anyway.
    """
    import io

    from PIL import Image

    try:
        with Image.open(io.BytesIO(payload)) as source:
            frame = source.convert("RGBA")
            flat = Image.new("RGB", frame.size, (0, 0, 0))
            flat.paste(frame, mask=frame.getchannel("A"))
            out = io.BytesIO()
            flat.convert("P", palette=Image.Palette.ADAPTIVE, colors=256).save(out, format="GIF")
            return out.getvalue()
    except (OSError, ValueError) as exc:
        raise AwtrixNgError(
            f"Could not convert the icon: {exc or type(exc).__name__}",
            code="icons.conversion_failed",
        ) from exc
