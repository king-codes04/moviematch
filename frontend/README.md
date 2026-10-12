# MovieMatch frontend

The React/Vite client talks to the existing FastAPI application and its room
WebSocket. With the backend running on `http://localhost:8000`, start the
frontend using `npm run dev`; Vite proxies API and WebSocket traffic to it.

Set `VITE_API_URL` to the backend origin when the frontend is served outside
the Vite development server. The browser only receives public movie metadata
and TMDB image paths; the TMDB bearer token remains on the backend.

## Shared movie pool

Room creation only creates the waiting room. When the host starts the room, the
backend fetches up to ten unique movies from TMDB and persists one ordered,
room-specific pool in Redis. Pool entries are not removed as members browse or
decide, so every member sees the same movies in the same order.

Each member's swipe position and undo history are stored in that member's
browser, separately from the room pool and every other member's browsing
state. Swiping left or using Undo only navigates; neither action records or
reverses a backend decision. A swipe right or Like records a `like`. The API
continues to accept explicit `skip` decisions for existing clients. Repeating
the same decision is idempotent. An explicit `skip` may be upgraded to `like`,
but a `like` cannot be downgraded to `skip`; the API returns HTTP 409 for that
conflict. Undoing navigation never sends a decision reversal.

### HTTP contract

- `POST /rooms` creates a waiting room; it does not fetch movies.
- `POST /rooms/{code}/start` fetches and stores the movie pool.
- `GET /rooms/{code}/movies?user_id={user_id}` returns the shared ordered pool
  with only that member's `my_decision` values.
- `GET /rooms/{code}/state?user_id={user_id}` recovers the room, member list,
  pool, the requesting member's decisions, and discovered matches after a
  refresh or reconnect.
- `POST /rooms/{code}/movies/{movie_id}/decision?user_id={user_id}` accepts
  `{"decision":"like"}` or `{"decision":"skip"}`. The backend validates room
  status, membership, and movie-pool membership.

A movie becomes a match after two distinct room members like it. Redis runs
decision recording and match insertion atomically; duplicate requests cannot
create another match. The room supports multiple matches. Room membership
continues to be capped at three, and only waiting-room members can leave.
The existing Redis setup has no automatic room TTL: cancelled rooms are
cleaned up, while ended-room pool, decisions, and matches remain available for
state recovery until Redis is otherwise cleared.

Run the browser-navigation unit tests with `npm test` from `frontend/`. The
backend matching and API tests cover decision retries, skip-to-like upgrades,
and atomic match creation.

### WebSocket events

Events retain the existing `{event, data}` envelope:

- `member_joined`: `{username, room}`
- `member_left`: `{username}`
- `room_started`: `{code, status, movie_count}`
- `decision_recorded`: `{movie_id}`; it does not reveal the member or choice
- `match_found`: `{movie}`; sent only when a match is first persisted
- `room_ended`: `{code, status}`; cancellation additionally includes
  `{reason:"cancelled"}`

WebSockets distribute changes; Redis-backed HTTP state is authoritative. The
client reloads room state on connection/reconnection and stores its room code
and nickname locally so a page refresh can recover the session. These nicknames
are not authenticated user identities. Pool pagination/loading beyond the
initial ten TMDB movies is not implemented yet.

The mutual-match celebration is triggered only by a new `match_found`
WebSocket event. It uses the event's `{movie}` object, displays its poster and
details, and adds the movie to the matches collection. Matches returned by
state recovery are marked as already known and do not replay the celebration.
Event movie IDs are also remembered per room/member in browser storage so a
duplicate event after reconnect or refresh is ignored. The celebration does
not block browsing once dismissed; its details and continue actions remain
available while the other room members keep browsing independently.
