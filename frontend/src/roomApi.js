const API_ROOT = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')

function apiUrl(path) {
  return `${API_ROOT}${path}`
}

export async function request(path, options = {}) {
  const response = await fetch(apiUrl(path), {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  })
  const result = await response.json().catch(() => null)

  if (!response.ok) {
    throw new Error(result?.detail || 'Something went wrong. Please try again.')
  }

  return result
}

export const roomApi = {
  create(username) {
    return request('/rooms', {
      method: 'POST',
      body: JSON.stringify({ username }),
    })
  },

  join(code, username) {
    return request(`/rooms/${encodeURIComponent(code)}/join`, {
      method: 'POST',
      body: JSON.stringify({ username }),
    })
  },

  getState(code, username) {
    return request(
      `/rooms/${encodeURIComponent(code)}/state?user_id=${encodeURIComponent(username)}`,
    )
  },

  getMovies(code, username) {
    return request(
      `/rooms/${encodeURIComponent(code)}/movies?user_id=${encodeURIComponent(username)}`,
    )
  },

  start(code, username) {
    return request(`/rooms/${encodeURIComponent(code)}/start`, {
      method: 'POST',
      body: JSON.stringify({ username }),
    })
  },

  decide(code, movieId, username, decision) {
    return request(
      `/rooms/${encodeURIComponent(code)}/movies/${encodeURIComponent(movieId)}/decision?user_id=${encodeURIComponent(username)}`,
      {
        method: 'POST',
        body: JSON.stringify({ decision }),
      },
    )
  },

  leave(code, username) {
    return request(`/rooms/${encodeURIComponent(code)}/leave`, {
      method: 'POST',
      body: JSON.stringify({ username }),
    })
  },

  end(code, username) {
    return request(`/rooms/${encodeURIComponent(code)}/end`, {
      method: 'POST',
      body: JSON.stringify({ username }),
    })
  },

  websocketUrl(code, username) {
    const root = API_ROOT.startsWith('http')
      ? new URL(API_ROOT)
      : new URL(window.location.origin)
    const protocol = root.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${root.host}/ws/${encodeURIComponent(code)}?user_id=${encodeURIComponent(username)}`
  },
}
