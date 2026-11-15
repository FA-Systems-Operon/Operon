import '@testing-library/jest-dom/vitest'
import { beforeEach, vi } from 'vitest'

// Tests see every page by default, including the ones hidden in Release 1 (#160).
// features.test.tsx turns the flags off to check the hiding itself.
beforeEach(() => {
  vi.stubEnv('FEATURE_BRAIN', 'true')
  vi.stubEnv('FEATURE_WORKFORCE', 'true')
})
