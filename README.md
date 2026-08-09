# DSE AI Learner

![Python](https://img.shields.io/badge/python-3.11-blue)
![Streamlit](https://img.shields.io/badge/framework-Streamlit-FF4B4B)

A multi-role AI learning platform built with Streamlit, providing a single web app for admins, teachers, and students.

- **Admins** manage users, classes, the model hub, invitation codes, and system settings.
- **Teachers** manage classes, a knowledge base, model access, and class analytics.
- **Students** learn in one workspace with chat, a notebook, mind maps, flashcards, and quizzes.

## What this project is

- Single Streamlit entrypoint: `app.py`
- Role-based experience: `admin` / `teacher` / `student`
- OpenAI-compatible model endpoints (Ollama, local gateways, cloud APIs, etc.)
- Document indexing and retrieval for RAG-assisted learning
- Student study workflow in one interface: chat (with image upload), practice question generation, a notebook, mind maps, flashcards, and auto-graded quizzes

## Main capabilities

### Admin
- User management (create/edit/suspend)
- Class and teacher-student relationship management
- Central model hub (publish models to teachers)
- Teacher/admin invitation code generation
- System settings and branding assets

### Teacher
- Class analytics dashboard (message volume, token estimate, word trends)
- Class roster and class-level model access
- Knowledge base management: foldered documents, PDF/DOCX/TXT upload, indexing and retrieval context
- Model management: platform models from admin, teacher-owned models, student-level and class-level prompt overrides

### Student
- Model selection from teacher-assigned access
- Chat with optional image input
- Personal notebook built from chat history
- Practice question generation from the notebook
- Study-doc upload and indexing
- Mind map, flashcard, and quiz generation from indexed content

## Tech stack

- Python 3.11
- Streamlit
- SQLite (default; encrypted API keys via `cryptography`/Fernet)
- OpenAI Python SDK, used against any OpenAI-compatible endpoint
- Optional: `streamlit-echarts` for charts, `streamlit-lottie` for UI animation

## Quick start (local)

```bash
git clone https://github.com/A11MiND/Learning-Assistant.git
cd Learning-Assistant
chmod +x start_app.sh
./start_app.sh
```

Open [http://localhost:8501](http://localhost:8501).

Default seeded accounts on a fresh database:

| Role | Username | Password |
|---|---|---|
| Admin | `admin123` | `admin123` |
| Teacher | `teacher` | `teacher` |
| Student | `student01` | `student01` |

Change these credentials before any non-local use.

## Manual run

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Testing

```bash
pytest tests/
```

## Configuration

Key environment variables:

| Variable | Purpose |
|---|---|
| `DATA_DIR` | Filesystem path for app data (default `data`) |
| `DATABASE_URL` | SQLite URL or file path (default `dse_ai.db`) |
| `DEFAULT_OLLAMA_URL` | Default Ollama endpoint shown in the UI |
| `DEFAULT_API_URL` | Default generic API endpoint shown in the UI |
| `FERNET_KEY` | Optional fixed key for consistent API-key encryption across restarts |

## Deployment

`render.yaml` provides a Render blueprint (persistent disk-backed SQLite, headless Streamlit start command). See [`RENDER_DEPLOY.md`](./RENDER_DEPLOY.md) for the full deployment guide.

A GitHub Actions workflow (`.github/workflows/streamlit-keepalive.yml`) can periodically ping a deployed instance to prevent it from sleeping on free hosting tiers; it is a manually-triggered uptime ping, not a build/test pipeline.

## Project structure

- `app.py` — main app router and all role dashboards
- `database.py` — schema, migrations, auth, and model/class/document/chat data access
- `rag_utils.py` — indexing and context retrieval helpers
- `runner.py` — legacy standalone runner, kept for compatibility
- `render.yaml` — Render blueprint
- `RENDER_DEPLOY.md` — Render deployment guide
- `USER_MANUAL.md` — longer operation manual
- `tests/` — pytest suite

## Notes

- The project previously worked as a "one-click publish to unique ports" app launcher; that is no longer the core product path.
- The current architecture is a unified, multi-role learning platform served from a single Streamlit app.

## Contributing

1. Fork the repository.
2. Create a feature branch.
3. Commit your changes.
4. Push the branch.
5. Open a pull request.
