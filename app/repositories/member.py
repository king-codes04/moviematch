class MemberRepository:
    def __init__(self, client):
        self.client = client

    def add_member(self, code, user_id):
        return self.client.sadd(
            f"ROOM:{code}:MEMBERS",
            user_id
        )

    def remove_member(self, code, user_id):
        return self.client.srem(
            f"ROOM:{code}:MEMBERS",
            user_id
        )

    def member_exists(self, code, user_id):
        return self.client.sismember(
            f"ROOM:{code}:MEMBERS",
            user_id
        )

    def get_members(self, code):
        return self.client.smembers(
            f"ROOM:{code}:MEMBERS"
        )