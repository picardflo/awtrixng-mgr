"""Icons: LaMetric catalogue, and installing onto a device.

Every endpoint exercised here is undocumented — read from the firmware source
and verified on a v0.98 device — so these tests also serve as the written
record of what was observed.
"""

import httpx
import pytest
import respx

from app.core.errors import AwtrixNgError
from app.services.ng import icons
from app.services.ng.client import NgClient
from app.services.ng.icons import CATALOGUE_URL, LametricCatalogue, download
from app.services.ng.transport import HttpTransport

BASE = "http://awtrix.test:80"
GIF = b"GIF89a" + b"\x00" * 40

CATALOGUE_PAGE = {
    "data": [
        {"id": 12182, "title": "Clear Day", "type": "movie",
         "thumb": {"small": "https://lametric/12182_sm.png"}},
        {"id": 12197, "title": "Cloudy", "type": "movie",
         "thumb": {"small": "https://lametric/12197_sm.png"}},
        {"id": 34, "title": "Dollar", "type": "picture",
         "thumb": {"small": "https://lametric/34_sm.png"}},
        {"id": 999, "title": "Samsung cloud", "type": "movie", "thumb": {}},
        {"id": 5, "title": None, "type": "movie"},
    ]
}


@pytest.fixture
def cat():
    return LametricCatalogue()


@pytest.fixture
def client():
    return NgClient(HttpTransport("awtrix.test"))


def mock_catalogue():
    respx.get(CATALOGUE_URL).mock(return_value=httpx.Response(200, json=CATALOGUE_PAGE))


class TestCatalogue:
    @respx.mock
    async def test_search_matches_titles(self, cat):
        mock_catalogue()
        assert [i.title for i in await cat.search("cloud")] == ["Cloudy", "Samsung cloud"]

    @respx.mock
    async def test_prefix_matches_come_first(self, cat):
        """Searching "cloud" must not bury "Cloudy" under "Samsung cloud"."""
        mock_catalogue()
        assert (await cat.search("cloud"))[0].title == "Cloudy"

    @respx.mock
    async def test_animated_only_by_default(self, cat):
        mock_catalogue()
        assert all(icon.animated for icon in await cat.search(""))

    @respx.mock
    async def test_stills_can_be_included(self, cat):
        mock_catalogue()
        titles = [i.title for i in await cat.search("", animated_only=False)]
        assert "Dollar" in titles

    @respx.mock
    async def test_catalogue_is_fetched_once(self, cat):
        route = respx.get(CATALOGUE_URL).mock(
            return_value=httpx.Response(200, json=CATALOGUE_PAGE)
        )
        await cat.search("a")
        await cat.search("b")
        assert route.call_count == 1

    @respx.mock
    async def test_malformed_entry_is_skipped_not_fatal(self, cat):
        mock_catalogue()
        # The entry with title None must not break the whole catalogue.
        assert len(await cat.search("", animated_only=False)) == 5

    @respx.mock
    async def test_unreachable_gallery_is_explained(self, cat):
        respx.get(CATALOGUE_URL).mock(side_effect=httpx.ConnectTimeout(""))
        with pytest.raises(AwtrixNgError, match="LaMetric"):
            await cat.search("sun")

    @respx.mock
    async def test_animated_flag_follows_the_movie_type(self, cat):
        mock_catalogue()
        icons = {i.title: i for i in await cat.search("", animated_only=False)}
        assert icons["Clear Day"].animated is True
        assert icons["Dollar"].animated is False
        assert icons["Clear Day"].filename == "12182.gif"
        assert icons["Dollar"].filename == "34.jpg"


class TestDownload:
    @respx.mock
    async def test_content_type_decides_whether_it_is_animated(self):
        url = "https://developer.lametric.com/content/apps/icon_thumbs/12182"
        respx.get(url).mock(
            return_value=httpx.Response(200, content=GIF, headers={"content-type": "image/gif"})
        )
        async with httpx.AsyncClient() as http:
            payload, animated = await download(12182, http)
        assert animated and payload == GIF

    @respx.mock
    async def test_a_still_is_reported_as_such(self):
        url = "https://developer.lametric.com/content/apps/icon_thumbs/34"
        respx.get(url).mock(
            return_value=httpx.Response(200, content=b"x", headers={"content-type": "image/png"})
        )
        async with httpx.AsyncClient() as http:
            _, animated = await download(34, http)
        assert animated is False

    @respx.mock
    async def test_unknown_id(self):
        url = "https://developer.lametric.com/content/apps/icon_thumbs/1"
        respx.get(url).mock(return_value=httpx.Response(404))
        async with httpx.AsyncClient() as http:
            with pytest.raises(AwtrixNgError, match="does not exist"):
                await download(1, http)


