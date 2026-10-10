
import pytest

from app.services.movie import MovieService


# -------------------------
# Fake TMDB client
# -------------------------

class FakeTMDBClient:
    def __init__(self, pages=None):
        self.pages = pages or {}
        self.requested_pages = []

    def get_popular_movies(self, page=1):
        self.requested_pages.append(page)

        return {
            "results": self.pages.get(page, [])
        }


def make_movie(movie_id, title=None, poster_path="/poster.jpg"):
    return {
        "id": movie_id,
        "title": title or f"Movie {movie_id}",
        "poster_path": poster_path,
    }


def make_service(pages=None):
    client = FakeTMDBClient(pages)
    service = MovieService(client)
    return service, client


# -------------------------
# get_popular_movies()
# -------------------------

def test_get_popular_movies_returns_results():
    expected = [make_movie(1), make_movie(2)]
    service, _ = make_service({1: expected})

    result = service.get_popular_movies()

    assert result == expected


def test_get_popular_movies_passes_page_number():
    service, client = make_service({3: [make_movie(3)]})

    service.get_popular_movies(page=3)

    assert client.requested_pages == [3]


@pytest.mark.parametrize("page", [0, -1, True, 1.5, "2"])
def test_get_popular_movies_rejects_invalid_page(page):
    service, client = make_service()

    with pytest.raises(ValueError, match="positive integer"):
        service.get_popular_movies(page=page)

    assert client.requested_pages == []


@pytest.mark.parametrize(
    "response",
    [
        None,
        [],
        "invalid response",
        {},
        {"results": None},
        {"results": "not a list"},
    ],
)
def test_get_popular_movies_rejects_malformed_response(response):
    class MalformedClient:
        def get_popular_movies(self, page=1):
            return response

    service = MovieService(MalformedClient())

    with pytest.raises(ValueError, match="Invalid TMDB response"):
        service.get_popular_movies()


# -------------------------
# _is_valid_movie()
# -------------------------

@pytest.mark.parametrize(
    "movie",
    [
        make_movie(1),
        make_movie(2, poster_path=None),
        make_movie(3, poster_path=""),
    ],
)
def test_is_valid_movie_accepts_usable_movies(movie):
    service, _ = make_service()

    assert service._is_valid_movie(movie) is True


@pytest.mark.parametrize(
    "movie",
    [
        None,
        [],
        "not a movie",
        {},
        {"title": "Missing ID"},
        {"id": 1, "title": ""},
        {"id": 1, "title": "   "},
        {"id": 1, "title": None},
        {"id": 1, "title": 123},
        {"id": None, "title": "Missing ID"},
    ],
)
def test_is_valid_movie_rejects_invalid_movies(movie):
    service, _ = make_service()

    assert service._is_valid_movie(movie) is False


# -------------------------
# get_movie_pool()
# -------------------------

def test_get_movie_pool_returns_ten_unique_movies():
    movies = [make_movie(i) for i in range(1, 11)]
    service, client = make_service({1: movies})

    result = service.get_movie_pool()

    assert len(result) == 10
    assert len({movie["id"] for movie in result}) == 10
    assert client.requested_pages == [1]


def test_get_movie_pool_removes_duplicate_ids():
    pages = {
        1: [make_movie(1), make_movie(2)],
        2: [make_movie(2), make_movie(3)],
    }
    service, client = make_service(pages)

    result = service.get_movie_pool(pool_size=3)

    assert [movie["id"] for movie in result] == [1, 2, 3]
    assert client.requested_pages == [1, 2]


def test_get_movie_pool_skips_invalid_movies():
    pages = {
        1: [
            make_movie(1),
            {"id": 2, "title": "   "},
            make_movie(3),
        ],
        2: [make_movie(4)],
    }
    service, client = make_service(pages)

    result = service.get_movie_pool(pool_size=3)

    assert [movie["id"] for movie in result] == [1, 3, 4]
    assert client.requested_pages == [1, 2]


def test_get_movie_pool_preserves_poster_path():
    poster = "/example-poster.jpg"
    service, _ = make_service({
        1: [make_movie(1, poster_path=poster)]
    })

    result = service.get_movie_pool(pool_size=1)

    assert result[0]["poster_path"] == poster


def test_get_movie_pool_allows_missing_poster():
    service, _ = make_service({
        1: [make_movie(1, poster_path=None)]
    })

    result = service.get_movie_pool(pool_size=1)

    assert result[0]["poster_path"] is None


def test_get_movie_pool_rejects_invalid_configuration():
    service, client = make_service()

    invalid_configurations = [
        {"pool_size": 0},
        {"pool_size": -1},
        {"pool_size": True},
        {"pool_size": 1.5},
        {"max_pages": 0},
        {"max_pages": -1},
        {"max_pages": True},
        {"max_pages": 1.5},
    ]

    for config in invalid_configurations:
        with pytest.raises(ValueError):
            service.get_movie_pool(**config)

    assert client.requested_pages == []


def test_get_movie_pool_raises_when_not_enough_movies():
    service, client = make_service({
        1: [make_movie(1), make_movie(2)],
        2: [make_movie(3)],
    })

    with pytest.raises(
        ValueError,
        match="Could not collect 5 unique valid movies",
    ):
        service.get_movie_pool(pool_size=5, max_pages=2)

    assert client.requested_pages == [1, 2]


def test_get_movie_pool_stops_when_pool_is_full():
    service, client = make_service({
        1: [make_movie(i) for i in range(1, 4)],
        2: [make_movie(i) for i in range(4, 7)],
        3: [make_movie(i) for i in range(7, 10)],
    })

    result = service.get_movie_pool(pool_size=5)

    assert len(result) == 5
    assert client.requested_pages == [1, 2]
