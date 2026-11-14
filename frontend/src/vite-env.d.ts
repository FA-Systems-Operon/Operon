/// <reference types="vite/client" />

// Feature flags (see features.ts). Vite passes them to the app as text.
interface ImportMetaEnv {
  readonly FEATURE_BRAIN?: string
  readonly FEATURE_WORKFORCE?: string
}
