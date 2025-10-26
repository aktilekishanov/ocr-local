I'll quickly scan your project root to see what's already there so I can tailor the recommended structure and avoid collisions. Then I'll propose a clean, best-practice layout for a Streamlit app plus FastAPI API, OCR pipeline, MinIO, Postgres logs, and local Textract + ChatGPT integration. After that, I’ll add a concise TODO plan to get you there.

# Proposed Best-Practice Project Structure

Below is a pragmatic, production-friendly layout for your OCR pipeline with:
- Streamlit UI for uploads and metadata entry
- FastAPI REST endpoint to run the pipeline
- MinIO for file storage
- Postgres for logs/metadata
- Local Textract and ChatGPT integrations

```text
ocr/
├─ apps/
│  ├─ streamlit_app/
│  │  ├─ app.py
│  │  ├─ pages/
│  │  └─ components/
│  └─ api/
│     ├─ main.py                  # FastAPI entrypoint
│     ├─ routers/
│     │  ├─ health.py
│     │  ├─ uploads.py            # receive raw files, store to MinIO
│     │  └─ pipeline.py           # run OCR pipeline, return result
│     ├─ dependencies.py
│     └─ middleware.py
├─ ocr_pipeline/
│  ├─ __init__.py
│  ├─ pipeline.py                 # orchestrates end-to-end flow
│  ├─ steps/
│  │  ├─ preprocess.py
│  │  ├─ textract_runner.py       # local Textract call
│  │  ├─ postprocess.py
│  │  └─ summarize.py             # ChatGPT/local LLM
│  ├─ filters.py                  # move from filter_textract_response.py
│  └─ schemas.py                  # pydantic models shared by API + UI
├─ services/
│  ├─ storage/
│  │  ├─ minio_client.py          # put/get signed URLs, bucket mgmt
│  │  └─ paths.py                 # naming conventions per user/reason/doc type
│  ├─ db/
│  │  ├─ models.py                # SQLAlchemy models for logs/metadata
│  │  ├─ session.py               # engine/session creation
│  │  └─ crud.py                  # inserts/selects for logs and runs
│  ├─ textract_client.py          # move from root
│  └─ llm_client.py               # move from gpt_client.py
├─ config/
│  ├─ settings.py                 # Pydantic BaseSettings
│  ├─ logging.py                  # struct logging config
│  └─ constants.py
├─ tests/
│  ├─ test_pipeline.py
│  ├─ test_api.py
│  └─ test_storage.py
├─ scripts/
│  ├─ seed_buckets.py
│  ├─ create_tables.py
│  └─ backfill.py
├─ data/                          # local sample inputs (dev only)
├─ output/                        # local sample outputs (dev only)
├─ .env.example                   # template of required envs
├─ pyproject.toml or requirements.txt
├─ docker-compose.yml             # api, streamlit, minio(+console), postgres
├─ Dockerfile.api
├─ Dockerfile.streamlit
└─ README.md
```

## How components map to your current files

