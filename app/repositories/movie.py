import json


class MovieRepository:
    def __init__(self, client):
        self.client = client

    def _pool_key(self, code):
        return f"MOVIES:{code}"

    def _index_key(self, code):
        return f"MOVIES:{code}:BY_ID"

    def add_movie(self, code, movie):
        return self.client.eval(
            """
            if redis.call('HSETNX', KEYS[1], ARGV[1], ARGV[2]) == 1 then
              redis.call('RPUSH', KEYS[2], ARGV[2])
              return 1
            end
            return 0
            """,
            2,
            self._index_key(code),
            self._pool_key(code),
            str(movie["id"]),
            json.dumps(movie),
        )

    def get_movies(self, code):
        movies = self.client.lrange(
            self._pool_key(code),
            0,
            -1
        )

        return [json.loads(movie) for movie in movies]

    def get_movie(self, code, movie_id):
        movie = self.client.hget(
            self._index_key(code),
            str(movie_id),
        )

        return json.loads(movie) if movie else None

    def get_next_movie(self, code):
        movie = self.client.lpop(self._pool_key(code))

        if movie is None:
            return None

        return json.loads(movie)

    def movie_count(self, code):
        return self.client.llen(self._pool_key(code))

    def delete_movies(self, code):
        return self.client.delete(
            self._pool_key(code),
            self._index_key(code),
        )

    def add_movies(self, code, movies):
      if not movies:
        raise ValueError("Movie pool cannot be empty")

      unique_movies = []
      seen_ids = set()
      for movie in movies:
        movie_id = str(movie["id"])
        if movie_id not in seen_ids:
          unique_movies.append(movie)
          seen_ids.add(movie_id)

      serialized_movies = [
        json.dumps(movie) for movie in unique_movies
      ]
      serialized_by_id = {
        str(movie["id"]): json.dumps(movie)
        for movie in unique_movies
      }

      with self.client.pipeline(transaction=True) as pipeline:
        pipeline.delete(self._pool_key(code), self._index_key(code))
        pipeline.rpush(self._pool_key(code), *serialized_movies)
        pipeline.hset(self._index_key(code), mapping=serialized_by_id)
        results = pipeline.execute()

      return results[-2]
