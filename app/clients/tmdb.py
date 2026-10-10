
import httpx

from app.core.config import settings


class TMDBClient:
    BASE_URL = "https://api.themoviedb.org/3"

    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {settings.TMDB_BEARER_TOKEN}",
            "accept": "application/json",
        }

    def _get_movies(
        self,
        endpoint: str,
        page: int = 1,
        region: str | None = None,
    ) -> dict:
        if page < 1:
            raise ValueError("Page must be at least 1")

        params = {
            "page": page,
            "language": "en-US",
        }

        if region:
            params["region"] = region

        try:
            response = httpx.get(
                f"{self.BASE_URL}{endpoint}",
                headers=self.headers,
                params=params,
                timeout=10.0,
            )
            response.raise_for_status()
            return response.json()

        except httpx.TimeoutException as exc:
            raise RuntimeError("TMDB request timed out") from exc

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"TMDB returned HTTP {exc.response.status_code}"
            ) from exc

        except httpx.RequestError as exc:
            raise RuntimeError("Could not connect to TMDB") from exc

    def get_popular_movies(self, page: int = 1) -> dict:
        return self._get_movies("/movie/popular", page=page)

    def get_now_playing_movies(
        self,
        page: int = 1,
        region: str | None = "TZ",
    ) -> dict:
        return self._get_movies(
            "/movie/now_playing",
            page=page,
            region=region,
        )
