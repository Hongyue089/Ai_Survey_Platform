import csv
import io
import json

from sqlalchemy import func, select

from .models import PreviewResponse, PreviewSession, SurveySnapshot
from .service import access, fail


def snapshots(db, sid):
    access(db, sid, write=True)
    rows = db.execute(
        select(SurveySnapshot.snapshot_id, SurveySnapshot.created_at,
               func.count(PreviewResponse.preview_response_id), func.max(PreviewResponse.submitted_at))
        .join(PreviewSession, PreviewSession.snapshot_id == SurveySnapshot.snapshot_id)
        .outerjoin(PreviewResponse, PreviewResponse.preview_session_id == PreviewSession.preview_session_id)
        .where(SurveySnapshot.survey_id == sid)
        .group_by(SurveySnapshot.snapshot_id, SurveySnapshot.created_at)
        .order_by(func.max(PreviewResponse.submitted_at).desc().nulls_last(),
                  func.max(PreviewSession.created_at).desc(), SurveySnapshot.snapshot_id)
    ).all()
    return [
        {"snapshot_id": identifier, "created_at": created, "response_count": count}
        for identifier, created, count, _ in rows
    ]


def response_query(db, sid, snapshot_id):
    access(db, sid, write=True)
    snapshot = db.get(SurveySnapshot, snapshot_id)
    if not snapshot or snapshot.survey_id != sid:
        fail("Preview Snapshot not found", 404)
    columns = [
        {"question_id": question["question_id"], "name": question["question_name"]}
        for block in snapshot.snapshot_json["blocks"] for question in block["questions"]
        if question["question_type"] != "text_graphic"
    ]
    query = select(PreviewResponse).where(
        PreviewResponse.survey_id == sid, PreviewResponse.snapshot_id == snapshot_id
    ).order_by(PreviewResponse.submitted_at.desc(), PreviewResponse.preview_response_id)
    return columns, query


def page(db, sid, snapshot_id, page_number):
    columns, query = response_query(db, sid, snapshot_id)
    count = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    rows = db.scalars(query.limit(50).offset((page_number - 1) * 50))
    return {"columns": columns, "total": count, "page_size": 50, "items": [
        {"response_id": row.preview_response_id, "submitted_at": row.submitted_at,
         "answers": row.response_json["answers"], "content": row.response_json["content"]}
        for row in rows
    ]}


def csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str) and (value.startswith(("\t", "\r", "\n"))
                                   or value.lstrip().startswith(("=", "+", "-", "@"))):
        return "'" + value
    return value


def csv_export(db, sid, snapshot_id):
    columns, query = response_query(db, sid, snapshot_id)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["response_id", "submitted_at", *[csv_cell(c["name"]) for c in columns], "content"])
    for row in db.scalars(query):
        values = row.response_json
        writer.writerow([row.preview_response_id, row.submitted_at.isoformat(),
                         *[csv_cell(values["answers"].get(c["question_id"])) for c in columns],
                         csv_cell(values["content"])])
    return out.getvalue()
