# AI Survey Platform V2

> To upgrade from the October 3, 2026 release, configure the connection to your existing database and run `python -m app.upgrade` from `backend`. Keep your existing `.env` file and database.

## Implemented features

- The Project List supports search, sorting, pagination, project creation, and JSON import. Each new import assigns fresh element IDs and rewrites internal references. Retrying the same request after a network failure returns the project already created by that request.
- Builder supports four question types, Question Groups, soft deletion, and Trash. Flow supports Block, Branch with multiple paths, Block Randomizer, Participant Randomizer, Python Code, AI Conversation Agent for text interviews, and End of Survey.
- Working Version supports Apply, Autosave, and version conflict detection. New Flow history entries store full Survey Revisions. Older Flow history entries can still be viewed and restored.
- Preview uses a fixed Revision and Snapshot. If there is no valid Flow, Preview prompts you to return to the editor. Click **Submit** after completing the survey to save test responses. You can view them in **Preview Data** and download a CSV.
- Publish pins the current Snapshot and records it in the publishing history. The participant entry point, public survey links, and the production response lifecycle are planned for their respective modules.

AI uses the existing server-side configuration. Preview data is stored separately from production survey statistics. This release uses the local development identity `dev_admin` and is intended for local use.

## Start the platform on Windows with PowerShell

Extract the ZIP into a new directory. Keep the original repository's `.git` directory, PRDs, and existing project documentation. If you later move the new code into the original repository, replace the application directories supplied in the ZIP and retain the Git history and existing documentation.

Open the extracted project root:

```powershell
cd F:\Git\ai-survey-platform-v2
```

You need Python 3.11+, Node.js 20+, and Docker Desktop / WSL or a running PostgreSQL instance.

If you are reusing a Docker development database, the default volume is `ai-survey-platform_survey_db`, the name typically created by the previous `ai-survey-platform` project. Check the actual volume name:

```powershell
docker volume ls
```

If the old volume has a different name, set it in the current terminal before starting the database. Avoid running `docker compose down -v`, which can delete database volumes.

```powershell
$env:SURVEY_DB_VOLUME = "your-existing-volume-name"
docker compose up -d db
```

If your existing PostgreSQL container is already running on port 5432, use that instance. If the selected volume contains no existing data, this starts a fresh development database and leaves other volumes intact.

Set up the backend environment:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` in place of `python` in the commands below. Set `DATABASE_URL` in `.env` to the development database you intend to upgrade. Keep passwords out of Git. The default connection uses the local `survey` database on port 5432.

### Prepare the database

If you have an existing database from the October 3 release, run this from `backend`:

```powershell
python -m app.upgrade
```

You can rerun the upgrade command. It preserves existing surveys, history, and Preview Sessions. For a fresh, empty database, use:

```powershell
python -m app.initialize
```

Start the backend:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Start the frontend in a second PowerShell terminal:

```powershell
cd F:\Git\ai-survey-platform-v2\frontend
npm ci
npm run dev
```

Open the [survey editor](http://localhost:5173). The backend also provides [API documentation](http://127.0.0.1:8000/docs) and a [health check](http://127.0.0.1:8000/health).

## Try JSON import and Preview

1. From the home page, open **Import a Project** and upload the [example JSON](docs/example-project.json). You can edit **Project Name** before importing.
2. Click **Go to Preview**, answer the questions, and click **Submit**.
3. Return to Builder, open **Preview Data**, select a Snapshot, and download the CSV.
4. Use **Publish** in Builder or Flow to save the current published version. You can see the entry in **History**.

The import JSON uses `blocks` and `flow`, with optional `survey_config` and `ai_configs` fields. Block, Question, Flow Node, Group, and AI Config identifiers use UUID v4. Flow accepts both `node_id` and the existing `element_id` field. The importer uses the Project Name entered in the dialog. It accepts one JSON file of up to 2 MiB. See the [API Contract](docs/API-CONTRACT.md) for field details.

## Python Code in Flow

In Preview, Python Code computes values using a restricted subset of Python. Read an answer with `response["question_id"]` or `{#question_id#}`, then use the `result` dictionary to pass variables to later nodes. Replace `question_id` in the following example with the actual question ID.

```python
score = int({#question_id#}) + 2
result = {"score": score}
```

In a later Branch, select **Embedded Data / Python Result** and enter `score` as the variable name. The supported syntax includes assignments, conditionals, basic operators, dictionaries, and common type conversion functions. Preview displays execution errors and line numbers when available. The runtime excludes file and network access, third-party modules, and arbitrary Python calls.

## Optional AI configuration

Set `OPENAI_API_KEY` and `AI_MODEL` in `backend/.env`, then restart the backend. The API key stays on the server and is excluded from the survey, frontend, and AI Config table. Each **AI Conversation Agent** node has its own configuration and Agent Name. **Input Source** lists questions available earlier in the flow. **Context** supports placeholders such as `{#Q1#}` and `{#variable_name#}`. Set the model explicitly in `AI_MODEL`.

Changes to AI settings are saved atomically to the separate `t_ai_config` table alongside the Working Version. The API also exposes separate GET and PUT endpoints for AI Config. The server increments `config_version`, and each Preview uses the Snapshot captured at launch. Verify model compatibility, quota, and network access with your own key and model.

## Run checks

```powershell
cd backend
python -m pytest -q
cd ..\frontend
npm run typecheck
npm run build
```

Application behavior tests use isolated SQLite databases. The platform uses PostgreSQL as its application database. See the [validation notes](docs/VALIDATION.md) for PostgreSQL SQL, foreign key, and reset checks. Run `tests/pg_verify.py` only against a fresh, disposable PostgreSQL database because it runs destructive integration checks.

## Project layout

```text
backend/app/        SQLAlchemy, Pydantic, services, API, and the Preview engine
backend/tests/      Application behavior and database checks
database/           schema.sql, seed.sql, and future migrations
frontend/src/       Vue, TypeScript, and Element Plus
frontend/dist/      Built frontend assets
docs/               PRDs, prototypes, decisions, validation notes, and screenshots
```

Builder and Flow autosave after 600 seconds of inactivity. Options autosaves after 10 seconds. **Apply** saves immediately. Preview opens in a new tab. Refreshing resumes the current temporary Session. Restarting Preview clears its state and assigns random conditions again. Sessions expire after two hours by default. Expired data is cleaned up the next time Preview starts.