class TestEnsureIcon:
    @respx.mock
    async def test_installs_a_missing_icon(self, client):
        respx.get(f"{BASE}/api/v1/files").mock(return_value=httpx.Response(200, json={"files": []}))
        respx.get("https://developer.lametric.com/content/apps/icon_thumbs/12197").mock(
            return_value=httpx.Response(200, content=GIF, headers={"content-type": "image/gif"})
        )
        upload = respx.post(f"{BASE}/api/v1/files").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        assert await client.ensure_icon("12197") is True
        assert b"12197.gif" in upload.calls.last.request.content
        assert upload.calls.last.request.url.params["dir"] == "/ICONS"

    @respx.mock
    async def test_already_installed_is_not_downloaded_again(self, client):
        respx.get(f"{BASE}/api/v1/files").mock(
            return_value=httpx.Response(200, json={"files": [{"name": "12197.gif"}]})
        )
        upload = respx.post(f"{BASE}/api/v1/files").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        assert await client.ensure_icon("12197") is True
        assert upload.call_count == 0

    @respx.mock
    async def test_the_device_is_listed_once_per_client(self, client):
        listing = respx.get(f"{BASE}/api/v1/files").mock(
            return_value=httpx.Response(200, json={"files": [{"name": "1.gif"}]})
        )
        await client.ensure_icon("1")
        await client.ensure_icon("1")
        assert listing.call_count == 1

    async def test_a_user_file_name_is_left_alone(self, client):
        """Only numeric LaMetric ids are managed; a hand-uploaded file is not."""
        assert await client.ensure_icon("my-logo") is True

    async def test_no_icon_is_not_an_error(self, client):
        assert await client.ensure_icon(None) is False

    @respx.mock
    async def test_a_still_icon_is_converted_rather_than_refused(self, client):
        """It used to raise. A still is now the normal case for whole families
        of icons — the moon phases have no animated equivalent at all."""
        import io

        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGBA", (8, 8), (10, 200, 90, 255)).save(buffer, format="PNG")

        respx.get(f"{BASE}/api/v1/files").mock(return_value=httpx.Response(200, json={"files": []}))
        respx.get("https://developer.lametric.com/content/apps/icon_thumbs/34").mock(
            return_value=httpx.Response(
                200, content=buffer.getvalue(), headers={"content-type": "image/png"}
            )
        )
        respx.post(f"{BASE}/api/v1/files").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        assert await client.ensure_icon("34") is True

    @respx.mock
    async def test_the_listing_also_says_what_room_is_left(self, client):
        """NG answers with counters AWTRIX 3 never gave. They matter: icons,
        melodies, palettes and scripts share one 512 KB partition, so an icon
        can fail to install because of something else entirely."""
        respx.get(f"{BASE}/api/v1/files").mock(
            return_value=httpx.Response(
                200,
                json={
                    "files": [{"name": "7.gif", "size": 1024}],
                    "usedBytes": 40960,
                    "totalBytes": 524288,
                },
            )
        )
        listing = await client.list_files()
        assert listing.names == ["7.gif"]
        assert listing.free_bytes == 483328


class TestRanking:
    """Search ordering, which is what makes the picker usable."""

    @respx.mock
    async def test_exact_title_wins(self, cat):
        respx.get(CATALOGUE_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {"id": 1, "title": "RAINBOW APPLE LOGO", "type": "movie"},
                        {"id": 2, "title": "Rainfall", "type": "movie"},
                        {"id": 3, "title": "Rain", "type": "movie"},
                    ]
                },
            )
        )
        assert [i.title for i in await cat.search("rain")] == [
            "Rain",
            "Rainfall",
            "RAINBOW APPLE LOGO",
        ]

    @respx.mock
    async def test_shorter_title_wins_within_a_tier(self, cat):
        respx.get(CATALOGUE_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {"id": 1, "title": "Sunset Animation", "type": "movie"},
                        {"id": 2, "title": "Sunrise", "type": "movie"},
                    ]
                },
            )
        )
        assert (await cat.search("sun"))[0].title == "Sunrise"


