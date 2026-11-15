# Operon Frontend

## Feature flags for unfinished pages (#160)

Brain and Workforce aren't built yet, so their tabs would open a blank page. Each
has a flag, and both are **off** by default:

| Flag | Off | On (`true`) |
| --- | --- | --- |
| `FEATURE_BRAIN` | No Brain tab; `#/brain` goes to Command. Add sources and draft progress mark Command. | Brain tab shown; Add sources and draft progress mark Brain. |
| `FEATURE_WORKFORCE` | No Workforce tab; `#/workforce` goes to Command. | Workforce tab shown. |

Only the exact value `true` turns a flag on.

**Turning one on**

- Docker (dev): set it in the root `.env`, then restart the frontend:
  `docker compose up -d frontend`. Vite reads the flags when it starts.
- Without Docker: `FEATURE_BRAIN=true npm run dev`, or put it in `frontend/.env.local`.
- Production build (`Dockerfile.prod`): the flags are fixed when the app is built,
  so pass them as build args (`compose.prod.yaml` does this from `.env`) and rebuild.

**When a page is ready:** remove its flag from `src/features.ts`, the `feature`
on its tab in `components/TopNav.tsx`, and the setting in `.env.example`, the
compose files and `Dockerfile.prod`. For Brain, also replace `sourcesTab()` in
`App.tsx` with `'brain'`: it decides which tab Add sources and draft progress
mark, and it reads the Brain flag.

The flags only hide pages; they are not access control. The API is unchanged.

**Tests** run with every flag on (`src/setupTests.ts`), so the existing tests keep
covering the pages. `src/features.test.tsx` turns them off to check the hiding.
