"""Allowlisted, dependency-aware PostgreSQL development reset. No CASCADE."""

import argparse, json
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.schema import CreateTable, CreateIndex, AddConstraint
from sqlalchemy.dialects import postgresql
from .models import Base, User
from .config import settings
from .db import SessionLocal

KNOWN = set(Base.metadata.tables)
FINGERPRINT = {
    "t_user": {"user_id", "created_at", "updated_at"},
    "t_survey": {"survey_id", "survey_name", "creator_id", "survey_config"},
    "t_block": {"block_id", "survey_id", "block_name", "sort_order"},
    "t_question": {"question_id", "block_id", "question_type", "config"},
    "t_survey_members": {"survey_id", "user_id", "role"},
    "t_survey_flow": {"flow_id", "survey_id", "flow_json"},
    "t_survey_revision": {"revision_id", "survey_id", "revision_number"},
    "t_survey_flow_revision": {"revision_id", "flow_id", "survey_id"},
    "t_ai_config": {"ai_config_id", "config_name", "config_version", "model"},
    "t_ai_run": {"run_id", "ai_config_id", "model"},
    "t_ai_conversation": {"conversation_id", "survey_id", "ai_config_id"},
    "t_ai_message": {"message_id", "conversation_id", "role"},
    "t_preview_session": {"preview_session_id", "survey_id", "snapshot_json"},
    "t_survey_snapshot": {"snapshot_id", "source_revision_id", "content_hash"},
    "t_survey_publication": {"publication_id", "revision_id", "snapshot_id"},
    "t_survey_change_log": {"log_id", "action_type", "survey_id"},
    "t_project_import": {"import_request_id", "user_id", "content_hash"},
    "t_preview_response": {"preview_response_id", "preview_session_id", "response_json"},
}


def inspect_project(conn):
    ins = inspect(conn)
    present = set(ins.get_table_names(schema="public")) & KNOWN
    details = []
    for table in sorted(present):
        cols = {c["name"] for c in ins.get_columns(table, schema="public")}
        if not FINGERPRINT[table] <= cols:
            raise RuntimeError(
                f"{table} does not match project fingerprint; reset refused"
            )
        count = conn.scalar(text(f'SELECT COUNT(*) FROM public."{table}"'))
        details.append(
            {
                "table": table,
                "rows": count,
                "foreign_keys": ins.get_foreign_keys(table, schema="public"),
            }
        )
    for schema in ins.get_schema_names():
        if schema in ("pg_catalog", "information_schema") or schema.startswith("pg_"):
            continue
        for table in ins.get_table_names(schema=schema):
            for fk in ins.get_foreign_keys(table, schema=schema):
                if (
                    fk["referred_table"] in present
                    and (fk.get("referred_schema") or schema) == "public"
                    and (schema != "public" or table not in present)
                ):
                    raise RuntimeError(
                        f'External dependency {schema}.{table} -> {fk["referred_table"]}; reset refused'
                    )
    # Views/materialized views would be indirectly removed by CASCADE; refuse them explicitly.
    deps = conn.execute(
        text("""SELECT DISTINCT ns.nspname, cl.relname, target.relname
      FROM pg_depend d JOIN pg_rewrite rw ON rw.oid=d.objid
      JOIN pg_class cl ON cl.oid=rw.ev_class JOIN pg_namespace ns ON ns.oid=cl.relnamespace
      JOIN pg_class target ON target.oid=d.refobjid JOIN pg_namespace tn ON tn.oid=target.relnamespace
      WHERE tn.nspname='public' AND cl.oid<>target.oid AND cl.relkind IN ('v','m')""")
    ).all()
    for schema, view, target in deps:
        if target in present:
            raise RuntimeError(
                f"View dependency {schema}.{view} -> {target}; reset refused"
            )
    return present, details


def reset_tables(conn, present):
    ins = inspect(conn)
    graph = {t: set() for t in present}
    for t in present:
        for fk in ins.get_foreign_keys(t, schema="public"):
            if fk["referred_table"] in present:
                graph[t].add(fk["referred_table"])
    order = []
    remaining = set(present)
    while remaining:
        leaves = sorted(
            t
            for t in remaining
            if not any(t in graph[other] for other in remaining if other != t)
        )
        if not leaves:
            # Break only verified project-to-project FKs, safely inside this transaction.
            for t in sorted(remaining):
                for fk in ins.get_foreign_keys(t, schema="public"):
                    if fk["referred_table"] in remaining:
                        quoted = conn.dialect.identifier_preparer.quote(fk["name"])
                        conn.execute(
                            text(f'ALTER TABLE public."{t}" DROP CONSTRAINT {quoted}')
                        )
                        graph[t].discard(fk["referred_table"])
            continue
        for t in leaves:
            conn.execute(text(f'DROP TABLE public."{t}"'))
            order.append(t)
            remaining.remove(t)
    return order


def export_schema(path):
    dialect = postgresql.dialect()
    statements = [
        "-- Generated from authoritative SQLAlchemy models. DO NOT edit independently.",
        "BEGIN;",
    ]
    for t in Base.metadata.sorted_tables:
        statements.append(str(CreateTable(t).compile(dialect=dialect)).strip() + ";")
    for t in Base.metadata.sorted_tables:
        for index in t.indexes:
            statements.append(str(CreateIndex(index).compile(dialect=dialect)) + ";")
        for constraint in t.foreign_key_constraints:
            if constraint.use_alter:
                statements.append(
                    str(AddConstraint(constraint).compile(dialect=dialect)) + ";"
                )
    statements.append("COMMIT;")
    sql = "\n\n".join(statements)
    Path(path).write_text("\n".join(line.rstrip() for line in sql.splitlines()) + "\n", encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inspect", action="store_true")
    p.add_argument("--reset", action="store_true")
    p.add_argument("--development-database", action="store_true")
    p.add_argument("--export-schema")
    args = p.parse_args()
    if args.export_schema:
        export_schema(args.export_schema)
        return
    engine = create_engine(settings.database_url)
    if engine.dialect.name != "postgresql":
        raise RuntimeError(
            "Initialization/reset requires PostgreSQL; SQLite is test-only"
        )
    with engine.begin() as conn:
        present, details = inspect_project(conn)
        print(json.dumps(details, default=str, indent=2))
        if args.inspect:
            return
        if args.reset:
            if not args.development_database:
                raise RuntimeError(
                    "Pass --development-database only after confirming this database contains disposable project test data"
                )
            print("Drop order:", reset_tables(conn, present))
        elif present:
            # Idempotent initialization only for a complete matching V2 schema.
            ins = inspect(conn)
            for name, t in Base.metadata.tables.items():
                cols = (
                    {c["name"] for c in ins.get_columns(name, schema="public")}
                    if name in present
                    else set()
                )
                if cols != set(t.columns.keys()):
                    raise RuntimeError(
                        "Old/incomplete schema detected. Inspect and use explicit development reset."
                    )
        Base.metadata.create_all(conn)
        conn.execute(
            text(
                "INSERT INTO t_user(user_id,created_at,updated_at) VALUES (:id,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) ON CONFLICT(user_id) DO NOTHING"
            ),
            {"id": settings.dev_user_id},
        )
    print("Schema ready; development user seeded.")


if __name__ == "__main__":
    main()
