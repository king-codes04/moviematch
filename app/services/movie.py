
class MovieService:
    def __init__(self, tmdb_client):
        self.tmdb_client = tmdb_client

    def get_popular_movies(self, page: int = 1) -> list:
        if type(page) is not int or page < 1:
            raise ValueError("Page must be a positive integer")

        response = self.tmdb_client.get_popular_movies(page=page)

        if not isinstance(response, dict):
            raise ValueError(
                "Invalid TMDB response: expected a dictionary"
            )

        results = response.get("results")

        if not isinstance(results, list):
            raise ValueError(
                "Invalid TMDB response: expected a results list"
            )

        return results

    def _is_valid_movie(self, movie: dict) -> bool:
        if not isinstance(movie, dict):
            return False

        if movie.get("id") is None:
            return False

        if not isinstance(movie.get("title"), str):
            return False

        if not movie["title"].strip():
            return False

        return True

    def get_movie_pool(
        self,
        pool_size: int = 10,
        max_pages: int = 5,
    ) -> list:
        if type(pool_size) is not int or pool_size < 1:
            raise ValueError(
                "Pool size must be a positive integer"
            )

        if type(max_pages) is not int or max_pages < 1:
            raise ValueError(
                "Maximum pages must be a positive integer"
            )

        movies_by_id = {}

        for page in range(1, max_pages + 1):
            response_movies = self.get_popular_movies(page=page)

            for movie in response_movies:
                if not self._is_valid_movie(movie):
                    continue

                movie_id = movie["id"]

                if movie_id not in movies_by_id:
                    movies_by_id[movie_id] = movie

                if len(movies_by_id) == pool_size:
                    return list(movies_by_id.values())

        raise ValueError(
            f"Could not collect {pool_size} unique valid movies; "
            f"found {len(movies_by_id)}"
        )
