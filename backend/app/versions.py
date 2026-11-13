from copy import deepcopy
from hashlib import sha256
import json

from sqlalchemy import select

from .config import settings
from .models import SurveyPublication, SurveyRevision, SurveySnapshot, now
from .schemas import WorkingData
from .service import access, fail, log_action, nodes, save, uid, validate, working


def digest(data):
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def execution_config(data):
    content = {key: deepcopy(data[key]) for key in WorkingData.model_fields}
    content["flow"]["trash"] = []
    content["blocks"] = [block for block in content["blocks"] if not block["is_deleted"]]
    for block in content["blocks"]:
        block["questions"] = [question for question in block["questions"] if not question["is_deleted"]]
    active_agents = {node["ai_config_id"] for node in nodes(content["flow"]["elements"])}
    default_agent = content["survey_config"]["ai"]["config_id"]
    content["ai_configs"] = [
        agent for agent in content["ai_configs"]
        if agent["ai_config_id"] in active_agents or agent["ai_config_id"] == default_agent
    ]
    return content


def ensure_applied(db, sid, expected_version):
    survey = access(db, sid, write=True, lock=True)
    if expected_version is not None and survey.working_version != expected_version:
        fail("Working Version changed. Reload before launching.", 409)
    revision = db.get(SurveyRevision, survey.working_revision_id) if survey.working_revision_id else None
    if not revision or revision.save_type != "apply":
        data = working(db, survey)
        args = {key: data[key] for key in WorkingData.model_fields}
        save(db, sid, dict(args, expected_version=survey.working_version, save_type="apply"))
        # Apply is a separate operation. Reacquire the lock and check for intervening edits.
        expected = data["working_version"]
        survey = access(db, sid, write=True, lock=True)
        if survey.working_version != expected:
            fail("Working Version changed. Reload before launching.", 409)
        revision = db.get(SurveyRevision, survey.working_revision_id)
    return survey, revision


def prepare_execution(db, sid, expected_version):
    survey, revision = ensure_applied(db, sid, expected_version)
    data = WorkingData.model_validate(
        {key: revision.survey_json[key] for key in WorkingData.model_fields}
    ).model_dump(mode="json")
    if not data["flow"]["elements"]:
        fail("No Flow configured. Please configure the Survey Flow before continuing.")
    validate(data, runtime=True)
    content = execution_config(data)
    version = 1
    content_hash = digest({"schema_version": version, "content": content})
    snapshot = db.scalar(select(SurveySnapshot).where(
        SurveySnapshot.survey_id == sid,
        SurveySnapshot.schema_version == version,
        SurveySnapshot.content_hash == content_hash,
    ))
    if snapshot is None:
        snapshot = SurveySnapshot(
            snapshot_id=uid(), survey_id=sid, source_revision_id=revision.revision_id,
            schema_version=version, content_hash=content_hash, snapshot_json=content,
            created_by=settings.dev_user_id,
        )
        db.add(snapshot)
        db.flush()
    return survey, revision, snapshot


def publish(db, sid, expected_version):
    survey, revision, snapshot = prepare_execution(db, sid, expected_version)
    publication = SurveyPublication(
        publication_id=uid(), survey_id=sid, revision_id=revision.revision_id,
        snapshot_id=snapshot.snapshot_id, published_by=settings.dev_user_id, published_at=now(),
    )
    db.add(publication)
    survey.published_snapshot_id = snapshot.snapshot_id
    survey.published_at = publication.published_at
    survey.status = "published"
    log_action(db, sid, "PUBLISH", "publication", publication.publication_id,
               revision_id=revision.revision_id, snapshot_id=snapshot.snapshot_id)
    db.commit()
    return working(db, survey)
