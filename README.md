# OPERON

**A Human-Supervised AI Operating System for Small Service Businesses**

Concordia University | SOEN 490 Capstone Project | 2026–2027

**Project Sponsor:** FA Systems Technologies Inc.

Operon is an internal web application that helps a small agency onboard clients. A staff member uploads a de-identified sales-call transcript and the client's intake answers. An AI agent drafts a client profile, links each field to the text it came from, and flags missing or conflicting information. A signed-in reviewer then edits, approves, or rejects the draft.

Nothing the agent writes becomes an approved profile without a named human reviewer approving it.

---

## Contents

- [What Release 1 does](#what-release-1-does)
- [Quick start with Docker](#quick-start-with-docker)
- [Run without Docker](#run-without-docker)
- [The AI model](#the-ai-model)
- [Using the app](#using-the-app)
- [Tests and linting](#tests-and-linting)
- [Configuration](#configuration)
- [Repository layout](#repository-layout)
- [Known limitations](#known-limitations)
- [Project overview](#project-overview)
- [Contributing](#contributing)
- [Wiki](#wiki)
- [Equity and diversity](#equity-and-diversity)

---

## What Release 1 does

Release 1 is one complete onboarding workflow, from upload to approval.

| Step | What happens |
|---|---|
| 1. Sign in | Accounts are invite-only. The first admin is created from the command line. An admin then creates one-time invite links. The roles are `admin`, `reviewer` and `viewer`. |
| 2. Add sources | A user picks a client and uploads two files: a call transcript and the intake answers (`.txt`, `.md`, or `.pdf`, up to 20 MB each). |
| 3. Draft | The Onboarding agent reads both files and writes a draft client profile. Every field cites a quote from the source text, and each quote is checked against that text in code. A citation that is not in the source is rejected. |
| 4. Flags | Fields the evidence does not support stay empty and are flagged as missing. Fields where the sources disagree are flagged as conflicts. The agent does not guess. |
| 5. Review | A reviewer opens the draft from the review inbox, corrects fields, and then approves it or rejects it with a reason. |
| 6. Versions | Nothing is overwritten. Each edit, approval and rejection is stored as a new version of the profile. |

**Not built yet.** The Brain and Workforce menu tabs are placeholders and are hidden by default. The Launch Preparation, Communication and Early Performance agents are planned for later releases. Audit-event recording is in progress (not on `main` yet).

---

## Quick start with Docker

This starts the database, API and frontend with one command. It is the recommended way to run Operon.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine with the Compose plugin), running.
- [Ollama](https://ollama.com/download) installed on your machine (not in Docker). See [The AI model](#the-ai-model).
- Free ports `5432`, `8000` and `5173`.

### 1. Clone and configure

```bash
git clone https://github.com/FA-Systems-Operon/Operon.git
cd Operon
cp .env.example .env
```

Open `.env` and replace `POSTGRES_PASSWORD=change-me` with a password of your choice. Compose will not start without it. The other defaults work as they are.

### 2. Pull the model

```bash
ollama pull qwen2.5:14b
```

This is a download of about 9 GB. You can skip it to look around the app; drafts will fail until a model is available (see [The AI model](#the-ai-model)).

### 3. Start everything

```bash
docker compose up --build
```

The first build takes a few minutes. When it finishes:

| Service | URL |
|---|---|
| Web app | http://localhost:5173 |
| API | http://localhost:8000 |
| API docs (try requests here) | http://localhost:8000/api/v1/docs |

Check that it is healthy:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### 4. Create the first admin

Sign-up is invite-only, so the first admin is created from the command line. In a second terminal, from the repository root:

```bash
docker compose exec api python -m src.create_admin you@example.com "Your Name"
```

It prompts for a password. Passwords must be at least 12 characters. Use a made-up email address; do not use a real person's.

### 5. Create a client

The web app lists clients but cannot create them yet, so create one through the API. Open http://localhost:8000/api/v1/docs, expand `POST /api/v1/clients`, click **Try it out**, and send `{"name": "Demo Client"}`. Or:

```bash
curl -X POST http://localhost:8000/api/v1/clients \
  -H 'Content-Type: application/json' \
  -d '{"name": "Demo Client"}'
```

### 6. Sign in

Open http://localhost:5173 and sign in with the admin account. An admin can do everything in this guide, including reviewing, so you do not need a second account.

To add another user, open the **Invite** tab, enter an email address, and copy the one-time link. They open it to set a password. The invite page creates `viewer` accounts, and a viewer cannot edit, approve or reject drafts. There is no screen for changing a role yet.

Then follow [Using the app](#using-the-app).

### Stop and reset

```bash
docker compose down        # stop; keeps your data
docker compose down -v     # stop and delete the database and uploaded files
```

The database schema is created when the API starts and is not migrated. After a change to the models, or to start clean, use `down -v`.

---

## Run without Docker

Use this if you want to run the API or frontend directly on your machine. You need PostgreSQL 17, Python 3.13 and Node.js 20.19 or newer (Docker uses Node 24).

### Database

Create a PostgreSQL database named `operon` and a user that owns it. Alternatively, start only the compose database with `docker compose up -d db`, which publishes Postgres on `localhost:5432`.

### Backend

The backend does not read `.env` by itself. Export the variables it needs, then start it from `backend/`:

```bash
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
pip install --require-hashes --only-binary=:all: -r requirements.lock

export DATABASE_URL="postgresql+psycopg://operon:YOUR_PASSWORD@localhost:5432/operon"
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_MODEL="qwen2.5:14b"
export STORAGE_DIR="storage"

fastapi dev src/main.py        # serves on http://localhost:8000
```

Create the first admin in another terminal with the same variables exported and the virtualenv active:

```bash
cd backend
python -m src.create_admin you@example.com "Your Name"
```

### Frontend

```bash
cd frontend
npm ci
npm run dev                    # serves on http://localhost:5173
```

The frontend proxies `/api` to `http://localhost:8000`. To point it elsewhere, set `API_URL` before `npm run dev`.

Create a client as in [step 5](#5-create-a-client) above.

---

## The AI model

Operon calls a local model through [Ollama](https://ollama.com). The team model is **`qwen2.5:14b`** (about 9 GB), set in `.env.example`. It was the most accurate of the models we tested. Smaller models missed real conflicts or failed most drafts. The comparison is in [backend/README.md](backend/README.md#model-choice-155).

- **Memory:** the model needs about 9 GB of free memory on top of Docker. Close other apps first.
- **Speed:** with a GPU the default 120-second timeout is enough. On a CPU-only laptop one draft took 3 to 9.5 minutes, and one model reply can take up to 15 minutes. If drafts time out, set `OLLAMA_TIMEOUT_SECONDS=1800` and `JOB_TIMEOUT_SECONDS=3600` in `.env`.
- **Where Ollama runs:** on your host, not in Compose. The API container reaches it at `host.docker.internal:11434`. On Linux, make Ollama listen on all interfaces (`OLLAMA_HOST=0.0.0.0`) so the container can reach it.
- **Check it:** open http://localhost:5173/#/status. It shows whether the API, database and Ollama are reachable and whether the configured model is installed.
- **Try a smaller model:** to just see the flow quickly, set `OLLAMA_MODEL` in `.env` to a model you already have (`ollama list`) and run `docker compose up -d api`. Draft quality will be poor.

Every model call goes through one adapter (`backend/src/ai/provider.py`), so the vendor can be swapped without touching the rest of the code. Ollama is the only provider implemented. Emails and phone numbers are masked before text is sent to the model.

---

## Using the app

1. **Sign in** at http://localhost:5173. Sessions last 8 hours.
2. **Add sources.** On **Command**, choose **New intake**. Pick the client, then choose the transcript file and the intake file. Both upload, and the draft starts automatically.
3. **Watch the draft.** The progress page follows the job (`pending`, `running`, `succeeded` or `failed`). Temporary failures, such as a model timeout, are retried automatically.
4. **Review.** Open **Reviews**. Drafts that are waiting for a decision are listed there. Open one to see each field, its source quote, and the missing and conflict flags.
5. **Edit and decide.** Correct fields and save. Saving creates a new draft version. Then **Approve** (creates a new approved version) or **Reject** (a reason is required; the draft never becomes approved). Only a `reviewer` or `admin` can edit, approve or reject.

Use only synthetic or de-identified files. A ready-made synthetic pair to try is `tests/fixtures/baseline/transcript_1.txt` (transcript) and `tests/fixtures/baseline/intake_1.txt` (intake answers).

Interactive API documentation is at http://localhost:8000/api/v1/docs.

---

## Tests and linting

Model calls are always mocked in tests. No test needs Ollama or a paid API.

### Backend

The tests need PostgreSQL. They use a separate `operon_test` database and never touch your development data. From the repository root, with the compose database running:

```bash
docker compose up -d db
docker compose exec db createdb -U operon operon_test    # first time only
pip install --require-hashes --only-binary=:all: -r backend/requirements-dev.lock
export TEST_DATABASE_URL="postgresql://operon:YOUR_PASSWORD@localhost:5432/operon_test"
pytest
```

Use the `POSTGRES_PASSWORD` from your `.env`. If it is `change-me`, you can skip the `export`, because that is the default.

Create `operon_test` before the first run. On a fresh machine, running `pytest` without it makes the first run report dozens of errors in `tests/test_auth.py` and elsewhere. A second run passes because the first one creates the database.

`TEST_DATABASE_URL` must point to a database whose name ends in `_test`. If you use your own PostgreSQL instead of the compose one and see timestamp failures, run it with its time zone set to UTC.

### Frontend

Run these on your machine, from `frontend/`:

```bash
npm ci
npm test
```

Do not run them inside the Docker container. Some tests read fixtures from the repository's top-level `tests/` folder, which the container does not include, so three test files fail there.

### Lint

CI runs Ruff on all Python code:

```bash
pip install ruff==0.16.9
ruff check .
ruff format --check .
```

CI also runs SonarQube and Codecov. See [.github/workflows/README.md](.github/workflows/README.md).

---

## Configuration

All settings are environment variables. Copy `.env.example` to `.env` for Docker. The ones you are most likely to change:

| Variable | Default | Purpose |
|---|---|---|
| `POSTGRES_PASSWORD` | none, required | Database password. |
| `OLLAMA_MODEL` | `qwen2.5:14b` | Model used for drafts. Required. |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Where Ollama is reachable. |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | How long to wait for one model reply. |
| `JOB_TIMEOUT_SECONDS` | `600` | How long a draft job may run before it counts as abandoned. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`. Logs never contain document text. |
| `MAX_UPLOAD_BYTES` | `20971520` | Largest accepted upload (20 MB). |
| `FEATURE_BRAIN`, `FEATURE_WORKFORCE` | `false` | Show the unfinished Brain and Workforce tabs. See [frontend/README.md](frontend/README.md). |

Never commit `.env` or any secret. Only `.env.example` is committed.

---

## Repository layout

| Path | Contents | More detail |
|---|---|---|
| `backend/` | FastAPI service: auth, documents, onboarding jobs, versioned profiles, review actions, model adapter | [backend/README.md](backend/README.md) |
| `frontend/` | React, TypeScript and Vite web app (the Command Center) | [frontend/README.md](frontend/README.md) |
| `tests/` | Backend test suite and shared synthetic test data | [tests/README.md](tests/README.md) |
| `docs/evaluation/` | Model comparison and Brain-context evaluation results | |
| `docs/plans/` | Implementation plans for specific issues | |
| `scripts/` | Evaluation scripts | |
| `agents/` | Design notes for the Workforce agents | [agents/README.md](agents/README.md) |
| `brain/` | Design notes for the Brain | [brain/README.md](brain/README.md) |
| `dashboard/` | Design notes for the Command Center | [dashboard/README.md](dashboard/README.md) |
| `.github/workflows/` | CI: build and tests, lint, burndown charts | [.github/workflows/README.md](.github/workflows/README.md) |
| `compose.yaml` | Local development stack (database, API, frontend) | |
| `compose.prod.yaml`, `Caddyfile` | Production sketch. Hosting is not decided. | |

The `backend/migrations/` folder holds hand-applied SQL scripts for upgrading an existing development database. A fresh database does not need them. See [backend/README.md](backend/README.md#database-schema-no-migrations-yet).

---

## Known limitations

Release 1 is built to run on one machine for demonstration and evaluation. Do not expose it to a network or use real client data.

- Some API routes, such as creating clients and uploading documents, do not require sign-in yet. Editing, approving and rejecting drafts, and inviting users, do.
- Only emails and phone numbers are masked before text reaches the model. Names and other details are not, which is why only de-identified data may be used.
- The web app cannot create clients yet. Use the API as in step 5.
- Several pages are placeholders (Brain, Workforce) and are hidden unless a feature flag is on.
- There is no email delivery. Invite links are copied from the app and sent manually.

---

## Project overview

### The problem

Small service businesses often keep their operations spread across disconnected tools, documents, conversations and individual employees' knowledge. For FA Systems, onboarding a client means gathering information, understanding business requirements, preparing marketing and operational materials, and coordinating communication. As the number of clients grows, this becomes repetitive, fragmented and inconsistent.

### Three components

**Brain: shared business context.** A versioned store of source documents, extracted context and client profiles. Nothing is overwritten. A new version points to the one it supersedes.

**Workforce: task-scoped agents.** Each agent does one defined job and returns a draft for human review.

| Agent | Responsibility | Planned release |
|---|---|---|
| Onboarding Agent | Extracts client requirements, prepares client profiles, and flags missing or conflicting information. | Release 1 |
| Launch Preparation Agent | Prepares campaign briefs and qualification instructions from approved client information. | Release 2 |
| Communication Agent | Drafts client updates, information requests and approval requests. | Release 2 |
| Early Performance Agent | Analyzes available operational data and identifies issues for human investigation. | Final Release (conditional) |

**Command Center: human supervision.** The web app: sign-in, role-based access, the review inbox, and version history.

### The central experiment

Release 1 tests whether giving the agent context from the Brain improves the draft. Drafts are scored against hand-written reference answers, with and without Brain context. A negative result is a valid, documented finding. Evaluation data and scores are in `docs/evaluation/`.

### Design principles

- **Human supervision:** agent output stays a draft until a named reviewer approves it.
- **Traceability:** drafts link to the source text they came from.
- **Empty, never guessed:** unsupported fields are left empty and flagged.
- **Provider independence:** model calls go through one adapter.
- **Privacy:** only synthetic or de-identified data is used.
- **Measurable value:** the team evaluates accuracy, not the number of agents built.

### Roadmap

| Release | Date | Main objectives | Demo |
|---|---|---|---|
| Release 1 | November 17, 2026 | Platform foundation, versioned context store, Onboarding agent, access control, human approval. | Link to be added |
| Release 2 | January 29, 2027 | Launch preparation and client communication workflows. | Not yet released |
| Final Release | April 13, 2027 | Reliability, evaluation, deployment and handover. Early performance analysis if reliable data is available. | Not yet released |

---

## Contributing

Work is tracked in GitHub Issues and Pull Requests.

1. Pick an issue and read its acceptance criteria.
2. Create a branch and make the change with its tests.
3. Reference the issue in every commit message, for example `Working on #123: what changed`.
4. Open a pull request linked to the issue. It needs at least one approval, and CI must pass. No direct pushes to `main`.
5. Disclose AI use in every commit, pull request and issue, as the course requires.

Use synthetic or de-identified data only. Never commit real personal information, API keys, passwords or `.env` files.

---

## Wiki

The [Operon GitHub Wiki](https://github.com/FA-Systems-Operon/Operon/wiki) holds the project's technical documentation, planning records and course deliverables.

| # | Page |
|---|---|
| 01 | Meeting Minutes |
| 02 | Risks |
| 03 | User Consent and End-User License Agreement |
| 04 | Legal and Ethical Issues |
| 05 | Economic |
| 06 | Budget |
| 07 | Personas |
| 08 | Mockups |
| 09 | Diversity Statement |
| 10 | Overall Architecture and Class Diagrams |
| 11 | Infrastructure and Tools |
| 12 | Naming Conventions |
| 13 | Testing Plan and Continuous Integration |
| 14 | Security |
| 15 | Performance |
| 16 | Deployment Plan and Infrastructure |
| 17 | Missing Knowledge and Independent Learning |
| 18 | Iterations |

---

## Equity and diversity

The Operon team is committed to developing software that respects diversity, promotes accessibility and supports inclusive collaboration.

Because Operon uses AI, its recommendations may be inaccurate or biased. Human review, visible source evidence and controlled access keep automated output accountable. The team aims to build an interface usable by people with different levels of technical expertise, and to evaluate it on varied business scenarios.
