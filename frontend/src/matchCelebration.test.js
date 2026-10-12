import assert from 'node:assert/strict'
import test from 'node:test'
import {
  createMatchTracker,
  recordMatchEvent,
} from './matchCelebration.js'

const match = { id: 101, title: 'Movie One' }

test('a confirmed match event is accepted once and duplicates are ignored', () => {
  const tracker = createMatchTracker()
  const first = recordMatchEvent(tracker, match)
  const duplicate = recordMatchEvent(first.knownIds, match)

  assert.equal(first.isNew, true)
  assert.equal(duplicate.isNew, false)
  assert.equal(duplicate.knownIds.has(match.id), true)
})

test('recovered match state prevents replaying a celebration after reconnect', () => {
  const tracker = createMatchTracker([match])
  const eventAfterReconnect = recordMatchEvent(tracker, match)

  assert.equal(eventAfterReconnect.isNew, false)
})

test('previously celebrated matches remain deduplicated after a page reload', () => {
  const tracker = createMatchTracker([], ['101'])
  const delayedDuplicate = recordMatchEvent(tracker, match)

  assert.equal(delayedDuplicate.isNew, false)
})

test('different confirmed matches each trigger once', () => {
  const tracker = createMatchTracker()
  const first = recordMatchEvent(tracker, match)
  const second = recordMatchEvent(first.knownIds, { id: 202, title: 'Movie Two' })

  assert.equal(first.isNew, true)
  assert.equal(second.isNew, true)
})

test('invalid match payloads never trigger a celebration', () => {
  const result = recordMatchEvent(createMatchTracker(), { title: 'Missing ID' })

  assert.equal(result.isNew, false)
  assert.equal(result.knownIds.size, 0)
})
