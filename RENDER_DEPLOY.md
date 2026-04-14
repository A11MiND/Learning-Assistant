# Deploy on Render

This repo now includes a Render Blueprint file: `render.yaml`.

## 1) Push to GitHub

Render deploys from a Git repo. Commit and push your latest code first.

## 2) Create the Render service

1. Open Render Dashboard.
2. Click **New** -> **Blueprint**.
3. Select this repository.
4. Render will detect `render.yaml` and create a Python Web Service.

## 3) Important settings

The blueprint sets:

- Start command:
  - `streamlit run app.py --server.address 0.0.0.0 --server.port $PORT --server.headless true`
- Python version:
  - `3.11.4`
- Persistent data paths:
  - `DATA_DIR=/var/data/data`
  - `DATABASE_URL=sqlite:////var/data/dse_ai.db`

It also defines a disk:

- mount path: `/var/data`
- size: `5GB`

## 4) Environment variables you should fill

In Render -> Service -> Environment:

- `DEFAULT_OLLAMA_URL` (optional)
  - Example: `https://your-ollama-gateway.example.com/v1`
- `DEFAULT_API_URL` (optional, for AnythingLLM/OpenAI-compatible endpoint)
  - Example: `https://your-anythingllm.example.com/api/v1`
- `FERNET_KEY` (recommended in production)
  - Generate once and keep it stable. If it changes, encrypted API keys may become unreadable.

## 5) About persistence and plans

- Free plans may sleep and may not support persistent disk in all regions/plans.
- For stable always-on behavior, use a paid plan (for example Starter+) and keep the disk attached.

## 6) First login after deploy

Default seeded accounts (if database starts fresh):

- admin: `admin123` / `admin123`
- teacher: `teacher` / `teacher`
- student: `student01` / `student01`

Change these credentials immediately in production.

## 7) Existing local data migration (optional)

If you want old local data to appear on Render:

1. Upload your local `data/` content to the Render disk path (`/var/data/data`).
2. Upload your local `dse_ai.db` to `/var/data/dse_ai.db`.
3. Restart the Render service.

## Notes

- This project can run on Render as a single Streamlit app.
- If you still depend on local-only backends (localhost Ollama/AnythingLLM), host those backends on reachable endpoints and set the env vars above.
