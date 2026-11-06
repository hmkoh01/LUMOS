# Railway beta deployment guardrails

This is a deployment preparation guide only.  It does not enable Engine v2,
the scheduler, collectors, or Agent Platform calls.

## Runtime

- Pin Python 3.12.9 via the tracked `.python-version`; set Railway's
  `RAILPACK_PYTHON_VERSION=3.12.9` as a matching deployment variable.
- `railway.toml` uses Railpack and starts FastAPI with Railway's `PORT`:
  `python -m uvicorn src.app.main:app --host 0.0.0.0 --port $PORT`.
- Railway health check: `GET /health`, expecting `{"status":"ok"}`.
- Run one web instance for the 10–15 person beta.  Do not start a second
  in-process worker in the web process.  The queue's atomic SQLite claim and
  job dedupe protect a single worker, but operationally there must be one
  designated worker process when workers are introduced.

## Persistent volume and flags

Mount one Railway volume at `/data` and configure only paths, never secrets:

- `LUMOS_DB_PATH=/data/lumos.sqlite`
- `LUMOS_DATA_DIR=/data` (prevents default `./data` files on ephemeral disk)
- `LUMOS_ENGINE_CACHE_DB_PATH=/data/engine_briefings.sqlite`
- queue path (when enabled) under `/data`, e.g. `/data/engine_queue.sqlite`;
  configure it in the future worker process, not the normal web process.
- keep `LUMOS_ENGINE_V2=false`, `LUMOS_SCHEDULER_ENABLED=false`,
  `LUMOS_EXTERNAL_CALLS=false`, and `LUMOS_BLOCK_EXTERNAL_CALLS=true` for the
  normal beta web service.

Agent Platform credentials and the narrow Engine approval belong only in a
separate staging/worker process.  Do not put them in logs, shell history, or
version control.

## Backup, restart, and monitoring

Before deploy or schema work, stop the designated worker and use SQLite's
online backup command (`sqlite3 /data/lumos.sqlite ".backup /data/backups/lumos-<date>.sqlite"`).
Copy both the application and Engine cache databases to durable backup storage;
restore while the service is stopped, then run the offline health checks.

Use `python tools/engine_monitor.py --cache-db /data/engine_briefings.sqlite --queue-db /data/engine_queue.sqlite`
for aggregate queue/cache/token/cost health.  It intentionally excludes API
keys, prompts, source text, user IDs, and provider error bodies.  Alert on
failed jobs, increasing wait time, validation failures, card shortfall, or
unexpected request/cost growth.  An incident response is to disable the
separate worker approval first; the web service remains read-only for LLMs.

## Scheduler and cost safety

Scheduler ownership is a single explicitly configured process; it remains off
for this beta.  No restart may create a second scheduler or worker.  Start
with `GENERATE_BRIEFING` jobs at `max_retries=0`; inspect failed aggregates
before manually creating a new job.  Keep Agent Platform concurrency at one,
disable grounding/tools, and retain the 3,000 KRW experiment cap until a
separate cost review approves a production budget.

## Beta handoff gate

Verified offline: Python 3.12 compatibility, isolated SQLite storage, queue
deduplication/`max_retries=0`, cache metrics, validated-card persistence,
and Engine-v1 rollback by leaving `LUMOS_ENGINE_V2=false`.

Not yet verified and therefore not deploy-ready: Railway volume attachment,
backup restore on Railway, production collector credentials and execution,
scheduled collection, and a live multi-process worker deployment.  Keep all
of these disabled until a staging checklist confirms them.  Before inviting
10–15 test users, create only test accounts, confirm the monitor command
works against the staging volume, set budget alerts, and rehearse disabling
the worker approval/Engine v2 flag as the rollback action.
