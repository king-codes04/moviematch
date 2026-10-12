export function createMatchTracker(recoveredMatches = [], previouslySeenIds = []) {
  const knownIds = new Set(previouslySeenIds.map(Number))
  for (const movie of recoveredMatches) {
    knownIds.add(Number(movie.id))
  }
  return knownIds
}

export function recordMatchEvent(knownIds, movie) {
  const movieId = Number(movie?.id)
  if (!Number.isInteger(movieId) || movieId <= 0) {
    return { knownIds, isNew: false }
  }

  if (knownIds.has(movieId)) {
    return { knownIds, isNew: false }
  }

  const nextKnownIds = new Set(knownIds)
  nextKnownIds.add(movieId)
  return { knownIds: nextKnownIds, isNew: true }
}
