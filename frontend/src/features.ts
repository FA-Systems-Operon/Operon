// Feature flags for pages that aren't finished (#160). A page whose flag is off has
// no menu tab, and opening its address goes to Command, so the demo never shows a
// blank page. Turn one on by setting FEATURE_BRAIN=true or FEATURE_WORKFORCE=true
// when starting or building the frontend (see frontend/README.md). Off by default.
export type Feature = 'brain' | 'workforce'

// Read on every call (not once at load) so tests can switch a flag with vi.stubEnv.
export function isEnabled(feature: Feature): boolean {
  const value =
    feature === 'brain' ? import.meta.env.FEATURE_BRAIN : import.meta.env.FEATURE_WORKFORCE
  return value === 'true'
}

// The page each flag hides.
const PAGES: Record<Feature, string> = {
  brain: '/brain',
  workforce: '/workforce',
}

export function isHiddenPage(path: string): boolean {
  return (Object.keys(PAGES) as Feature[]).some(
    (feature) => PAGES[feature] === path && !isEnabled(feature),
  )
}