class TestStillIcons:
    """Still icons arrive as PNG, which the firmware cannot draw.

    They used to be refused outright, from when the project only wanted
    animated ones. That made whole families unusable — the moon phases among
    them, where the icon carries the information and no animated set exists.
    """

    @staticmethod
    def _png(size: tuple[int, int] = (8, 8), transparent: bool = True) -> bytes:
        import io

        from PIL import Image

        image = Image.new("RGBA", size, (255, 210, 0, 255))
        if transparent:
            image.putpixel((0, 0), (0, 0, 0, 0))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def test_a_png_becomes_a_gif(self):
        import io

        from PIL import Image

        converted = icons.to_gif(self._png())
        assert converted[:3] == b"GIF"
        with Image.open(io.BytesIO(converted)) as image:
            assert image.format == "GIF"
            assert image.size == (8, 8)

    def test_transparency_is_flattened_onto_black(self):
        """AWTRIX GIFs carry no transparency, and the matrix behind is black."""
        import io

        from PIL import Image

        with Image.open(io.BytesIO(icons.to_gif(self._png()))) as image:
            assert image.convert("RGB").getpixel((0, 0)) == (0, 0, 0)

    def test_rubbish_is_reported_rather_than_crashing(self):
        with pytest.raises(AwtrixNgError) as failure:
            icons.to_gif(b"this is not an image")
        assert failure.value.code == "icons.conversion_failed"

    def test_the_filename_is_a_gif_whatever_came_in(self):
        """One format on the device, so one extension."""
        assert icons.icon_filename(2318) == "2318.gif"


class TestInstallingAStill:
    @pytest.mark.asyncio
    @respx.mock
    async def test_a_still_icon_installs_as_a_converted_gif(self):
        """The regression behind an empty matrix: the moon widget asked for
        icon 2318, the download succeeded, and nothing was ever stored."""
        png = TestStillIcons._png()
        respx.get(icons.ICON_URL.format(icon_id=2318)).mock(
            return_value=httpx.Response(200, content=png, headers={"content-type": "image/png"})
        )

        sent: dict = {}

        class Transport:
            async def post_file(
                self, path, *, field, filename, content, content_type, params=None
            ):
                sent.update(
                    path=path, field=field, filename=filename, content=content,
                    content_type=content_type, params=params,
                )

            async def aclose(self):
                pass

        client = NgClient(Transport())
        async with httpx.AsyncClient() as outbound:
            name = await client.install_icon(2318, outbound)

        assert name == "2318.gif"
        # NG takes the folder as a query parameter, so the filename is bare.
        # AWTRIX 3 wanted "ICONS/2318.gif" inside the multipart field.
        assert sent["filename"] == "2318.gif"
        assert sent["params"] == {"dir": "/ICONS"}
        assert sent["content"][:3] == b"GIF", "a PNG was sent; the device draws nothing"
        assert sent["content_type"] == "image/gif"

    @pytest.mark.asyncio
    @respx.mock
    async def test_an_animated_icon_is_stored_untouched(self):
        """Converting an animation would flatten it to one frame."""
        animated = b"GIF89a" + b"\x00" * 40
        respx.get(icons.ICON_URL.format(icon_id=12183)).mock(
            return_value=httpx.Response(
                200, content=animated, headers={"content-type": "image/gif"}
            )
        )

        sent: dict = {}

        class Transport:
            async def post_file(
                self, path, *, field, filename, content, content_type, params=None
            ):
                sent.update(content=content)

            async def aclose(self):
                pass

        async with httpx.AsyncClient() as outbound:
            await NgClient(Transport()).install_icon(12183, outbound)

        assert sent["content"] == animated


class TestWeatherIconChoice:
    """Which icon goes with which sky.

    Both defects were spotted on a real matrix, not in a test: an overcast icon
    nobody could identify, and a cloud sitting next to "74%" on a widget whose
    whole subject is rain.
    """

    def test_the_cloudy_icon_is_the_legible_one(self):
        """12197 is named "Cloudy" and draws a diagonal smudge in the corner at
        eight pixels. Pinned so nobody picks it back by its name."""
        from app.connectors.weather import wmo

        assert wmo.ICON_CLOUDY == 12246

    def test_a_clear_sky_with_no_rain_coming_shows_the_sky(self):
        """The defect a first version shipped: it forced rain whenever it was
        not already raining, so a downpour sat next to "0 %" on a clear
        afternoon — the widget contradicting its own number."""
        from app.connectors.weather import wmo

        assert wmo.precipitation_icon(0, 0, is_day=True) == str(wmo.ICON_CLEAR_DAY)
        assert wmo.precipitation_icon(0, 30, is_day=True) == str(wmo.ICON_CLEAR_DAY)
        assert wmo.precipitation_icon(3, 10, is_day=True) == str(wmo.ICON_CLOUDY)

    def test_rain_is_announced_before_it_falls(self):
        """A clear sky at 74 % is exactly when the icon should say rain."""
        from app.connectors.weather import wmo

        assert wmo.precipitation_icon(0, 74, is_day=True) == str(wmo.ICON_RAIN)
        assert wmo.precipitation_icon(3, 74, is_day=True) == str(wmo.ICON_RAIN)

    def test_night_is_not_always_day(self):
        """is_day was hard-coded true, so a clear night showed a sun."""
        from app.connectors.weather import wmo

        assert wmo.precipitation_icon(0, 0, is_day=False) == str(wmo.ICON_CLEAR_NIGHT)

    def test_it_keeps_the_real_thing_whatever_the_odds(self):
        """Snow stays snow: falling back to rain would be worse, not simpler —
        and at 0 % it would be nonsense while it is actually snowing."""
        from app.connectors.weather import wmo

        for probability in (0, 50, 100):
            assert wmo.precipitation_icon(71, probability) == str(wmo.ICON_SNOW)
            assert wmo.precipitation_icon(95, probability) == str(wmo.ICON_THUNDERSTORM)

    def test_an_unknown_code_still_gets_an_icon(self):
        from app.connectors.weather import wmo

        assert wmo.precipitation_icon(None, None) == str(wmo.ICON_RAIN)
        assert wmo.precipitation_icon(999, 10) == str(wmo.ICON_RAIN)