- [filter_textract_response.py](cci:7://file:///Users/aktilekishanov/Documents/career/forte/ds/ocr/filter_textract_response.py:0:0-0:0) → `ocr_pipeline/filters.py`
- [gpt_client.py](cci:7://file:///Users/aktilekishanov/Documents/career/forte/ds/ocr/gpt_client.py:0:0-0:0) → `services/llm_client.py`
- [textract_client.py](cci:7://file:///Users/aktilekishanov/Documents/career/forte/ds/ocr/textract_client.py:0:0-0:0) → `services/textract_client.py`
- [main.py](cci:7://file:///Users/aktilekishanov/Documents/career/forte/ds/ocr/main.py:0:0-0:0) is likely doing orchestration; split:
  - Core logic into `ocr_pipeline/pipeline.py`
  - API entry into `apps/api/main.py`
  - Streamlit entry into `apps/streamlit_app/app.py`

## Key design notes

- **Separation of concerns**
  - **UI** in `apps/streamlit_app/` calls API (never raw pipeline) for consistent access control and logging.
  - **API** in `apps/api/` orchestrates the pipeline and persists logs.
  - **Pipeline** in `ocr_pipeline/` is framework-agnostic, callable from API or CLI.
  - **Integrations** in `services/` for MinIO, Postgres, Textract, LLM.

- **MinIO storage layout**
  - Use a deterministic path scheme in `services/storage/paths.py`:
    - `/{env}/{doc_type}/{reason}/{user_id}/{yyyy}/{mm}/{dd}/{uuid}/{original_filename}`
  - Expose helpers like `put_raw()`, `put_intermediate()`, `get_signed_url()`.

- **Postgres logging**
  - Tables: `ingestions`, `pipeline_runs`, `documents`, `events`
  - Log at each step with status, durations, artifact URIs, and errors.
  - Use SQLAlchemy models in `services/db/models.py`.

- **Configs and secrets**
  - Centralize via `config/settings.py` with Pydantic `BaseSettings`.
  - Example envs in `.env.example`:
    - `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`
    - `DATABASE_URL=postgresql+psycopg://...`
    - `OPENAI_API_KEY` or local LLM socket/URL
    - `TEXTRACT_BIN_PATH` or service host
    - `APP_ENV`, `LOG_LEVEL`

- **API surface (FastAPI)**
  - `POST /uploads/` → accepts file+metadata, stores in MinIO, returns object key
  - `POST /pipeline/run` → body: object key, doc_type, reason, user; returns structured result
  - `GET /runs/{id}` → returns status/result
  - `GET /health` → readiness/liveness

- **Streamlit**
  - `app.py`:
    - Inputs: name, reason, doc type, file upload
    - On submit:
      - Call `POST /uploads/` then `POST /pipeline/run`
      - Poll `GET /runs/{id}` if async
      - Display structured results and links to MinIO artifacts
  - Keep UI state minimal; treat API as source of truth.

- **Async and long-running**
  - If the pipeline can be long: add a worker later (e.g., RQ/Celery) and make `/pipeline/run` enqueue a job. For now, a sync call is fine if typical processing is short.

- **Testing**
  - Unit tests for `ocr_pipeline/steps/*` with local fixtures.
  - Integration tests that spin up test MinIO and Postgres (docker-compose) and run minimal flows.

- **Observability**
  - `config/logging.py` provides JSON logs, correlation IDs per run.
  - Store run IDs and trace IDs in DB for debugging.

## Suggested docker-compose services

- **api**: builds `Dockerfile.api`, exposes `:8000`
- **streamlit**: builds `Dockerfile.streamlit`, exposes `:8501`
- **minio**: MinIO server + optional console
- **postgres**: with healthcheck; mount volume
- Optional: **pgadmin** for quick DB browsing

## Minimal settings contracts

- `ocr_pipeline/schemas.py`
  - `UploadMetadata(name: str, reason: Literal[...] , doc_type: Literal[...])`
  - `RunRequest(object_key: str, metadata: UploadMetadata)`
  - `RunResult(text: str, structured: dict, artifacts: dict, duration_ms: int)`

- `apps/api/routers/pipeline.py`
  - Calls `ocr_pipeline/pipeline.run(request)`, persists `pipeline_runs`.

## Migration steps for you

- **Move files** into the proposed folders as mapped above.
- **Extract orchestration** from [main.py](cci:7://file:///Users/aktilekishanov/Documents/career/forte/ds/ocr/main.py:0:0-0:0) into `ocr_pipeline/pipeline.py`.
- **Create FastAPI** entry `apps/api/main.py` with the routers indicated.
- **Create Streamlit** `apps/streamlit_app/app.py` to call API.
- **Add `config/settings.py`** and replace hardcoded values with envs.
- **Add DB models** for runs/logs and a `scripts/create_tables.py`.

If you want, I can generate skeletons for `settings.py`, `api/main.py`, `streamlit_app/app.py`, and the `pipeline.run()` signature without touching your current code, or prepare a staged patch to reorganize files.

# Recommended Actions

- **[choose-structure]** Confirm you want this structure and whether to include docker-compose now.
- **[skeletons]** Have me create minimal skeleton files for API, Streamlit, settings, and pipeline.
- **[migrate]** I’ll produce a safe patch moving your existing files into the new structure and wiring imports.
- **[infra]** Add `.env.example`, `requirements.txt/pyproject.toml`, and `docker-compose.yml`.

Summary: Proposed a clean modular layout for Streamlit UI, FastAPI API, MinIO storage, Postgres logging, and local Textract/ChatGPT integrations, and mapped your current files into it with concrete next steps.