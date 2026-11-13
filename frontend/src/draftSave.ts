import type { ReviewStatus } from './api'

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error' | 'stale'

// #62 must also enforce permissions, conflict decisions and freshness at approval
// time. This is only the local save prerequisite, never server authorization.
export function draftSaveGate(status: ReviewStatus, dirty: boolean, pending: boolean, saveStatus: SaveStatus) {
  const editable = status === 'draft' || status === 'in_review'
  return {
    canSave: editable && !pending && saveStatus !== 'saving' && saveStatus !== 'stale'
      && (dirty || saveStatus === 'error'),
    blocksApproval: !editable || dirty || pending || saveStatus === 'saving'
      || saveStatus === 'error' || saveStatus === 'stale',
  }
}
