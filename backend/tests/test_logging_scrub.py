"""§32.11: no secret in the logs. The Tautulli key travels in the query string."""

from app.core.logging import scrub


def test_query_string_is_masked():
    assert scrub("GET http://tautulli.lan/api/v2?apikey=deadbeef&cmd=get_activity") == (
        "GET http://tautulli.lan/api/v2?***"
    )


def test_token_in_body_is_masked():
    assert "abc123" not in scrub('{"token": "abc123"}')


def test_password_is_masked():
    assert "hunter2" not in scrub("password=hunter2")


def test_plain_message_untouched():
    assert scrub("weather.home fetch successful") == "weather.home fetch successful"


def test_bearer_token_is_masked_not_just_the_scheme():
    """The secret is the token, not the word "Bearer"."""
    masked = scrub("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload")
    assert "eyJhbGciOiJIUzI1NiJ9" not in masked
    assert masked == "Authorization: Bearer ***"


def test_basic_auth_value_is_masked():
    assert "dXNlcjpwYXNz" not in scrub("Authorization: Basic dXNlcjpwYXNz")


def test_authorization_without_scheme_is_masked():
    assert "rawtoken" not in scrub("authorization=rawtoken")


def test_scrub_is_idempotent():
    once = scrub("Authorization: Bearer secret123")
    assert scrub(once) == once
