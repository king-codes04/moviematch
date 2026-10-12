import json


class MatchRepository:
    def __init__(self, client):
        self.client = client

    def add_match(self, code, movie):
        return self.client.eval(
            """
            if redis.call('SADD', KEYS[1], ARGV[1]) == 1 then
              redis.call('RPUSH', KEYS[2], ARGV[2])
              redis.call('HSET', KEYS[3], ARGV[1], ARGV[2])
              return 1
            end
            return 0
            """,
            3,
            f"MATCHES:{code}:IDS",
            f"MATCHES:{code}",
            f"MATCHES:{code}:BY_ID",
            str(movie["id"]),
            json.dumps(movie),
        )

    def get_matches(self, code):
        matches = self.client.lrange(
            f"MATCHES:{code}",
            0,
            -1
        )

        return [json.loads(match) for match in matches]

    def get_match(self, code, movie_id):
        match = self.client.hget(
            f"MATCHES:{code}:BY_ID",
            str(movie_id),
        )
        return json.loads(match) if match else None

    def has_match(self, code, movie_id):
        return bool(
            self.client.sismember(
                f"MATCHES:{code}:IDS",
                str(movie_id),
            )
        )

    def match_count(self, code):
        return self.client.llen(f"MATCHES:{code}")

    def delete_matches(self, code):
        return self.client.delete(
            f"MATCHES:{code}",
            f"MATCHES:{code}:IDS",
            f"MATCHES:{code}:BY_ID",
        )