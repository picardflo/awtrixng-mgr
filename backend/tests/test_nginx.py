"""The frontend's proxy, read as text.

It fronts the API, so every call the browser makes goes through it — and a
mistake here is invisible to every other test in this project: the backend
answers 200 on its own loopback while the interface shows nothing at all.

That is not hypothetical. `proxy_pass http://awtrixng-mgr-backend:8000;` named
the backend literally, and nginx resolves a literal name **once, at startup**,
then keeps the address forever. `docker compose up -d --build` recreates only
the containers whose image changed; the backend came back on a new address on
the Docker network and the frontend, untouched and still running, went on
writing to the dead one. Every `/api/` call answered 502 while
`docker compose ps` showed both containers healthy and the backend's own log
showed `GET /api/health 200`.

The symptom pointed at nothing, which is why the fix is pinned here.
"""

import re
from pathlib import Path

import pytest

CONF = Path(__file__).resolve().parents[2] / "frontend" / "nginx.conf"


@pytest.fixture(scope="module")
def api_block() -> str:
    conf = CONF.read_text(encoding="utf-8")
    start = conf.index("location /api/")
    return conf[start : conf.index("location /assets/", start)]


def test_the_backend_is_resolved_on_every_request(api_block: str):
    """A variable in `proxy_pass` is what forces it. Without one, nginx
    caches the address it got at startup."""
    assert re.search(r"^\s*proxy_pass\s+\$\w+;", api_block, re.MULTILINE), (
        "proxy_pass names the backend literally again — one recreated "
        "container and every /api/ call answers 502"
    )


def test_it_uses_dockers_own_resolver(api_block: str):
    """127.0.0.11, and a short TTL: an address that changed must not be
    believed for long."""
    assert "resolver 127.0.0.11" in api_block
    assert re.search(r"valid=\d+s", api_block), "no TTL on the resolver"


def test_it_does_not_ask_for_an_address_the_backend_cannot_serve(api_block: str):
    """`ipv6=off`, because uvicorn binds 0.0.0.0 — IPv4 only. A AAAA record
    from Docker's resolver would bring the same 502 back through the other
    door."""
    assert "ipv6=off" in api_block


def test_the_proxied_path_is_unchanged(api_block: str):
    """`proxy_pass $backend;` with no path forwards the original URI, exactly
    as the literal form did. A trailing slash here would send `/foo` where the
    backend expects `/api/foo`, and every route would 404 instead."""
    directive = re.search(r"^\s*proxy_pass\s+(\S+);", api_block, re.MULTILINE)
    assert directive is not None
    assert directive.group(1) == "$backend", "a path crept into proxy_pass"
