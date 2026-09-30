import json


class MovieRepository:
    def __init__(self, client):
        self.client = client

    def add_movie(self, code, movie):
        return self.client.rpush(
            f"MOVIES:{code}",
            json.dumps(movie)
        )

    def get_movies(self, code):
        movies = self.client.lrange(
            f"MOVIES:{code}",
            0,
            -1
        )

        return [json.loads(movie) for movie in movies]

    def get_next_movie(self, code):
        movie = self.client.lpop(f"MOVIES:{code}")

        if movie is None:
            return None

        return json.loads(movie)

    def movie_count(self, code):
        return self.client.llen(f"MOVIES:{code}")

    def delete_movies(self, code):
        return self.client.delete(f"MOVIES:{code}")