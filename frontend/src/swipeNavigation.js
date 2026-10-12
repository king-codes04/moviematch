export function restoreBrowseState(saved, movies) {
  const movieIds = new Set(movies.map((movie) => movie.id))
  const history = Array.isArray(saved?.history)
    ? saved.history.filter((movieId) => movieIds.has(movieId))
    : []
  const savedPosition = Number(saved?.position)
  const position = Number.isFinite(savedPosition)
    ? Math.max(0, Math.min(Math.trunc(savedPosition), movies.length))
    : 0

  return { position, history }
}

export function advanceBrowseState(state, movieId) {
  return {
    position: state.position + 1,
    history: [...state.history, movieId],
  }
}

export function undoBrowseState(state, movies) {
  if (!state.history.length) return null

  const history = state.history.slice(0, -1)
  const position = movies.findIndex(
    (movie) => movie.id === state.history[state.history.length - 1],
  )
  if (position < 0) return null

  return { position, history }
}
