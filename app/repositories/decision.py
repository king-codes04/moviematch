
class DecisionRepository:
    def __init__(self, client):
        self.client = client

    RECORD_MOVIE_DECISION = """
    if redis.call('EXISTS', KEYS[1]) == 0 then
      return {-1, 0}
    end
    if redis.call('HGET', KEYS[1], 'status') ~= 'started' then
      return {-5, 0}
    end
    if redis.call('SISMEMBER', KEYS[2], ARGV[1]) == 0 then
      return {-2, 0}
    end
    local movie = redis.call('HGET', KEYS[3], ARGV[2])
    if not movie then
      return {-3, 0}
    end
    local previous = redis.call('HGET', KEYS[4], ARGV[1])
    if previous then
      if previous == ARGV[3] then
        return {0, redis.call('SISMEMBER', KEYS[5], ARGV[2])}
      end
      if previous ~= 'skip' or ARGV[3] ~= 'like' then
        return {-4, 0}
      end
    end
    redis.call('HSET', KEYS[4], ARGV[1], ARGV[3])
    if ARGV[3] ~= 'like' then
      return {1, 0}
    end
    local likes = 0
    local decisions = redis.call('HVALS', KEYS[4])
    for _, value in ipairs(decisions) do
      if value == 'like' then
        likes = likes + 1
      end
    end
    if likes < 2 then
      return {1, 0}
    end
    if redis.call('SADD', KEYS[5], ARGV[2]) == 1 then
      redis.call('RPUSH', KEYS[6], movie)
      redis.call('HSET', KEYS[7], ARGV[2], movie)
      return {2, 1}
    end
    return {1, 1}
    """

    def submit_movie_decision(self, code, movie_id, user_id, decision):
        return self.client.eval(
            self.RECORD_MOVIE_DECISION,
            7,
            f"ROOM:{code}",
            f"ROOM:{code}:MEMBERS",
            f"MOVIES:{code}:BY_ID",
            f"DECISIONS:{code}:MOVIE:{movie_id}",
            f"MATCHES:{code}:IDS",
            f"MATCHES:{code}",
            f"MATCHES:{code}:BY_ID",
            user_id,
            str(movie_id),
            decision,
        )

    def get_user_decisions(self, code, user_id, movie_ids):
        decisions = {}
        for movie_id in movie_ids:
            decision = self.client.hget(
                f"DECISIONS:{code}:MOVIE:{movie_id}",
                user_id,
            )
            if decision:
                decisions[int(movie_id)] = decision
        return decisions

    def delete_room_decisions(self, code):
        keys = list(
            self.client.scan_iter(
                match=f"DECISIONS:{code}:MOVIE:*"
            )
        )
        if keys:
            return self.client.delete(*keys)
        return 0
