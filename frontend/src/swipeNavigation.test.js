import assert from 'node:assert/strict'
import test from 'node:test'
import {
  advanceBrowseState,
  restoreBrowseState,
  undoBrowseState,
} from './swipeNavigation.js'

const movies = [{ id: 101 }, { id: 202 }, { id: 303 }]

test('swiping past movies advances local browsing without setting a decision', () => {
  const initial = { position: 0, history: [] }
  const next = advanceBrowseState(initial, movies[0].id)

  assert.deepEqual(next, { position: 1, history: [101] })
  assert.deepEqual(initial, { position: 0, history: [] })
  assert.equal('decision' in next, false)
})

test('undo revisits the last skipped card so it can be liked later', () => {
  const browsed = advanceBrowseState(
    advanceBrowseState({ position: 0, history: [] }, 101),
    202,
  )

  assert.deepEqual(undoBrowseState(browsed, movies), {
    position: 1,
    history: [101],
  })
})

test('browser history restores safely and discards movies outside the pool', () => {
  assert.deepEqual(
    restoreBrowseState({ position: 2.8, history: [101, 999] }, movies),
    { position: 2, history: [101] },
  )
  assert.deepEqual(restoreBrowseState({ position: -3 }, movies), {
    position: 0,
    history: [],
  })
})

test('members maintain independent browsing histories', () => {
  const host = advanceBrowseState({ position: 0, history: [] }, 101)
  const guest = advanceBrowseState(
    advanceBrowseState({ position: 0, history: [] }, 101),
    202,
  )

  assert.deepEqual(host, { position: 1, history: [101] })
  assert.deepEqual(guest, { position: 2, history: [101, 202] })
})
