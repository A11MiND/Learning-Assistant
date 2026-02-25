# DSE AI Tutor (Streamlit + AnythingLLM + Ollama)

This platform now supports teacher-managed language models. Teachers can add multiple model endpoints, supply system prompts, and control which students have access to which models. Students see a simple chat UI and a notebook for tracking mistakes.


A comprehensive, multi-user AI tutoring platform that empowers students to design, build, and publish their own personalized AI tutors. This system integrates **Streamlit**, **Ollama**, and **AnythingLLM** to provide a robust environment for AI education.

## ✨ Features

- **🔐 Role-Based Access**:
  - **Teacher Dashboard**: Manage student accounts, monitor running apps, and handle system cleanup.
  - **Student Workspace**: A dedicated environment for students to configure and launch their AI apps.

- **App Designer**:
  - Students can customize their AI's personality (System Prompt).
  - Configure backend connections (Ollama for Vision, AnythingLLM for RAG/Chat).

- **One-Click Publishing**:
  - The platform acts as an "App Store". Students can click "Publish" to spawn their AI tutor as a **standalone web application** on a unique port (e.g., `8502`, `8503`).
  - Uses `subprocess` and `psutil` for robust process management.

- **🧠 Multi-Modal Capabilities**:
  - **Text Chat**: Powered by AnythingLLM (RAG support).
  - **Vision**: Powered by Ollama (e.g., Qwen-VL) for analyzing uploaded images.
  - **Smart Notebook**: Automatically summarizes mistakes and key concepts using AI when saving Q&A pairs.

## 📋 Prerequisites

Before running the platform, ensure you have the following installed and running:

### 1. Python Environment
- Python 3.9 or higher.

### 2. Ollama (Local LLM & Vision)
Required for local model inference and image analysis.
1. Download from [ollama.com](https://ollama.com).
2. Pull a vision-capable model (default configuration uses `qwen3-vl:8b`):
   ```bash
   ollama pull qwen3-vl:8b
   ```
3. Ensure Ollama is running (usually on `http://localhost:11434`).

### 3. AnythingLLM (RAG & Chat Backend)
Required for the chat interface and vector database management.
1. Install via Docker (MacOS/Linux):
   ```bash
   export STORAGE_LOCATION="$HOME/anythingllm"
   mkdir -p "$STORAGE_LOCATION"
   touch "$STORAGE_LOCATION/.env"
   
   docker run -d -p 3001:3001 \
   --cap-add SYS_ADMIN \
   --name anythingllm \
   --restart always \
   -v "$STORAGE_LOCATION:/app/server/storage" \
   -v "$STORAGE_LOCATION/.env:/app/server/.env" \
   -e STORAGE_DIR="/app/server/storage" \
   -e SERVER_WORKERS=5 \
   mintplexlabs/anythingllm
   ```
   *(For Windows instructions, see `USER_MANUAL.md`)*
2. **Initial Setup**:
   - Access `http://localhost:3001`.
   - Complete the onboarding.
   - **Create a Workspace** (e.g., named `default`).
   - **Generate an API Key** (Settings -> Developer API).
   - You will need the **API Key** and **Workspace Slug** to configure the student apps.

## Installation & Setup

1. **Clone the Repository**
   ```bash
   git clone https://github.com/A11MiND/DSE_AI_Learner.git
   cd DSE_AI_Learner
   ```

2. **Start the Platform**
   We provide a helper script to automatically set up the virtual environment, install dependencies, and launch the app.
   ```bash
   chmod +x start_app.sh
   ./start_app.sh
   ```

   **Manual Startup:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   streamlit run app.py
   ```

3. **Access the App**
   - Main Portal: `http://localhost:8501`
   - Default Teacher Credentials:
     - Username: `teacher`
     - Password: `admin`

## 📂 Project Structure

- **`app.py`**: The main entry point. Handles user authentication, the teacher dashboard, and the student "App Store" interface.
- **`runner.py`**: The template for the student's standalone app. When a student "publishes" their app, `app.py` spawns a new instance of `runner.py` on a free port.
- **`database.py`**: Manages the SQLite database (`dse_ai.db`) for users, deployments (PID/Port tracking), and persistence.
- **`requirements.txt`**: Python dependencies (`streamlit`, `requests`, `psutil`, etc.).
- **`start_app.sh`**: Startup automation script.

## 🤝 Contributing

1. Fork the repository.
2. Create your feature branch (`git checkout -b feature/AmazingFeature`).
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

## 🔗 Links
- GitHub: [https://github.com/A11MiND](https://github.com/A11MiND)
# Learning-Assistant
