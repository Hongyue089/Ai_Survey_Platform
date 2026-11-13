# Validation — V2 rebuild

## Completed

- Backend: 10 pytest tests passed. Covers new Survey defaults, required answers, linear Preview, Branch/Variable/End, random balancing, Back without reroll, cross-Survey reference rejection, stale Working Version rejection, revision restore, malformed configs, future AI input rejection, AI Opening Message / Turn accounting, AI configuration restore, literal search/pagination, read-only operations preserving modification time, Matrix selection and required rows.
- Frontend: `vue-tsc --noEmit` passed; `vite build` passed with a bundle-size advisory only.
- API startup: Uvicorn started successfully in the disposable UI test environment; `/health` and browser API calls passed.
- Browser: new project → empty Block → add Multiple Choice → inline text/choice editing → Apply → independent Preview tab → select answer → end; Flow Block configuration → Apply; Options edit → Apply; History dialog; Flow soft delete → Trash Restore. No browser page errors.
- Matrix: actual browser DOM verified 3 statement rows × 5 scale columns = 15 cells, with horizontal grid structure. Screenshot reviewed.
- Project counts: after adding two answerable Questions, API returns question_count=2 and response_count=0. Preview submissions did not change formal counts.
- PostgreSQL: generated schema.sql executed in a PostgreSQL 17 WASM engine (PGlite); all 13 tables and real JSONB/foreign keys created. Repeated seed retained exactly one dev_admin; invalid creator FK rejected.
- PostgreSQL wire integration: FastAPI + SQLAlchemy connected via psycopg to a disposable PGlite PostgreSQL wire-protocol endpoint. Project creation/list/Preview and JSONB mapping passed.
- Reset integration: unknown external FK dependency was rejected; unrelated table retained; project-only dependency drop order and repeated transactional reset/create/seed passed. Internal Survey↔AI Config cycle was handled by dropping only known internal FK constraints before tables. No CASCADE used.

## Limits

The user's local PostgreSQL instance was never accessible and was not modified. All destructive verification used a newly created disposable test engine, not the user's database. Run the README's inspect/reset commands locally against the confirmed project test database to perform the actual old-table reset.

Native PostgreSQL 16 installation could not run in this execution environment's single-UID mapping; PostgreSQL semantics were checked using PostgreSQL 17 WASM plus a wire endpoint, rather than a native PostgreSQL 16 daemon. Validate the supplied initialization command on the local PostgreSQL 16 environment.

AI API requests were tested using an explicit provider test double, not a live model/key. The application itself does not use fake AI replies. Configure OPENAI_API_KEY and AI_MODEL to validate live compatibility, provider quota and network.

Screenshot environment lacks Japanese/CJK fonts; Japanese labels can appear as squares in captured Preview/Options screenshots, while the actual strings and localized browser interactions are correct. The app uses ordinary system fonts, including the Japanese fonts provided on Windows; no font assets were added to the product.

Formal Response, Published Snapshot, Publish execution, Distribution, Data & Analysis, Report and production authentication were deliberately deferred per user instruction. Security/availability settings that need these modules are configuration only. Temporary Preview records have a two-hour TTL and are cleaned at next Preview creation.

## Reproducibility

Use backend/requirements-validated.txt for the exact primary dependencies used here; normal backend/requirements.txt has compatible version ranges. Frontend/package-lock.json records the resolved dependencies. SQLite appears only in test fixtures and temporary UI verification; PostgreSQL remains the product database.

The final Browser check was read-only on the existing disposable UI database; it did not reset or reinitialize that database after the user requested continuation.


2026-10-03 修正版本验证和升级记录见 UPDATE-20261003.md；本次共 21 项 Backend 测试通过。
