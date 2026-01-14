# DSE AI Learner Platform - User Manual

## INSTALLATION AND SETUP

### PREREQUISITES
Before installing the DSE AI Learner platform, ensure you have the following software installed on your system:
*   **Operating System:** macOS, Linux, or Windows (via WSL2)
*   **Python:** Version 3.8 or higher
*   **Git:** To clone the repository
*   **Docker Desktop:** (Optional) For running AnythingLLM
*   **Ollama:** (Optional) For running local AI models

### INSTALLATION STEPS

#### OLLAMA INSTALLATION
Ollama is used to run open-source Large Language Models (LLMs) locally on your machine.
1.  Visit the official download page: [https://ollama.com/download](https://ollama.com/download)
2.  Download the installer for your operating system.
3.  Run the installer and follow the on-screen instructions.
4.  Once installed, open a terminal and pull a model (e.g., qwen):
    ```bash
    ollama pull qwen
    ```

#### DOCKER INSTALLATION
Docker is required if you plan to use containerized services like AnythingLLM.
1.  Visit [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/)
2.  Download and install Docker Desktop.
3.  Start Docker Desktop and ensure it is running in the background.

#### ANYTHING LLM INSTALLATION
AnythingLLM provides a powerful backend for document embedding and RAG (Retrieval-Augmented Generation).
1.  Open your terminal.
2.  Run the following command to pull and start the AnythingLLM docker container:
    ```bash
    docker run -d -p 3001:3001 --cap-add SYS_ADMIN --name anythingllm mintplexlabs/anythingllm
    ```
3.  Access the interface at `http://localhost:3001` to complete the setup.

#### PLATFORM INSTALLATION (GITHUB)
1.  Open your terminal.
2.  Clone the DSE AI Learner repository:
    ```bash
    git clone https://github.com/A11MiND/DSE_AI_Learner.git
    cd DSE_AI_Learner
    ```
3.  Make the startup script executable:
    ```bash
    chmod +x start_app.sh
    ```

---

## GETTING STARTED

### RUN THE PLATFORM
To start the main application platform:

1.  Navigate to the project directory in your terminal.
2.  Run the startup script:
    ```bash
    ./start_app.sh
    ```
3.  The application will automatically set up the virtual environment, install dependencies, and launch in your default web browser at:
    **http://localhost:8501**

---

## STUDENT INTERFACE

The student interface focuses on creating and managing personalized AI learning assistants.

### FUNCTION 1: APP DESIGNER
*   **Purpose:** Customize the behavior and knowledge base of the AI Tutor.
*   **Settings:**
    *   **App Title:** Name your AI application (e.g., "Math Tutor").
    *   **System Prompt:** Define the AI's persona and rules. This is crucial for guiding how the AI responds (e.g., "You are a friendly English teacher").
    *   **AI Backend:** Configure the connection to **Ollama** (Local) or **AnythingLLM** (RAG).

### FUNCTION 2: PUBLISH & RUN
*   **Purpose:** Deploy the configured AI Tutor as a standalone web application.
*   **Features:**
    *   **One-Click Launch:** Instantly start a dedicated server process for your specific bot.
    *   **Unique Port:** Each student app runs on a unique local port (e.g., 8502, 8503).
    *   **Status Indicators:** specific status showing if the app is Running or Stopped.

### FUNCTION 3: PROFILE MANAGEMENT
*   **Purpose:** Manage user credentials.
*   **Features:**
    *   Update Display Name.
    *   Change Password.

---

## ADMIN / TEACHER INTERFACE

The teacher interface provides oversight and management capabilities for the entire class.

### FUNCTION 1: STUDENT OVERSIGHT (DASHBOARD)
*   **Purpose:** View a comprehensive list of all student accounts.
*   **Data Points:**
    *   Student ID and Name.
    *   Current Deployment Status (Running/Stopped).
    *   Port Number of deployed apps.

### FUNCTION 2: DIRECT ACCESS
*   **Purpose:** Review student work.
*   **Features:**
    *   **Open App:** Teachers can click a direct link to open and test any student's running AI Tutor application.

### FUNCTION 3: USER MANAGEMENT
*   **Purpose:** Maintain system hygiene.
*   **Features:**
    *   **Delete User:** Remove student accounts and their associated data/deployments (using the Trash icon).

---

## USER CASE DEMONSTRATE (CREATE A CYBER SECURITY LEARNER)

This scenario guides you through creating a specialized AI Tutor for learning Cyber Security.

### STEP 1: LOGIN
1.  Navigate to `http://localhost:8501`.
2.  Register a new student account (e.g., `cyber_student`) or login.

### STEP 2: DESIGN THE AI
1.  Click on **"App Designer"** in the sidebar.
2.  **App Title:** Enter `Cyber Security Guardian`.
3.  **System Prompt:** Copy and paste the following:
    > You are an expert Cyber Security Instructor.
    > Your goal is to teach concepts like Phishing, SQL Injection, and Firewalls in simple terms.
    > Always warn about the ethical implications of hacking.
    > Never provide executable exploit code.
4.  **Backend:** Ensure Ollama URL is set to `http://localhost:11434` and Model is `qwen` (or your installed model).
5.  Click **"💾 Save Configuration"**.

### STEP 3: PUBLISH THE APP
1.  Click on **"Publish & Run"** in the sidebar.
2.  Click the **"▶️ Publish & Launch"** button.
3.  Wait for the success message: `App launched on port 8502!`.

### STEP 4: START LEARNING
1.  Click the generated link (e.g., `http://localhost:8502`).
2.  A new tab opens with your "Cyber Security Guardian".
3.  Try asking: *"Explain how a SQL Injection attack works and how to prevent it."*

---

## DEBUG AND ERROR HANDLING

If you encounter issues during installation or usage:

1.  **Check Terminal Output:** Look at the terminal running `./start_app.sh` for python errors.
2.  **Port Conflicts:** If `localhost:8501` is in use, the app may use the next available port (8502, etc).
3.  **Dependency Issues:** Try deleting the `venv` folder and restarting `./start_app.sh` to reinstall dependencies.

**Still having trouble?**

Please capture a screenshot of the error message or terminal output and email it to technical support:

**📧 Email:** admin@edcosys.com
**Subject:** DSE AI Learner Support Request
