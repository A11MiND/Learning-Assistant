# DSE AI Learner

A multi-role AI learning platform built with Streamlit.

The project is now a unified teaching system (not a per-student app launcher):

- Admin manages users, classes, model hub, invitation codes, and system settings.
- Teachers manage classes, knowledge base, model access, and class analytics.
- Students learn in one workspace with chat, notebook, mind map, flashcards, and quiz tools.

## What This Project Is (Current)

- Single Streamlit web app entrypoint: `app.py`
- Role-based experience: `admin` / `teacher` / `student`
- OpenAI-compatible model endpoints (Ollama, local gateways, cloud APIs, etc.)
- Document indexing and retrieval for RAG-assisted learning
- Student study workflow in one interface:

  - Chat (supports image upload)
  - Practice question generation
  - Notebook (capture key Q&A)
  - Mind Map generation
  - Flashcards generation and review
  - Quiz generation and auto grading

## Main Capabilities

### Admin

- User management (create/edit/suspend)
- Class and teacher-student relationship management
- Central Model Hub (publish models to teachers)
- Teacher/admin invitation code generation
- System settings and branding assets

### Teacher

- Class analytics dashboard (message volume, token estimate, word trends)
- Class roster and class-level model access
- Knowledge Base management:

  - Foldered documents
  - File upload (PDF/DOCX/TXT)
  - Indexing and retrieval context

- Model management:

  - Platform models from admin
  - Teacher-owned models
  - Student-level and class-level prompt overrides

### Student

- Model selection from teacher-assigned access
- Chat with optional image input
- Personal notebook from chat history
- Practice question generation from notebook
- Study-doc upload and indexing
- Mind map, flashcards, and quiz generation from indexed content

## Tech Stack

- Python 3.11+
- Streamlit
- SQLite (default)
- OpenAI Python SDK (for OpenAI-compatible APIs)
- Optional visualization: streamlit-echarts

## Quick Start (Local)

1. Clone repo

```bash
git clone https://github.com/A11MiND/DSE_AI_Learner.git
cd DSE_AI_Learner
```

1. Start with helper script

```bash
chmod +x start_app.sh
./start_app.sh
```

1. Open browser

- [http://localhost:8501](http://localhost:8501)

1. Default seeded accounts (fresh database)

- admin: username `admin123`, password `admin123`
- teacher: username `teacher`, password `teacher`
- student: username `student01`, password `student01`

Change these credentials immediately for production use.

## Manual Run

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Configuration

Important environment variables:

- `DATA_DIR`: filesystem path for app data (default `data`)
- `DATABASE_URL`: sqlite URL or file path (default `dse_ai.db`)
- `DEFAULT_OLLAMA_URL`: default model API URL shown in UI
- `DEFAULT_API_URL`: default generic API URL shown in UI
- `FERNET_KEY`: optional key for API key encryption consistency

## Deploy to Render

This repo includes Render blueprint config in `render.yaml`.

Deployment guide:

- See `RENDER_DEPLOY.md`

## Project Structure

- `app.py`: main app router and all role dashboards
- `database.py`: schema, migrations, auth, model/class/document/chat data access
- `rag_utils.py`: indexing and context retrieval helpers
- `runner.py`: legacy standalone runner (kept for compatibility)
- `render.yaml`: Render blueprint
- `RENDER_DEPLOY.md`: Render deployment guide
- `USER_MANUAL.md`: longer operation manual

## Notes

- The previous "one-click publish to unique ports" workflow is no longer the core product path.
- The current architecture is a unified multi-role learning platform in a single Streamlit app.

## Contributing

1. Fork the repository.
2. Create a feature branch.
3. Commit your changes.
4. Push the branch.
5. Open a Pull Request.
