import type { ReviewStatus } from './api'

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error' | 'stale'

// The local prerequisite for the Approve button. The approve endpoint (#62) does
// the real checks: signed-in reviewer, and the draft is still the latest version.
export function draftSaveGate(status: ReviewStatus, dirty: boolean, pending: boolean, saveStatus: SaveStatus) {
  const editable = status === 'draft' || status === 'in_review'
  return {
    canSave: editable && !pending && saveStatus !== 'saving' && saveStatus !== 'stale'
      && (dirty || saveStatus === 'error'),
    blocksApproval: !editable || dirty || pending || saveStatus === 'saving'
      || saveStatus === 'error' || saveStatus === 'stale',
  }
}
