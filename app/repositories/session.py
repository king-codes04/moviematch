class SessionRepository:
    def __init__(self, client):
        self.client = client

    def create_session(self, code, status):
        return self.client.hset(
            f"SESSION:{code}",
            mapping={
                "status": status,
            }
        )

    def get_session(self, code):
        return self.client.hgetall(f"SESSION:{code}")

    def session_exists(self, code):
        return self.client.exists(f"SESSION:{code}")

    def update_session(self, code, **fields):
        return self.client.hset(
            f"SESSION:{code}",
            mapping=fields
        )

    def delete_session(self, code):
        return self.client.delete(f"SESSION:{code}")