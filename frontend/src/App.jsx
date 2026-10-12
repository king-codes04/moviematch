import { useCallback, useEffect, useRef, useState } from 'react'
import { roomApi } from './roomApi'
import {
  advanceBrowseState,
  restoreBrowseState,
  undoBrowseState,
} from './swipeNavigation'
import {
  createMatchTracker,
  recordMatchEvent,
} from './matchCelebration'
import './App.css'

const TMDB_IMAGE_ROOT = 'https://image.tmdb.org/t/p'
const TMDB_GENRES = {
  12: 'Adventure',
  14: 'Fantasy',
  16: 'Animation',
  18: 'Drama',
  27: 'Horror',
  28: 'Action',
  35: 'Comedy',
  36: 'History',
  37: 'Western',
  53: 'Thriller',
  80: 'Crime',
  99: 'Documentary',
  878: 'Sci-Fi',
  9648: 'Mystery',
  10402: 'Music',
  10749: 'Romance',
  10751: 'Family',
  10752: 'War',
  10770: 'TV Movie',
}
const celebrationParticles = Array.from({ length: 26 }, (_, index) => index)

function imageUrl(path, size = 'w780') {
  if (!path) return ''
  if (path.startsWith('https://') || path.startsWith('http://')) return path
  return `${TMDB_IMAGE_ROOT}/${size}${path.startsWith('/') ? path : `/${path}`}`
}

function Icon({ name }) {
  const paths = {
    plus: <path d="M12 5v14M5 12h14" />,
    arrow: <path d="M5 12h14m-7-7 7 7-7 7" />,
    heart: <path d="M20.8 8.6c0 5.1-8.8 10-8.8 10s-8.8-4.9-8.8-10a4.6 4.6 0 0 1 8.8-1.8 4.6 4.6 0 0 1 8.8 1.8Z" />,
    camera: <><rect x="3" y="6" width="13" height="12" rx="2" /><path d="m16 10 5-3v10l-5-3" /></>,
    close: <path d="m18 6-12 12M6 6l12 12" />,
    undo: <><path d="M9 14 4 9l5-5" /><path d="M4 9h9a6 6 0 0 1 0 12h-2" /></>,
    copy: <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></>,
    sparkles: <><path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z" /><path d="m19 14 .9 2.1L22 17l-2.1.9L19 20l-.9-2.1L16 17l2.1-.9L19 14Z" /></>,
  }

  return (
    <svg aria-hidden="true" className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  )
}

function Poster({ movie, loading = 'eager' }) {
  const [failed, setFailed] = useState(false)
  const src = imageUrl(movie?.poster_path)

  if (!src || failed) {
    return (
      <div className="poster-fallback" role="img" aria-label={`Poster unavailable for ${movie?.title || 'this movie'}`}>
        <span className="fallback-mark"><Icon name="sparkles" /></span>
        <span>Artwork unavailable</span>
      </div>
    )
  }

  return (
    <img
      className="movie-poster"
      src={src}
      alt={`Poster for ${movie.title}`}
      width="500"
      height="750"
      loading={loading}
      decoding="async"
      onError={() => setFailed(true)}
    />
  )
}

function movieYear(movie) {
  return movie?.release_date?.slice(0, 4) || null
}

function browsingKey(code, user) {
  return `moviematch.browse.${encodeURIComponent(code)}.${encodeURIComponent(user)}`
}

function seenMatchesKey(code, user) {
  return `moviematch.celebrated.${encodeURIComponent(code)}.${encodeURIComponent(user)}`
}

function getPreviouslySeenMatchIds(code, user) {
  try {
    const saved = JSON.parse(localStorage.getItem(seenMatchesKey(code, user)) || '[]')
    return Array.isArray(saved) ? saved : []
  } catch {
    return []
  }
}

function readBrowsingState(code, user, pool) {
  try {
    const saved = JSON.parse(localStorage.getItem(browsingKey(code, user)) || 'null')
    return restoreBrowseState(saved, pool)
  } catch {
    return { position: 0, history: [] }
  }
}

