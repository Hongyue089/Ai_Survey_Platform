import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from typing import Literal
from fastapi import FastAPI, Depends, Query
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from .db import get_db, SessionLocal
from .config import settings
from .models import *
from .schemas import (
    SaveRequest,
    ImportRequest,
    RestoreRequest,
    SubmitAnswers,
    ChatRequest,
    WorkingView,
    ProjectPage,
    WorkingData,
    AIConfigData,
    AIConfigRequest,
)
from . import service, preview, project_import, versions, preview_data


def purge_expired_previews():
    with SessionLocal.begin() as db:
        preview.cleanup_expired(db)


async def preview_cleanup_loop():
    while True:
        await asyncio.sleep(15 * 60)
        try:
            await run_in_threadpool(purge_expired_previews)
        except Exception:
            logging.getLogger(__name__).error("Preview data cleanup failed")


@asynccontextmanager
async def lifespan(app):
    if not settings.development_mode:
        raise RuntimeError(
            "Real authentication is not implemented. This build requires DEVELOPMENT_MODE=true and must run locally."
        )
    cleanup_task = asyncio.create_task(preview_cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


app = FastAPI(title="AI Survey Platform V2", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)
DB = Depends(get_db)


@app.get("/health")
def health(db: Session = DB):
    from sqlalchemy import text

    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/capabilities")
def capabilities():
    return {
        "development_user": settings.dev_user_id,
        "builder": True,
        "flow": True,
        "options": True,
        "preview": True,
        "publish": True,
        "response": False,
        "distribution": False,
        "analysis": False,
        "ai_config": True,
        "ai_ready": bool(settings.openai_api_key and settings.ai_model),
        "default_model": settings.ai_model,
        "autosave_seconds": 600,
        "options_autosave_seconds": 10,
    }


@app.get("/api/projects", response_model=ProjectPage)
def projects(
    search_keyword: str = Query("", max_length=100),
    sort_option: Literal[
        "last_modified", "date_created", "name_az", "name_za", "responses"
    ] = "last_modified",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = DB,
):
    keyword = (
        search_keyword.strip()
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    base = (
        select(Survey)
        .join(SurveyMember, SurveyMember.survey_id == Survey.survey_id)
        .where(SurveyMember.user_id == settings.dev_user_id)
    )
    if keyword:
        base = base.where(Survey.survey_name.ilike("%" + keyword + "%", escape="\\"))
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    ordering = {
        "last_modified": Survey.updated_at.desc(),
        "date_created": Survey.created_at.desc(),
        "name_az": Survey.survey_name.asc(),
        "name_za": Survey.survey_name.desc(),
        "responses": Survey.updated_at.desc(),
    }[sort_option]
    # No formal Response table exists; every response_count is currently 0.
    rows = db.scalars(
        base.order_by(ordering, Survey.survey_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    counts = dict(
        db.execute(
            select(Block.survey_id, func.count(Question.question_id))
            .join(Question, Question.block_id == Block.block_id)
            .where(
                Block.survey_id.in_([s.survey_id for s in rows]),
                Block.is_deleted == False,
                Question.is_deleted == False,
                Question.question_type != "text_graphic",
            )
            .group_by(Block.survey_id)
        ).all()
    )
    return {
        "items": [
            {
                "survey_id": s.survey_id,
                "project_type": s.project_type,
                "survey_name": s.survey_name,
                "status": s.status,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
                "question_count": counts.get(s.survey_id, 0),
                "response_count": 0,
            }
            for s in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@app.post("/api/projects", response_model=WorkingView, status_code=201)
def create(db: Session = DB):
    return service.create_survey(db)


@app.post("/api/projects/import", status_code=201)
def import_project(payload: ImportRequest, db: Session = DB):
    return project_import.import_project(db, payload)


@app.get("/api/surveys/{sid}/working", response_model=WorkingView)
def get_working(sid: str, db: Session = DB):
    return service.working(db, service.access(db, sid))


@app.put("/api/surveys/{sid}/working", response_model=WorkingView)
def put_working(sid: str, payload: SaveRequest, db: Session = DB):
    return service.save(db, sid, payload.model_dump(mode="json"))


@app.get("/api/surveys/{sid}/ai-configs", response_model=list[AIConfigData])
def ai_configs(sid: str, db: Session = DB):
    return service.working(db, service.access(db, sid))["ai_configs"]


@app.get("/api/surveys/{sid}/revisions")
def revisions(sid: str, module: Literal["survey", "flow"] = "survey", db: Session = DB):
    service.access(db, sid)
    current = db.scalars(select(SurveyRevision).where(SurveyRevision.survey_id == sid)).all()
    result = [
        revision_view(r, r.survey_json, "survey") for r in current
    ]
    if module == "flow":
        legacy = db.scalars(select(FlowRevision).where(FlowRevision.survey_id == sid)).all()
        result.extend(revision_view(r, r.flow_json, "legacy_flow") for r in legacy)
    publications = db.execute(
        select(SurveyPublication, SurveyRevision).join(
            SurveyRevision, SurveyPublication.revision_id == SurveyRevision.revision_id
        ).where(SurveyPublication.survey_id == sid)
    ).all()
    for publication, revision in publications:
        item = revision_view(revision, revision.survey_json, "publication")
        item.update(
            revision_id=publication.publication_id, save_type="published",
            created_at=publication.published_at, created_by=publication.published_by,
        )
        result.append(item)
    return sorted(result, key=lambda item: (service.iso(item["created_at"]), item["revision_id"]), reverse=True)


def revision_view(revision, data, source):
    blocks = [b for b in data.get("blocks", []) if not b["is_deleted"]]
    return {
        "revision_id": revision.revision_id,
        "revision_number": revision.revision_number,
        "save_type": revision.save_type,
        "source": source,
        "created_at": revision.created_at,
        "created_by": revision.created_by,
        "block_count": len(blocks),
        "question_count": sum(not q["is_deleted"] for b in blocks for q in b["questions"]),
        "element_count": sum(1 for _ in service.nodes(data.get("elements", data.get("flow", {}).get("elements", [])))),
    }


@app.post("/api/surveys/{sid}/revisions/{rid}/restore", response_model=WorkingView)
def restore(
    sid: str,
    rid: str,
    payload: RestoreRequest,
    module: Literal["survey", "flow"] = "survey",
    db: Session = DB,
):
    s = service.access(db, sid, True, True)
    r = db.get(SurveyRevision, rid)
    publication = db.get(SurveyPublication, rid) if r is None else None
    if publication and publication.survey_id == sid:
        r = db.get(SurveyRevision, publication.revision_id)
    legacy = db.get(FlowRevision, rid) if r is None and module == "flow" else None
    selected = r or legacy
    if not selected or selected.survey_id != sid:
        service.fail("Revision not found", 404)
    data = service.working(db, s)
    if module == "survey":
        data = r.survey_json
    else:
        data["flow"] = r.survey_json["flow"] if r else legacy.flow_json
        configs = r.survey_json["ai_configs"] if r else legacy.ai_configs_json
        historical = {a["ai_config_id"]: a for a in configs}
        data["ai_configs"] = [
            historical.pop(a["ai_config_id"], a) for a in data["ai_configs"]
        ] + list(historical.values())
    args = {k: data[k] for k in WorkingData.model_fields}
    args.update(expected_version=payload.expected_version, save_type="apply")
    return service.save(db, sid, args, save_type="restore", base_revision_id=r.revision_id if r else None)


@app.delete("/api/surveys/{sid}/trash/{kind}/{identifier}", response_model=WorkingView)
def permanent(
    sid: str,
    kind: Literal["block", "question"],
    identifier: str,
    expected_version: int = Query(ge=1),
    db: Session = DB,
):
    s = service.access(db, sid, True, True)
    if s.working_version != expected_version:
        service.fail("Working Version changed; reload before deletion", 409)
    service.fail("Permanent deletion is disabled in V1; use Restore", 409)


@app.post("/api/surveys/{sid}/execution-preparation", response_model=WorkingView)
def prepare_execution(sid: str, expected_version: int | None = Query(None, ge=1), db: Session = DB):
    survey, _ = versions.ensure_applied(db, sid, expected_version)
    return service.working(db, survey)


@app.post("/api/surveys/{sid}/publish", response_model=WorkingView)
def publish(sid: str, payload: RestoreRequest, db: Session = DB):
    return versions.publish(db, sid, payload.expected_version)


@app.post("/api/surveys/{sid}/preview-sessions", status_code=201)
def start_preview(sid: str, expected_version: int | None = Query(None, ge=1), db: Session = DB):
    return preview.new_session(db, sid, expected_version)


@app.get("/api/surveys/{sid}/preview-data/snapshots")
def preview_snapshots(sid: str, db: Session = DB):
    return preview_data.snapshots(db, sid)


@app.get("/api/surveys/{sid}/preview-data/{snapshot_id}/csv")
def export_preview(sid: str, snapshot_id: str, db: Session = DB):
    return Response(
        "﻿" + preview_data.csv_export(db, sid, snapshot_id),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="preview-responses.csv"'},
    )


@app.get("/api/surveys/{sid}/preview-data/{snapshot_id}")
def get_preview_data(sid: str, snapshot_id: str, page: int = Query(1, ge=1), db: Session = DB):
    return preview_data.page(db, sid, snapshot_id, page)


@app.get("/api/preview-sessions/{identifier}")
def get_preview(identifier: str, db: Session = DB):
    return preview.view(db, preview.load_session(db, identifier))


@app.post("/api/preview-sessions/{identifier}/next")
def next_preview(identifier: str, payload: SubmitAnswers, db: Session = DB):
    return preview.next_page(db, identifier, payload.answers, [t.model_dump(mode="json") for t in payload.timings])


@app.post("/api/preview-sessions/{identifier}/back")
def back_preview(identifier: str, db: Session = DB):
    return preview.back_page(db, identifier)


@app.post("/api/preview-sessions/{identifier}/quit-conversation")
def quit_preview_conversation(identifier: str, db: Session = DB):
    return preview.quit_conversation(db, identifier)


@app.post("/api/preview-sessions/{identifier}/chat")
async def chat_preview(identifier: str, payload: ChatRequest, db: Session = DB):
    return await preview.chat(db, identifier, payload.message)


@app.post("/api/preview-sessions/{identifier}/submit")
def submit_preview(identifier: str, db: Session = DB):
    return preview.submit(db, identifier)


@app.delete("/api/preview-sessions/{identifier}", status_code=204)
def end_preview(identifier: str, db: Session = DB):
    preview.end(db, identifier)


@app.put("/api/surveys/{sid}/ai-configs/{config_id}", response_model=WorkingView)
def put_ai_config(sid: str, config_id: str, payload: AIConfigRequest, db: Session = DB):
    if payload.config.ai_config_id != config_id:
        service.fail("AI Config ID does not match URL")
    s = service.access(db, sid, True, True)
    data = service.working(db, s)
    configs = {a["ai_config_id"]: a for a in data["ai_configs"]}
    configs[config_id] = payload.config.model_dump(mode="json")
    args = {k: data[k] for k in WorkingData.model_fields}
    args["ai_configs"] = list(configs.values())
    args.update(expected_version=payload.expected_version, save_type="apply")
    return service.save(db, sid, args)


@app.get("/api/surveys/{sid}/ai-configs/{config_id}", response_model=AIConfigData)
def get_ai_config(sid: str, config_id: str, db: Session = DB):
    data = service.working(db, service.access(db, sid))
    config = next(
        (a for a in data["ai_configs"] if a["ai_config_id"] == config_id), None
    )
    if not config:
        service.fail("AI Configuration not found", 404)
    return config
