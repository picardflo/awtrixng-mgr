"""ADR-009: protect without breaking LAN use, which is the point of the product."""

import pytest

from app.core.errors import UnsafeUrlError
from app.core.http import validate_url


@pytest.mark.parametrize("url", ["http://127.0.0.1:8181", "https://localhost/api"])
def test_lan_targets_are_allowed(url):
    assert validate_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com",
        "gopher://example.com",
    ],
)
def test_non_http_schemes_refused(url):
    with pytest.raises(UnsafeUrlError, match="http"):
        validate_url(url)


def test_cloud_metadata_address_refused():
    with pytest.raises(UnsafeUrlError, match="refused"):
        validate_url("http://169.254.169.254/latest/meta-data/")


def test_url_without_host_refused():
    with pytest.raises(UnsafeUrlError):
        validate_url("http:///nohost")
