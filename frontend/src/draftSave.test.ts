import { expect, test } from 'vitest'
import { draftSaveGate, type SaveStatus } from './draftSave'
import type { ReviewStatus } from './api'

test.each<[ReviewStatus, boolean, boolean, SaveStatus, boolean, boolean]>([
  ['draft', false, false, 'idle', false, false],
  ['in_review', false, false, 'saved', false, false],
  ['draft', true, false, 'idle', true, true],
  ['draft', true, true, 'idle', false, true],
  ['draft', false, true, 'idle', false, true],
  ['draft', true, false, 'saving', false, true],
  ['draft', false, false, 'saving', false, true],
  ['draft', true, false, 'error', true, true],
  ['draft', false, false, 'error', true, true],
  ['draft', true, false, 'stale', false, true],
  ['draft', false, false, 'stale', false, true],
  ['approved', false, false, 'idle', false, true],
  ['rejected', true, false, 'error', false, true],
  ['stale', false, false, 'saved', false, true],
])('save prerequisite: %s dirty=%s pending=%s save=%s', (status, dirty, pending, save, canSave, blocksApproval) => {
  expect(draftSaveGate(status, dirty, pending, save)).toEqual({ canSave, blocksApproval })
})
