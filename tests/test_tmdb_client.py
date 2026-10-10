import httpx
import pytest

from app.clients.tmdb import TMDBClient


# --------------------------------------------------
# Helpers: create predictable fake HTTP responses
# --------------------------------------------------

def mock_tmdb_response(request):
    return httpx.Response(
        200,
        json={
            "page": 1,
            "results": [
                {
                    "id": 123,
                    "title": "Example Movie",
                },
                {
                    "id": 456,
                    "title": "Another Movie",
                },
            ],
        },
        request=request,
    )


def install_mock_get(
    monkeypatch,
    captured,
    *,
    status_code=200,
    error=None,
):
    """Replace httpx.get() and record the request arguments."""

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)

        if error is not None:
            raise error

        request = httpx.Request("GET", url)

        if status_code == 200:
            return mock_tmdb_response(request)

        return httpx.Response(
            status_code,
            json={"status_message": "Request failed"},
            request=request,
        )

    monkeypatch.setattr(httpx, "get", fake_get)


# --------------------------------------------------
# 1. Popular movies
# --------------------------------------------------

def test_get_popular_movies(monkeypatch):
    # Arrange
    captured = {}
    install_mock_get(monkeypatch, captured)
    client = TMDBClient()

    # Act
    result = client.get_popular_movies()

    # Assert: endpoint
    assert captured["url"] == (
        "https://api.themoviedb.org/3/movie/popular"
    )

    # Assert: authentication headers
    headers = captured["headers"]
    assert headers["Authorization"].startswith("Bearer ")
    assert headers["Authorization"] != "Bearer "
    assert headers["accept"] == "application/json"

    # Assert: default query parameters
    assert captured["params"]["page"] == 1
    assert captured["params"]["language"] == "en-US"

    # Assert: timeout
    assert captured["timeout"] == 10.0

    # Assert: returned movie data
    assert isinstance(result, dict)
    assert isinstance(result["results"], list)
    assert len(result["results"]) == 2
    assert result["results"][0]["id"] == 123
    assert result["results"][0]["title"] == "Example Movie"


def test_get_popular_movies_with_custom_page(monkeypatch):
    captured = {}
    install_mock_get(monkeypatch, captured)
    client = TMDBClient()

    result = client.get_popular_movies(page=3)

    assert captured["params"]["page"] == 3
    assert result["page"] == 1


# --------------------------------------------------
# 2. Now-playing movies
# --------------------------------------------------

def test_get_now_playing_movies_with_tanzania_region(monkeypatch):
    captured = {}
    install_mock_get(monkeypatch, captured)
    client = TMDBClient()

    result = client.get_now_playing_movies()

    assert captured["url"] == (
        "https://api.themoviedb.org/3/movie/now_playing"
    )
    assert captured["params"]["page"] == 1
    assert captured["params"]["language"] == "en-US"
    assert captured["params"]["region"] == "TZ"
    assert isinstance(result["results"], list)


def test_get_now_playing_movies_without_region(monkeypatch):
    captured = {}
    install_mock_get(monkeypatch, captured)
    client = TMDBClient()

    client.get_now_playing_movies(region=None)

    assert "region" not in captured["params"]


# --------------------------------------------------
# 3. Invalid input
# --------------------------------------------------

def test_rejects_page_zero(monkeypatch):
    def unexpected_request(*args, **kwargs):
        pytest.fail("HTTP request should not be made for page 0")

    monkeypatch.setattr(httpx, "get", unexpected_request)

    client = TMDBClient()

    with pytest.raises(
        ValueError,
        match="Page must be at least 1",
    ):
        client.get_popular_movies(page=0)


def test_rejects_negative_page(monkeypatch):
    def unexpected_request(*args, **kwargs):
        pytest.fail("HTTP request should not be made for a negative page")

    monkeypatch.setattr(httpx, "get", unexpected_request)

    client = TMDBClient()

    with pytest.raises(
        ValueError,
        match="Page must be at least 1",
    ):
        client.get_popular_movies(page=-1)


# --------------------------------------------------
# 4. HTTP status errors
# --------------------------------------------------

def test_handles_http_error(monkeypatch):
    captured = {}
    install_mock_get(
        monkeypatch,
        captured,
        status_code=401,
    )
    client = TMDBClient()

    with pytest.raises(
        RuntimeError,
        match="TMDB returned HTTP 401",
    ):
        client.get_popular_movies()


def test_handles_server_error(monkeypatch):
    captured = {}
    install_mock_get(
        monkeypatch,
        captured,
        status_code=500,
    )
    client = TMDBClient()

    with pytest.raises(
        RuntimeError,
        match="TMDB returned HTTP 500",
    ):
        client.get_popular_movies()


# --------------------------------------------------
# 5. Timeout errors
# --------------------------------------------------

def test_handles_timeout(monkeypatch):
    captured = {}
    install_mock_get(
        monkeypatch,
        captured,
        error=httpx.TimeoutException("Request timed out"),
    )
    client = TMDBClient()

    with pytest.raises(
        RuntimeError,
        match="TMDB request timed out",
    ):
        client.get_popular_movies()


# --------------------------------------------------
# 6. Connection and request errors
# --------------------------------------------------

def test_handles_connection_error(monkeypatch):
    captured = {}
    install_mock_get(
        monkeypatch,
        captured,
        error=httpx.ConnectError("Connection failed"),
    )
    client = TMDBClient()

    with pytest.raises(
        RuntimeError,
        match="Could not connect to TMDB",
    ):
        client.get_popular_movies()


def test_handles_other_request_errors(monkeypatch):
    captured = {}
    install_mock_get(
        monkeypatch,
        captured,
        error=httpx.RequestError("Request failed"),
    )
    client = TMDBClient()

    with pytest.raises(
        RuntimeError,
        match="Could not connect to TMDB",
    ):
        client.get_popular_movies()
