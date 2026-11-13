# API / Data Contract

Every editor write uses `expected_version`; mismatches return 409. The server checks the development user's `t_survey_members` membership and edit role. View-only members can read Working Version and History. Preview, Publish, and changes require edit access. This is a development identity, not a production authentication scheme.

`GET /api/projects` accepts `search_keyword`, `sort_option`, `page`, `page_size`. Allowed sort tokens: last_modified, date_created, name_az, name_za, responses. Permissions → literal contains search → ordering → pagination. Responses all tie at zero while formal Response is deferred.

`POST /api/projects` creates Survey + owner member + empty Block 1 + empty Working Flow in one transaction. `GET/PUT /api/surveys/{sid}/working` reads/writes the Working Version, including relational Block/Question/AI data and JSON Flow/Options. Autosave and Apply both persist the Working Version. Removed Blocks and Questions must remain soft-deleted. Omitting them from a normal save is rejected.

Question configs are type-specific Pydantic schemas. Choices/scales have stable choice_id and numeric value. Matrix statements have stable statement_id. Multiple answers are numeric arrays. Matrix answers are `{statement_id: numeric_value_or_array}`. Placeholder labels are empty strings, not fake data.

Flow JSON has schema_version=1, elements, trash. Each element has element_id, type, sort_order, optional block_id/ai_config_id, config, children. Randomizer uses children. Branch uses `config.condition_groups[]` with group_id, connector, conditions, children. Condition has source_type (question/variable), source_id, operator (equals/not_equals), typed value, connector (AND/OR). Connectors fold left-to-right; the first connector is ignored. A true combined Branch predicate runs the matching groups' paths in order. Groups are not mutually exclusive. Trash records keep the entire subtree, parent/group IDs and insertion position. Restore falls back to Root if the old parent/group is gone.

Draft nodes may be incomplete. An empty or invalid active Flow blocks Preview and Publish. Existing dependency checks protect active and trashed Flow references during edits. Runtime additionally validates prior data availability.

`GET /api/surveys/{sid}/revisions?module=survey|flow` lists revisions. Restore creates a new Working Version. New Survey revisions capture the whole Working Version. Flow History includes the old Flow rows for compatibility and combines them with unified revisions and publication records. The latest 20 ordinary autosaves are retained. Revision sequences do not reuse pruned numbers.

`GET/PUT /api/surveys/{sid}/ai-configs/{id}` / list APIs expose configuration data only. The list GET path is `/api/surveys/{sid}/ai-configs`; the item PUT takes `{expected_version, config}` and creates/updates a configuration atomically with Working Version. No API Key is returned or stored in Survey configuration.

`POST /api/surveys/{sid}/preview-sessions` freezes Working Version and creates t_preview_session. GET session, POST next/back/chat and DELETE session all re-check member ownership. next accepts current Block's answers only. Chat opening takes empty message, subsequent turns take a participant message. AI prompts are resolved server-side; endpoint response exposes the agent name, turn limit, messages and error but not system/context templates.

Preview startup and Publish both pin an Applied Revision and reuse the same immutable Snapshot if execution content matches. The frontend calls `POST /api/surveys/{sid}/execution-preparation` before local validation and launch. The server checks the expected Working version again at launch. `POST /api/surveys/{sid}/publish` takes `{expected_version}` and records the release, even if the Snapshot is reused.

`POST /api/preview-sessions/{id}/submit` archives the current valid answers and AI transcript once per session. `GET /api/surveys/{sid}/preview-data/snapshots` lists Preview Snapshots. Under `/preview-data/{snapshot_id}`, GET returns paginated results and GET `/csv` downloads them. Both read archived JSON. Active sessions use temporary runtime state for branch evaluation. Changing an earlier answer invalidates later results and reruns the remaining path. Session exit or expiry cleans temporary content while retaining submitted responses.

`POST /api/projects/import` takes `{import_request_id, project_name, file_name, content}`. The content is the text of the uploaded file. See [example-project.json](example-project.json) for the minimal shape. An idempotency key belongs to the requesting user and a single file/name combination. Unknown or malformed references cause the entire import to fail. New imports generate database IDs for Blocks, Questions, Flow Nodes, Groups, and AI Configs.

JSON schema details are available in FastAPI's generated `/docs` and `docs/openapi.json`.
