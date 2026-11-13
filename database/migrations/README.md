# Database upgrades

For the 2026-10-03 V2 database, run `python -m app.upgrade` from `backend` using the existing `DATABASE_URL`. This applies the question-group adjustment and the database V1 additions in a transaction. It backfills Question ownership and the latest Working Revision pointer, and keeps old Flow History available for reading and restoration.

For an empty PostgreSQL database, run `python -m app.initialize`. The current schema is generated from the SQLAlchemy models in `backend/app/models.py`.
