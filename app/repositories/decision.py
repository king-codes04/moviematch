
class DecisionRepository:
    def __init__(self, client):
        self.client = client

    def submit_decision(self, code, round_number, user_id, decision):
        return self.client.hsetnx(
            f"DECISIONS:{code}:ROUND:{round_number}",
            user_id,
            decision
        )

    def get_decisions(self, code, round_number):
        return self.client.hgetall(
            f"DECISIONS:{code}:ROUND:{round_number}"
        )

    def get_user_decision(self, code, round_number, user_id):
        return self.client.hget(
            f"DECISIONS:{code}:ROUND:{round_number}",
            user_id
        )

    def has_decided(self, code, round_number, user_id):
        return self.client.hexists(
            f"DECISIONS:{code}:ROUND:{round_number}",
            user_id
        )

    def delete_round_decisions(self, code, round_number):
        return self.client.delete(
            f"DECISIONS:{code}:ROUND:{round_number}"
        )