class TestTheWholeGalleryIsWalked:
    """The gallery is far larger than one wave of pages.

    `MAX_PAGES` was 12, which stopped at 24 000 of the 71 858 icons LaMetric
    publishes. Two thirds were invisible in the picker and the only way to use
    one was to know its number — found when "Fuel ani" (55274, page 26) could
    not be searched for. Nothing in the repository saw it: every test mocked a
    single short page, so the loop stopped at page one and its bound was never
    reached.
    """

    #: Enough pages to pass the old bound and the first wave boundary.
    PAGES = 20

    def full_page(self, page: int) -> dict:
        start = (page - 1) * icons.PAGE_SIZE
        return {
            "data": [
                {"id": start + n, "title": f"Icon {start + n}", "type": "movie"}
                for n in range(icons.PAGE_SIZE)
            ]
        }

    def mock_many_pages(self):
        def answer(request: httpx.Request) -> httpx.Response:
            page = int(request.url.params.get("page", 1))
            if page > self.PAGES:
                return httpx.Response(200, json={"data": []})
            if page == self.PAGES:
                # A short page is how the gallery says "that was the last one".
                return httpx.Response(200, json={"data": self.full_page(page)["data"][:10]})
            return httpx.Response(200, json=self.full_page(page))

        respx.get(CATALOGUE_URL).mock(side_effect=answer)

    @respx.mock
    @pytest.mark.asyncio
    async def test_it_does_not_stop_at_the_twelfth_page(self, cat):
        self.mock_many_pages()
        loaded = await cat.load()
        expected = (self.PAGES - 1) * icons.PAGE_SIZE + 10
        assert len(loaded) == expected

    @respx.mock
    @pytest.mark.asyncio
    async def test_an_icon_past_the_old_bound_is_searchable(self, cat):
        """Page 26 is where "Fuel ani" lives upstream."""
        self.mock_many_pages()
        await cat.load()
        wanted = 15 * icons.PAGE_SIZE + 274
        found = await cat.search(f"Icon {wanted}", animated_only=True, limit=5)
        assert [icon.id for icon in found][:1] == [wanted]

    @respx.mock
    @pytest.mark.asyncio
    async def test_the_bound_still_stops_a_gallery_that_never_ends(self, cat):
        """The guard is against an upstream change, not against the gallery."""
        respx.get(CATALOGUE_URL).mock(
            side_effect=lambda request: httpx.Response(200, json=self.full_page(1))
        )
        loaded = await cat.load()
        assert len(loaded) <= icons.MAX_PAGES * icons.PAGE_SIZE


class TestTheThumbnailIsDerived:
    def test_it_follows_the_gallery_pattern(self):
        """Checked against all 71 858 entries: not one deviates. Storing the
        string cost 8 MB of resident memory for something the id determines."""
        summary = icons.IconSummary(id=55274, title="Fuel ani", animated=True)
        assert summary.thumbnail == (
            "https://developer.lametric.com/content/apps/icon_thumbs/"
            "55274_icon_thumb_sm.png"
        )

    def test_the_api_still_carries_one(self):
        """The picker reads it, so the route must still fill it from the
        property rather than from a field that no longer exists."""
        from app.api.routes.icons import Icon

        out = Icon.of(icons.IconSummary(id=55274, title="Fuel ani", animated=True))
        assert out.thumbnail.endswith("55274_icon_thumb_sm.png")
        assert out.filename == "55274.gif"
