import json


class MatchRepository:
    def __init__(self, client):
        self.client = client

    def add_match(self, code, movie):
        return self.client.rpush(
            f"MATCHES:{code}",
            json.dumps(movie)
        )

    def get_matches(self, code):
        matches = self.client.lrange(
            f"MATCHES:{code}",
            0,
            -1
        )

        return [json.loads(match) for match in matches]

    def match_count(self, code):
        return self.client.llen(f"MATCHES:{code}")

    def delete_matches(self, code):
        return self.client.delete(f"MATCHES:{code}")