function App() {
  const [screen, setScreen] = useState('home')
  const [username, setUsername] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('moviematch.room') || '{}').username || ''
    } catch {
      return ''
    }
  })
  const [roomCodeInput, setRoomCodeInput] = useState('')
  const [room, setRoom] = useState(null)
  const [movies, setMovies] = useState([])
  const [matches, setMatches] = useState([])
  const [members, setMembers] = useState([])
  const [activeTab, setActiveTab] = useState('pool')
  const [selectedMovie, setSelectedMovie] = useState(null)
  const [pendingMovieIds, setPendingMovieIds] = useState(() => new Set())
  const [browsePosition, setBrowsePosition] = useState(0)
  const [browseHistory, setBrowseHistory] = useState([])
  const [dragX, setDragX] = useState(0)
  const [swipeExit, setSwipeExit] = useState('')
  const [poolLoading, setPoolLoading] = useState(false)
  const [matchNotice, setMatchNotice] = useState('')
  const [celebrationMovie, setCelebrationMovie] = useState(null)
  const [socketStatus, setSocketStatus] = useState('connecting')
  const [restoring, setRestoring] = useState(() => {
    try {
      const savedRoom = JSON.parse(localStorage.getItem('moviematch.room') || 'null')
      return Boolean(savedRoom?.code && savedRoom?.username)
    } catch {
      return false
    }
  })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [homeAction, setHomeAction] = useState(null)
  const socketRef = useRef(null)
  const notificationTimeout = useRef(null)
  const celebrationTimerRef = useRef(null)
  const celebrationQueueRef = useRef([])
  const activeCelebrationRef = useRef(null)
  const pendingMovieIdsRef = useRef(new Set())
  const swipeLockRef = useRef(false)
  const swipeTimerRef = useRef(null)
  const browseReadyKeyRef = useRef('')
  const matchTrackerKeyRef = useRef('')
  const knownMatchIdsRef = useRef(new Set())
  const [pointerStartX, setPointerStartX] = useState(null)
  const isHost = room?.host_id === username

  const scheduleNextCelebration = useCallback((movie) => {
    celebrationTimerRef.current = window.setTimeout(() => {
      celebrationTimerRef.current = null
      activeCelebrationRef.current = movie
      setCelebrationMovie(movie)
    }, 320)
  }, [])

  const dismissCelebration = useCallback(() => {
    activeCelebrationRef.current = null
    setCelebrationMovie(null)
    const nextMovie = celebrationQueueRef.current.shift()
    if (nextMovie) scheduleNextCelebration(nextMovie)
  }, [scheduleNextCelebration])

  const recoverRoomState = useCallback(async (
    code,
    user,
    initialize = false,
  ) => {
    setPoolLoading(true)
    try {
      const state = await roomApi.getState(code, user)
      setRoom(state.room)
      setMembers(state.members)
      setMovies(state.movies)
      setMatches(state.matches)
      const matchKey = seenMatchesKey(code, user)
      const trackerKey = `${code}:${user}`
      if (matchTrackerKeyRef.current !== trackerKey) {
        matchTrackerKeyRef.current = trackerKey
        knownMatchIdsRef.current = createMatchTracker(
          state.matches,
          getPreviouslySeenMatchIds(code, user),
        )
      } else {
        for (const movie of state.matches) {
          knownMatchIdsRef.current.add(Number(movie.id))
        }
      }
      localStorage.setItem(
        matchKey,
        JSON.stringify([...knownMatchIdsRef.current]),
      )
      setScreen(state.room.status === 'waiting' ? 'lobby' : 'browse')
      const key = browsingKey(code, user)
      if (browseReadyKeyRef.current !== key) {
        const savedBrowseState = readBrowsingState(code, user, state.movies)
        browseReadyKeyRef.current = key
        setBrowsePosition(savedBrowseState.position)
        setBrowseHistory(savedBrowseState.history)
        setDragX(0)
        setSwipeExit('')
      }
      if (initialize) {
        setActiveTab(state.room.status === 'ended' ? 'matches' : 'pool')
      }
      setRestoring(false)
      return state
    } finally {
      setPoolLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    let reconnectTimer
    let socket

    function connect(code, user) {
      if (cancelled) return
      setSocketStatus('connecting')
      socket = new WebSocket(roomApi.websocketUrl(code, user))
      socketRef.current = socket

      socket.onopen = async () => {
        setSocketStatus('connected')
        try {
          await recoverRoomState(code, user)
        } catch (stateError) {
          setError(stateError.message)
        }
      }

      socket.onmessage = async (messageEvent) => {
        try {
          const message = JSON.parse(messageEvent.data)
          const data = message.data || {}

          if (message.event === 'member_joined') {
            setMembers((current) => current.includes(data.username)
              ? current
              : [...current, data.username])
          } else if (message.event === 'member_left') {
            setMembers((current) => current.filter((member) => member !== data.username))
          } else if (message.event === 'room_started') {
            await recoverRoomState(code, user)
          } else if (message.event === 'match_found' && data.movie) {
            const trackerKey = `${code}:${user}`
            if (matchTrackerKeyRef.current !== trackerKey) {
              matchTrackerKeyRef.current = trackerKey
              knownMatchIdsRef.current = createMatchTracker(
                [],
                getPreviouslySeenMatchIds(code, user),
              )
            }
            const matchEvent = recordMatchEvent(
              knownMatchIdsRef.current,
              data.movie,
            )
            knownMatchIdsRef.current = matchEvent.knownIds
            if (matchEvent.isNew) {
              localStorage.setItem(
                seenMatchesKey(code, user),
                JSON.stringify([...knownMatchIdsRef.current]),
              )
              setMatches((current) => current.some((movieItem) => movieItem.id === data.movie.id)
                ? current
                : [...current, data.movie])
              setMatchNotice(`${data.movie.title} is a match!`)
              setSelectedMovie(null)
              if (activeCelebrationRef.current || celebrationTimerRef.current) {
                celebrationQueueRef.current.push(data.movie)
              } else {
                scheduleNextCelebration(data.movie)
              }
            }
          } else if (message.event === 'room_ended') {
            if (data.reason === 'cancelled') {
              socketRef.current?.close()
              localStorage.removeItem('moviematch.room')
              setRoom(null)
              setMovies([])
              setMatches([])
              setMembers([])
              setScreen('home')
              setError('The host cancelled this room.')
              return
            }
            try {
              const state = await recoverRoomState(code, user)
              if (state.room.status === 'ended') setActiveTab('matches')
            } catch (stateError) {
              setRoom((current) => current ? { ...current, status: 'ended' } : current)
              setActiveTab('matches')
              setError(stateError.message)
            }
          }
        } catch (eventError) {
          setError(eventError.message || 'Unable to update the room.')
        }
      }

      socket.onerror = () => {
        setSocketStatus('reconnecting')
      }
      socket.onclose = (event) => {
        if (cancelled) return
        if (event.code === 1008) {
          setSocketStatus('disconnected')
          localStorage.removeItem('moviematch.room')
          setRoom(null)
          setMovies([])
          setMatches([])
          setMembers([])
          setScreen('home')
          setError('This room is no longer available.')
          return
        }
        setSocketStatus('reconnecting')
        reconnectTimer = window.setTimeout(() => connect(code, user), 1500)
      }
    }

    if (room?.code && username) {
      connect(room.code, username)
    } else {
      let savedRoom
      try {
        savedRoom = JSON.parse(localStorage.getItem('moviematch.room') || 'null')
      } catch {
        localStorage.removeItem('moviematch.room')
      }

      if (savedRoom?.code && savedRoom?.username) {
        queueMicrotask(() => {
          if (cancelled) return
          recoverRoomState(savedRoom.code, savedRoom.username, true)
            .catch((stateError) => {
              localStorage.removeItem('moviematch.room')
              setError(`Could not restore your room: ${stateError.message}`)
              setRestoring(false)
            })
        })
      }
    }

    return () => {
      cancelled = true
      window.clearTimeout(reconnectTimer)
      socket?.close()
      if (socketRef.current === socket) socketRef.current = null
    }
  }, [room?.code, username, recoverRoomState, scheduleNextCelebration])

  useEffect(() => {
    if (!copied) return undefined
    const timeout = window.setTimeout(() => setCopied(false), 1600)
    return () => window.clearTimeout(timeout)
  }, [copied])

  useEffect(() => {
    if (!room?.code || !username) return
    const key = browsingKey(room.code, username)
    if (browseReadyKeyRef.current !== key) return
    localStorage.setItem(key, JSON.stringify({
      position: browsePosition,
      history: browseHistory,
    }))
  }, [browseHistory, browsePosition, room?.code, username])

  useEffect(() => () => {
    window.clearTimeout(swipeTimerRef.current)
    window.clearTimeout(celebrationTimerRef.current)
  }, [])

  async function enterRoom(action) {
    const cleanUsername = username.trim()
    if (!cleanUsername) {
      setError('Add your name to get started.')
      return
    }

    setBusy(true)
    setError('')
    try {
      const code = roomCodeInput.trim().toUpperCase()
      const nextRoom = action === 'create'
        ? await roomApi.create(cleanUsername)
        : await roomApi.join(code, cleanUsername)

      setUsername(cleanUsername)
      setRoom(nextRoom)
      browseReadyKeyRef.current = ''
      matchTrackerKeyRef.current = `${nextRoom.code}:${cleanUsername}`
      knownMatchIdsRef.current = createMatchTracker()
      setBrowsePosition(0)
      setBrowseHistory([])
      setMembers([...new Set([nextRoom.host_id, cleanUsername])])
      setMovies([])
      setMatches([])
      setActiveTab('pool')
      setScreen(nextRoom.status === 'started' ? 'browse' : 'lobby')
      localStorage.setItem(
        'moviematch.room',
        JSON.stringify({ code: nextRoom.code, username: cleanUsername }),
      )
      if (nextRoom.status === 'started') {
        await recoverRoomState(nextRoom.code, cleanUsername, true)
      }
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  async function startRoom() {
    if (!room) return
    setBusy(true)
    setError('')
    try {
      await roomApi.start(room.code, username)
      await recoverRoomState(room.code, username, true)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  async function submitDecision(movieItem, decision) {
    if (
      !room
      || movieItem.my_decision === 'like'
      || pendingMovieIdsRef.current.has(movieItem.id)
    ) return false
    pendingMovieIdsRef.current.add(movieItem.id)
    setPendingMovieIds((current) => new Set(current).add(movieItem.id))
    setError('')
    try {
      const result = await roomApi.decide(
        room.code,
        movieItem.id,
        username,
        decision,
      )
      setMovies((current) => current.map((item) => item.id === movieItem.id
        ? { ...item, my_decision: result.decision }
        : item))
      if (result.matched && result.match) {
        setMatches((current) => current.some((item) => item.id === result.match.id)
          ? current
          : [...current, result.match])
      }
      return true
    } catch (requestError) {
      setError(requestError.message)
      try {
        await recoverRoomState(room.code, username)
      } catch {
        // Preserve the original decision error; the state request can be retried.
      }
      return false
    } finally {
      pendingMovieIdsRef.current.delete(movieItem.id)
      setPendingMovieIds((current) => {
        const next = new Set(current)
        next.delete(movieItem.id)
        return next
      })
    }
  }

  function undoBrowse() {
    if (swipeLockRef.current || !browseHistory.length) return
    const previousState = undoBrowseState(
      { position: browsePosition, history: browseHistory },
      movies,
    )
    if (!previousState) return
    setBrowseHistory(previousState.history)
    setBrowsePosition(previousState.position)
    setDragX(0)
    setSwipeExit('')
  }

  async function swipeMovie(movieItem, direction) {
    if (swipeLockRef.current || !movieItem || room?.status !== 'started') return
    swipeLockRef.current = true
    if (direction === 'right') {
      const saved = await submitDecision(movieItem, 'like')
      if (!saved) {
        swipeLockRef.current = false
        setDragX(0)
        return
      }
    }

    setSwipeExit(direction)
    swipeTimerRef.current = window.setTimeout(() => {
      const nextState = advanceBrowseState(
        { position: browsePosition, history: browseHistory },
        movieItem.id,
      )
      setBrowseHistory(nextState.history)
      setBrowsePosition(nextState.position)
      setSwipeExit('')
      setDragX(0)
      swipeLockRef.current = false
    }, 260)
  }

  function handleCardPointerDown(event) {
    if (event.button !== 0 || event.target.closest('button')) return
    setPointerStartX(event.clientX)
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function handleCardPointerMove(event) {
    if (pointerStartX === null || swipeLockRef.current) return
    setDragX(event.clientX - pointerStartX)
  }

  function handleCardPointerUp(event) {
    if (pointerStartX === null) return
    const distance = event.clientX - pointerStartX
    setPointerStartX(null)
    if (Math.abs(distance) >= 90) {
      const movieItem = movies.find(
        (movie) => movie.id === Number(event.currentTarget.dataset.movieId),
      )
      void swipeMovie(movieItem, distance > 0 ? 'right' : 'left')
    } else {
      setDragX(0)
    }
  }

  async function leaveRoom() {
    if (!room) return
    setBusy(true)
    setError('')
    try {
      await roomApi.leave(room.code, username)
      socketRef.current?.close()
      setRoom(null)
      setMovies([])
      setMatches([])
      setMembers([])
      setScreen('home')
      localStorage.removeItem('moviematch.room')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  async function endRoom() {
    if (!room) return
    setBusy(true)
    setError('')
    try {
      await roomApi.end(room.code, username)
      await recoverRoomState(room.code, username)
      setActiveTab('matches')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  async function copyRoomCode() {
    try {
      await navigator.clipboard.writeText(room.code)
      setCopied(true)
    } catch {
      setError('Could not copy the room code. Select and copy it instead.')
    }
  }

  function resetToHome() {
    socketRef.current?.close()
    setRoom(null)
    setMovies([])
    setMatches([])
    setMembers([])
    setSelectedMovie(null)
    activeCelebrationRef.current = null
    celebrationQueueRef.current = []
    window.clearTimeout(celebrationTimerRef.current)
    setCelebrationMovie(null)
    setPendingMovieIds(new Set())
    setError('')
    setRoomCodeInput('')
    setHomeAction(null)
    setScreen('home')
    localStorage.removeItem('moviematch.room')
  }

  useEffect(() => {
    if (!matchNotice) return undefined
    notificationTimeout.current = window.setTimeout(() => setMatchNotice(''), 5000)
    return () => window.clearTimeout(notificationTimeout.current)
  }, [matchNotice])

  useEffect(() => {
    if (!selectedMovie && !celebrationMovie) return undefined
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const handleKeyDown = (event) => {
      if (event.key !== 'Escape') return
      if (celebrationMovie) dismissCelebration()
      else setSelectedMovie(null)
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [selectedMovie, celebrationMovie, dismissCelebration])

  return (
    <main className="app-shell">
      <header className="topbar">
        <button className="brand" type="button" onClick={resetToHome} aria-label="MovieMatch home">
          <span className="brand-symbol"><Icon name="camera" /></span>
          <span>movie<span className="brand-accent">match</span></span>
        </button>
        {screen === 'home' && (
          <nav className="topbar-nav" aria-label="Main navigation">
            <a href="#how-it-works">How it works</a>
            <a href="#room-privacy">Room privacy</a>
          </nav>
        )}
        {room && (
          <div className="room-pill">
            <span>ROOM</span>
            <strong>{room.code}</strong>
          </div>
        )}
      </header>

      {error && (
        <div className="notice" role="alert">
          <span>{error}</span>
          <button type="button" aria-label="Dismiss message" onClick={() => setError('')}><Icon name="close" /></button>
        </div>
      )}

      {restoring && !room && (
        <section className="restore-state" role="status">
          <span className="waiting-pulse" /> Restoring your movie room…
        </section>
      )}

      {screen === 'home' && (
        <section className="home page-enter">
          <div className="landing">
            <div className="landing-copy">
              <span className="eyebrow"><span className="eyebrow-line" /> MOVIE NIGHT, MADE EASY</span>
              <h1>Stop scrolling.<br /><span className="gradient-text">Start matching.</span></h1>
              <p className="landing-description">Find a movie you want to watch together. Real-time matching built for movie nights.</p>
              {!homeAction ? (
                <div className="home-actions">
                  <button className="button button-primary" type="button" onClick={() => setHomeAction('create')}>Create a room <Icon name="plus" /></button>
                  <button className="button button-secondary" type="button" onClick={() => setHomeAction('join')}>Join a room <Icon name="arrow" /></button>
                </div>
              ) : (
                <div className="landing-form">
                  <div className="form-heading">
                    <div><span className="section-kicker">{homeAction === 'create' ? 'NEW SCREENING ROOM' : 'JOIN A FRIEND'}</span><strong>{homeAction === 'create' ? 'Create your matching room' : 'Enter your room code'}</strong></div>
                    <button className="form-back" type="button" onClick={() => setHomeAction(null)}>Back</button>
                  </div>
                  {homeAction === 'join' && (
                    <>
                      <label className="field-label" htmlFor="room-code">ROOM CODE</label>
                      <input
                        id="room-code"
                        autoCapitalize="characters"
                        maxLength={6}
                        placeholder="ABC123"
                        value={roomCodeInput}
                        onChange={(event) => setRoomCodeInput(event.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''))}
                      />
                    </>
                  )}
                  <label className="field-label" htmlFor="username">{homeAction === 'create' ? 'CHOOSE NICKNAME' : 'YOUR NICKNAME'}</label>
                  <input
                    id="username"
                    autoComplete="nickname"
                    maxLength={32}
                    placeholder="What should we call you?"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    onKeyDown={(event) => event.key === 'Enter' && enterRoom(homeAction)}
                  />
                  <button className="button button-primary create-button" type="button" disabled={busy || (homeAction === 'join' && !roomCodeInput.trim())} onClick={() => enterRoom(homeAction)}>
                    {busy ? 'One moment…' : homeAction === 'create' ? 'Create room' : 'Join room'} <Icon name="arrow" />
                  </button>
                  <p className="form-footnote">No account needed. Just invite your crew and find a film you’ll all love.</p>
                </div>
              )}
            </div>
            <div className="landing-art" aria-hidden="true">
              <div className="orbit orbit-one" /><div className="orbit orbit-two" />
              <div className="art-card art-card-back-side"><span className="art-stars">✦</span><span>ONE ROOM.<br />ONE CREW.<br />GOOD PICKS.</span></div>
              <div className="art-card art-card-back"><span className="art-stars">✦</span><span>YOUR NEXT<br />MOVIE NIGHT<br />STARTS HERE.</span></div>
              <div className="art-card art-card-front"><span className="art-card-top">MOVIEMATCH</span><span className="art-play"><span /></span><span className="art-card-bottom">FIND A FILM.<br /><b>VOTE TOGETHER.</b></span></div>
              <div className="floating-tag tag-top"><Icon name="sparkles" /> no more scrolling</div>
              <div className="floating-tag tag-bottom"><Icon name="heart" /> chosen together</div>
              <span className="art-spark spark-one">✳</span><span className="art-spark spark-two">✦</span>
            </div>
          </div>
          <section className="how-section" id="how-it-works">
            <div className="how-heading"><h2>Match in three simple steps</h2><p>How MovieMatch makes endless scrolling a thing of the past.</p></div>
            <div className="steps-grid">
              <article className="step-card"><span className="step-number">1</span><h3>Create</h3><p>Start a room in seconds. Invite friends with a 6-character code. No sign-up needed.</p></article>
              <article className="step-card"><span className="step-number">2</span><h3>Explore</h3><p>Browse the shared movie pool at your own pace. Like or skip anything that catches your eye.</p></article>
              <article className="step-card"><span className="step-number">3</span><h3>Match</h3><p>When two members like the same movie, everyone sees it in the room’s matches.</p></article>
            </div>
          </section>
        </section>
      )}

      {screen === 'lobby' && room && (
        <section className="lobby page-enter">
          <span className="eyebrow"><span className="eyebrow-line" /> YOUR PRIVATE SCREENING ROOM</span>
          <div className="lobby-heading"><h1>Bring your<br /><span className="gradient-text">movie crew.</span></h1><p>Share your room code and get everyone in. Your first pick is just a few taps away.</p></div>
          <div className="lobby-content">
            <div className="invite-card">
              <div className="invite-card-heading"><span className="invite-icon"><Icon name="sparkles" /></span><div><strong>Room code</strong><span>Send this to your friends</span></div></div>
              <button className="code-copy" type="button" onClick={copyRoomCode} aria-label="Copy room code">
                <span>{room.code.split('').map((letter, index) => <b key={`${letter}-${index}`}>{letter}</b>)}</span>
                <span className="copy-action"><Icon name="copy" /> {copied ? 'COPIED' : 'COPY'}</span>
              </button>
              <p className="invite-tip">Up to 3 movie lovers can join a room.</p>
            </div>
            <div className="crew-card">
              <div className="crew-heading"><div><span className="section-kicker">THE CREW</span><strong>{members.length} {members.length === 1 ? 'person' : 'people'} in the room</strong></div><span className="live-label"><i /> LIVE</span></div>
              <div className="crew-list">{members.map((member, index) => <div className="crew-member" key={member}><span className={`member-avatar avatar-${index % 4}`}>{member.slice(0, 1).toUpperCase()}</span><span>{member}{member === username ? ' (you)' : ''}</span>{member === room.host_id && <span className="host-label">HOST</span>}</div>)}</div>
              <div className="waiting-note"><span className="waiting-pulse" /> Waiting for your crew to join…</div>
            </div>
          </div>
          <div className="lobby-actions">
            <button className="button button-primary" type="button" disabled={busy || !isHost || members.length < 2} onClick={startRoom}>{busy ? 'Starting…' : 'Start movie night'} <Icon name="arrow" /></button>
            {isHost && members.length < 2 && <span className="action-hint">Invite at least one friend to start</span>}
            {!isHost && <span className="action-hint">The host will start the movie night</span>}
            <button className="text-button" type="button" disabled={busy} onClick={leaveRoom}>Leave room</button>
          </div>
        </section>
      )}

      {screen === 'browse' && room && (
        <section className="pool-room page-enter">
          <div className="pool-heading">
            <div>
              <span className="eyebrow"><span className="eyebrow-line" /> YOUR MOVIE NIGHT</span>
              <h1>Find your next<br /><span className="gradient-text">movie match.</span></h1>
              <p>Browse at your own pace. Your choices never move anyone else’s screen.</p>
            </div>
            <div className="pool-room-status">
              <span className={`live-label ${socketStatus !== 'connected' ? 'live-label-offline' : ''}`}>
                <i /> {socketStatus === 'connected' ? 'LIVE' : 'RECONNECTING'}
              </span>
              <strong>{members.length} {members.length === 1 ? 'member' : 'members'}</strong>
              <span className="pool-member-names">{members.join(' · ')}</span>
              <div className="mini-avatars">
                {members.slice(0, 3).map((member, index) => (
                  <span className={`member-avatar avatar-${index % 4}`} key={member}>
                    {member.slice(0, 1).toUpperCase()}
                  </span>
                ))}
              </div>
              <span className="pool-room-code">ROOM {room.code}</span>
            </div>
          </div>

          {room.status === 'ended' && (
            <div className="room-ended-banner" role="status">
              Movie night has ended. Your discovered matches are still here.
            </div>
          )}

          {matchNotice && (
            <div className="match-toast" role="status" aria-live="polite">
              <Icon name="heart" />
              <span>{matchNotice}</span>
              <button type="button" aria-label="Dismiss match notification" onClick={() => setMatchNotice('')}>
                <Icon name="close" />
              </button>
            </div>
          )}

          <div className="pool-tabs" role="tablist" aria-label="Room movies">
            <button
              className={activeTab === 'pool' ? 'pool-tab active' : 'pool-tab'}
              type="button"
              role="tab"
              aria-selected={activeTab === 'pool'}
              onClick={() => setActiveTab('pool')}
            >
              Browse pool <span>{movies.length}</span>
            </button>
            <button
              className={activeTab === 'matches' ? 'pool-tab active' : 'pool-tab'}
              type="button"
              role="tab"
              aria-selected={activeTab === 'matches'}
              onClick={() => setActiveTab('matches')}
            >
              Your matches <span>{matches.length}</span>
            </button>
            {isHost && room.status === 'started' && (
              <button className="text-button pool-end-button" type="button" disabled={busy} onClick={endRoom}>
                {busy ? 'Ending…' : 'End movie night'}
              </button>
            )}
          </div>

          {activeTab === 'pool' ? (
            !movies.length ? (
              <div className="pool-empty swipe-empty" role={poolLoading || restoring ? 'status' : 'alert'}>
                <Icon name="sparkles" />
                <h2>{poolLoading || restoring ? 'Loading your movie pool…' : 'No movies available yet'}</h2>
                <p>{poolLoading || restoring
                  ? 'Getting your room back in sync.'
                  : 'The shared pool is empty. Try loading your room again.'}</p>
                {!poolLoading && !restoring && (
                  <button
                    className="button button-secondary"
                    type="button"
                    onClick={() => recoverRoomState(room.code, username).catch((stateError) => setError(stateError.message))}
                  >
                    Try again
                  </button>
                )}
              </div>
            ) : browsePosition >= movies.length ? (
              <div className="pool-empty swipe-exhausted" role="status">
                <Icon name="sparkles" />
                <span className="section-kicker">THAT’S THE POOL</span>
                <h2>You’ve seen every movie</h2>
                <p>Undo to revisit a skipped card, or check your room matches.</p>
                <button
                  className="swipe-undo-button"
                  type="button"
                  disabled={!browseHistory.length || room.status !== 'started'}
                  onClick={undoBrowse}
                >
                  <Icon name="undo" /> Undo last swipe
                </button>
              </div>
            ) : (
              (() => {
                const movieItem = movies[browsePosition]
                const genres = movieItem.genre_ids
                  ?.map((genreId) => TMDB_GENRES[genreId])
                  .filter(Boolean) || []
                const pending = pendingMovieIds.has(movieItem.id)
                const isMatch = matches.some((match) => match.id === movieItem.id)
                const cardStyle = {
                  '--drag-x': `${dragX}px`,
                  '--drag-rotation': `${dragX / 18}deg`,
                }

                return (
                  <div className="swipe-discovery">
                    <div className="swipe-progress" aria-label={`Movie ${browsePosition + 1} of ${movies.length}`}>
                      <div className="swipe-progress-track">
                        <span style={{ width: `${((browsePosition + 1) / movies.length) * 100}%` }} />
                      </div>
                      <span>{String(browsePosition + 1).padStart(2, '0')} <i>/</i> {String(movies.length).padStart(2, '0')}</span>
                    </div>
                    <div className="swipe-stage" role="tabpanel" aria-label="Shared movie pool">
                      <div className="swipe-stack-shadow" aria-hidden="true" />
                      <article
                        key={movieItem.id}
                        className={`swipe-card${dragX > 12 ? ' is-dragging-like' : dragX < -12 ? ' is-dragging-skip' : ''}${swipeExit ? ` swipe-exit-${swipeExit}` : ''}`}
                        data-movie-id={movieItem.id}
                        style={cardStyle}
                        onPointerDown={handleCardPointerDown}
                        onPointerMove={handleCardPointerMove}
                        onPointerUp={handleCardPointerUp}
                        onPointerCancel={() => {
                          setPointerStartX(null)
                          setDragX(0)
                        }}
                      >
                        <div className="swipe-card-poster">
                          <Poster movie={movieItem} loading="eager" />
                        </div>
                        <div className="swipe-card-shade" />
                        <span className="swipe-stamp swipe-stamp-like" aria-hidden="true">LIKE</span>
                        <span className="swipe-stamp swipe-stamp-skip" aria-hidden="true">SKIP</span>
                        <div className="swipe-card-copy">
                          <div className="swipe-card-labels">
                            <span className="section-kicker">MOVIE {String(browsePosition + 1).padStart(2, '0')}</span>
                            {isMatch && <span className="mutual-match-badge"><Icon name="heart" /> MUTUAL MATCH</span>}
                          </div>
                          <h2>{movieItem.title}</h2>
                          <div className="pool-movie-facts">
                            {movieYear(movieItem) && <span>{movieYear(movieItem)}</span>}
                            {genres.slice(0, 3).map((genre) => <span key={genre}>{genre}</span>)}
                            {movieItem.vote_average > 0 && (
                              <span className="pool-rating">★ {movieItem.vote_average.toFixed(1)} / 10</span>
                            )}
                          </div>
                          <p>{movieItem.overview || 'No overview is available for this movie yet.'}</p>
                          <button
                            className="swipe-details-button"
                            type="button"
                            onClick={() => setSelectedMovie(movieItem)}
                          >
                            View movie details <Icon name="arrow" />
                          </button>
                        </div>
                      </article>
                    </div>
                    <div className="swipe-controls" aria-label="Movie decisions">
                      <button
                        className="swipe-undo-button"
                        type="button"
                        disabled={!browseHistory.length || pending || room.status !== 'started'}
                        onClick={undoBrowse}
                        aria-label="Undo and revisit the previous movie"
                      >
                        <Icon name="undo" /><span>Undo</span>
                      </button>
                      <button
                        className="swipe-action swipe-skip"
                        type="button"
                        disabled={pending || room.status !== 'started' || Boolean(swipeExit)}
                        onClick={() => void swipeMovie(movieItem, 'left')}
                        aria-label={`Skip ${movieItem.title}`}
                      >
                        <Icon name="close" /><span>Skip</span>
                      </button>
                      <button
                        className={`swipe-action swipe-like${movieItem.my_decision === 'like' ? ' is-liked' : ''}`}
                        type="button"
                        disabled={pending || movieItem.my_decision === 'like' || room.status !== 'started' || Boolean(swipeExit)}
                        onClick={() => void swipeMovie(movieItem, 'right')}
                        aria-label={movieItem.my_decision === 'like' ? `Already liked ${movieItem.title}` : `Like ${movieItem.title}`}
                      >
                        <Icon name="heart" /><span>{pending ? 'Saving…' : movieItem.my_decision === 'like' ? 'Liked' : 'Like'}</span>
                      </button>
                    </div>
                    <p className="swipe-instructions">Swipe right to like <span>·</span> left to skip</p>
                  </div>
                )
              })()
            )
          ) : (
            <div className="matches-panel" role="tabpanel" aria-label="Discovered matches">
              {matches.length ? (
                <div className="matches-grid">
                  {matches.map((match) => (
                    <button className="match-card" type="button" key={match.id} onClick={() => setSelectedMovie(match)}>
                      <div className="match-poster"><Poster movie={match} loading="lazy" /></div>
                      <span className="section-kicker"><Icon name="heart" /> ROOM MATCH</span>
                      <strong>{match.title}</strong>
                      {movieYear(match) && <span>{movieYear(match)}</span>}
                    </button>
                  ))}
                </div>
              ) : (
                <div className="pool-empty">
                  <Icon name="heart" />
                  <h2>No matches yet</h2>
                  <p>As soon as two members like the same movie, it will show up here.</p>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {selectedMovie && (
        <div className="movie-dialog-backdrop" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setSelectedMovie(null)
        }}>
          <section
            className="movie-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="movie-dialog-title"
          >
            <button className="movie-dialog-close" type="button" aria-label="Close movie details" onClick={() => setSelectedMovie(null)}>
              <Icon name="close" />
            </button>
            <div className="movie-dialog-poster"><Poster movie={selectedMovie} loading="lazy" /></div>
            <div className="movie-dialog-content">
              <span className="section-kicker">{selectedMovie.my_decision ? 'YOUR DECISION' : 'MOVIE DETAILS'}</span>
              <h2 id="movie-dialog-title">{selectedMovie.title}</h2>
              <div className="pool-movie-facts">
                {movieYear(selectedMovie) && <span>{movieYear(selectedMovie)}</span>}
                {selectedMovie.vote_average > 0 && <span>★ {selectedMovie.vote_average.toFixed(1)} / 10</span>}
              </div>
              <p>{selectedMovie.overview || 'No overview is available for this movie yet.'}</p>
            </div>
          </section>
        </div>
      )}

      {celebrationMovie && (
        <div className="match-celebration-backdrop">
          <section
            className="match-celebration"
            role="dialog"
            aria-modal="true"
            aria-labelledby="match-celebration-title"
            aria-describedby="match-celebration-description"
          >
            <div className="celebration-burst" aria-hidden="true">
              <span className="celebration-ring celebration-ring-one" />
              <span className="celebration-ring celebration-ring-two" />
              {celebrationParticles.map((particle) => (
                <span
                  className={`celebration-particle celebration-particle-${particle % 4}`}
                  key={particle}
                  style={{
                    '--particle-angle': `${(360 / celebrationParticles.length) * particle}deg`,
                    '--particle-delay': `${(particle % 7) * 35}ms`,
                    '--particle-distance': `${125 + ((particle * 37) % 145)}px`,
                  }}
                >
                  {particle % 3 === 0 ? '♥' : particle % 3 === 1 ? '✦' : '✧'}
                </span>
              ))}
            </div>
            <div className="celebration-content">
              <span className="celebration-eyebrow">THE ROOM HAS SPOKEN</span>
              <h2 id="match-celebration-title">MUTUAL MATCH!</h2>
              <div className="celebration-poster-frame">
                <div className="celebration-poster">
                  <Poster movie={celebrationMovie} loading="eager" />
                </div>
              </div>
              <h3>{celebrationMovie.title}</h3>
              <p id="match-celebration-description">
                {movieYear(celebrationMovie) && <span>{movieYear(celebrationMovie)} <i>·</i> </span>}
                You both picked the same movie. Movie night is looking good.
              </p>
              <div className="celebration-actions">
                <button
                  className="celebration-details-button"
                  type="button"
                  autoFocus
                  onClick={() => {
                    setSelectedMovie(celebrationMovie)
                    dismissCelebration()
                  }}
                >
                  View movie details
                </button>
                <button
                  className="celebration-continue-button"
                  type="button"
                  onClick={dismissCelebration}
                >
                  Keep browsing
                </button>
              </div>
              <span className="celebration-match-saved"><Icon name="heart" /> Added to your Matches</span>
            </div>
          </section>
        </div>
      )}

      <footer className="site-footer" id="room-privacy"><span>© 2026 MOVIEMATCH</span><span>YOUR ROOM, YOUR MOVIE NIGHT <Icon name="heart" /></span></footer>
    </main>
  )
}

export default App
