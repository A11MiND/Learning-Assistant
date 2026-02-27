import streamlit as st
import sys
import requests
import json
import os
from datetime import datetime
import uuid
import glob
import subprocess
import socket
import time
import database
import rag_utils
from openai import OpenAI

# ---- OpenAI-compatible model API helpers ----

def call_model_api(model, messages):
    """
    Multi-turn chat call using the OpenAI client library.
    model: dict with api_url, api_key, model_name, system_prompt, override_prompt (optional)
    messages: list of {"role": ..., "content": ...} (user + assistant turns, no system msg)
    Returns: response string
    """
    client = OpenAI(
        api_key=model.get("api_key") or "not-required",
        base_url=model["api_url"]
    )
    system_parts = []
    if model.get("system_prompt"):
        system_parts.append(model["system_prompt"])
    if model.get("override_prompt"):
        system_parts.append(model["override_prompt"])
    full_messages = []
    if system_parts:
        full_messages.append({"role": "system", "content": "\n\n".join(system_parts)})
    full_messages.extend(messages)
    try:
        resp = client.chat.completions.create(
            model=model.get("model_name") or "gpt-3.5-turbo",
            messages=full_messages,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"[Model Error]: {e}"


def call_model_api_single(model, prompt):
    """Convenience wrapper for a single-turn call (summaries, indexing, etc.)."""
    return call_model_api(model, [{"role": "user", "content": prompt}])

# --- Helper Functions ---

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

SERVER_IP = get_local_ip()

# --- Configuration & Constants ---
DEFAULT_ANYTHINGLLM_URL = f"http://{SERVER_IP}:3001/api/v1"
DEFAULT_OLLAMA_URL = f"http://{SERVER_IP}:11434"
DATA_DIR = "data"

# --- System Settings Helper ---
SYSTEM_SETTINGS_FILE = "data/system/settings.json"

def load_system_settings():
    if os.path.exists(SYSTEM_SETTINGS_FILE):
        try:
            with open(SYSTEM_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_system_settings(settings):
    os.makedirs(os.path.dirname(SYSTEM_SETTINGS_FILE), exist_ok=True)
    with open(SYSTEM_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)

# Initialize DB
database.init_db()
database.cleanup_zombies() # Cleanup on startup

st.set_page_config(page_title="DSE AI Tutor Platform", layout="wide")

# Apply System Customization (CSS) if exists
sys_settings = load_system_settings()
if sys_settings.get("background_url"):
    page_bg_img = f'''
    <style>
    .stApp {{
        background-image: url("{sys_settings.get("background_url")}");
        background-size: cover;
    }}
    </style>
    '''
    st.markdown(page_bg_img, unsafe_allow_html=True)

# --- Helper Functions ---

def get_user_dir(username):
    user_dir = os.path.join(DATA_DIR, username)
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
        os.makedirs(os.path.join(user_dir, "history"), exist_ok=True)
    return user_dir

def load_config(username):
    config_file = os.path.join(get_user_dir(username), "config.json")
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_config(username, config):
    config_file = os.path.join(get_user_dir(username), "config.json")
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

# --- Student workspace helper functions ---

def save_image(username, image_bytes):
    images_dir = os.path.join(get_user_dir(username), "images")
    os.makedirs(images_dir, exist_ok=True)
    filename = f"{uuid.uuid4()}.png"
    file_path = os.path.join(images_dir, filename)
    with open(file_path, "wb") as f:
        f.write(image_bytes)
    return filename

def get_image_path(username, filename):
    return os.path.join(get_user_dir(username), "images", filename)

def get_notebook_path(username):
    return os.path.join(get_user_dir(username), "notebook.json")

def load_notebook(username):
    path = get_notebook_path(username)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_notebook(username, data):
    path = get_notebook_path(username)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_to_notebook(username, question, answer, summary=None):
    notebook = load_notebook(username)
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "title": (summary[:50] if summary else question[:50]),
        "question": question,
        "answer": answer,
        "summary": summary,
    }
    notebook.append(entry)
    save_notebook(username, notebook)

def delete_notebook_entry(username, entry_id):
    notebook = load_notebook(username)
    notebook = [n for n in notebook if n["id"] != entry_id]
    save_notebook(username, notebook)

def save_session(username, session_id, messages):
    if not messages:
        return
    title = "New Chat"
    for msg in messages:
        if msg["role"] == "user":
            title = msg["content"][:30] + ("..." if len(msg["content"]) > 30 else "")
            break
    history_dir = os.path.join(get_user_dir(username), "history")
    os.makedirs(history_dir, exist_ok=True)
    file_path = os.path.join(history_dir, f"{session_id}.json")
    messages_to_save = []
    for msg in messages:
        mc = msg.copy()
        mc.pop("image_data", None)
        messages_to_save.append(mc)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump({"id": session_id, "title": title,
                   "updated_at": datetime.now().isoformat(),
                   "messages": messages_to_save}, f, ensure_ascii=False, indent=2)

def get_free_port():
    """Find a free port starting from 8502."""
    active_ports = database.get_all_active_ports()
    port = 8502
    while True:
        if port not in active_ports:
            # Double check if port is actually free on OS
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            if result != 0: # Port is closed (free)
                return port
        port += 1

def start_student_app(user_id, username):
    """Launch runner.py for a specific user on a new port."""
    # Check if already running
    dep = database.get_deployment(user_id)
    if dep and dep['status'] == 'running':
        # Check if process is actually alive
        try:
            os.kill(dep['pid'], 0)
            return dep['port'] # Still running
        except OSError:
            pass # Process dead, restart

    port = get_free_port()
    
    # Command to run Streamlit
    cmd = [
        sys.executable, "-m", "streamlit", "run", "runner.py",
        "--server.port", str(port),
        "--server.headless", "true",
        "--server.address", "0.0.0.0",
        "--server.fileWatcherType", "none",
        "--", f"user_id={user_id}"
    ]
    
    # Start process
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Update DB
    database.update_deployment(user_id, port, process.pid)
    
    # Wait a bit for it to start
    time.sleep(2)
    return port

def stop_student_app(user_id):
    dep = database.get_deployment(user_id)
    if dep and dep['pid']:
        try:
            os.kill(dep['pid'], 15) # SIGTERM
        except OSError:
            pass
        database.stop_deployment_record(user_id)

# --- UI Components ---

def render_login():
    sys_settings = load_system_settings()
    
    # Custom Branding
    if sys_settings.get("logo_url"):
        st.image(sys_settings.get("logo_url"), width=200)
    
    title = sys_settings.get("school_name", "DSE AI Learner Login")
    st.title(title)
    
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            user = database.verify_user(username, password)
            if user:
                if user.get('account_status') == 'banned':
                    st.error("This account has been suspended.")
                else:
                    st.session_state.user = user
                    st.success(f"Welcome, {user['name']}!")
                    st.rerun()
            else:
                st.error("Invalid credentials")
                
    with tab2:
        new_user = st.text_input("New Username")
        new_pass = st.text_input("New Password", type="password")
        new_name = st.text_input("Full Name")
        if st.button("Register"):
            if database.create_user(new_user, new_pass, "student", new_name):
                st.success("Registration successful! Please login.")
            else:
                st.error("Username already exists.")

def render_profile(user):
    st.header("User Profile")
    
    with st.form("profile_form"):
        new_name = st.text_input("Display Name", value=user['name'])
        new_pass = st.text_input("New Password (leave blank to keep)", type="password")
        
        if st.form_submit_button("Update Profile"):
            success, msg = database.update_user_profile(
                user['id'], 
                new_password=new_pass if new_pass else None,
                new_name=new_name
            )
            if success:
                st.success("Profile updated! Please re-login.")
                st.session_state.user = None
                st.rerun()
            else:
                st.error(msg)

def render_teacher_dashboard():
    st.title("Teacher Dashboard")

    tab_students, tab_models, tab_kb, tab_system = st.tabs(
        ["Student Management", "Model Management", "Knowledge Base", "System Customization"]
    )
    
    with tab_students:
        if st.button("Refresh List"):
            st.rerun()
            
        students = database.get_all_students()
        
        # Table Header
        cols = st.columns([1, 2, 2, 1.5, 1.5, 4])
        cols[0].markdown("**ID**")
        cols[1].markdown("**Name**")
        cols[2].markdown("**Username**")
        cols[3].markdown("**App Status**")
        cols[4].markdown("**Acc Status**")
        cols[5].markdown("**Actions**")
        
        # Pre-fetch all models for access checkboxes
        all_models = database.get_models()
        
        for s in students:
            with st.container():
                cols = st.columns([1, 2, 2, 1.5, 1.5, 4])
                cols[0].write(s['id'])
                cols[1].write(s['name'])
                cols[2].write(s['username'])
                
                # App Status
                dep = database.get_deployment(s['id'])
                app_status = "Stopped"
                app_url = ""
                is_running = False
                if dep and dep['status'] == 'running':
                    try:
                        os.kill(dep['pid'], 0)
                        app_status = f"Running (port {dep['port']})"
                        app_url = f"http://{SERVER_IP}:{dep['port']}"
                        is_running = True
                    except:
                        app_status = "Zombie"
                cols[3].write(app_status)
                
                # Account Status
                acc_status = s.get('account_status', 'active')
                if acc_status == 'banned':
                    cols[4].markdown("BANNED")
                else:
                    cols[4].markdown("Active")
                
                # Actions
                with cols[5]:
                    sub_cols = st.columns([1.2, 1.2, 1.2], gap="small")
                    
                    with sub_cols[0]:
                        if is_running:
                            if st.button("Stop", key=f"stop_{s['id']}"):
                                stop_student_app(s['id'])
                                st.rerun()
                        else:
                            if st.button("Run", key=f"run_{s['id']}"):
                                 start_student_app(s['id'], s['username'])
                                 st.rerun()
                    with sub_cols[1]:
                        if app_url:
                            st.write(f"[Open]({app_url})")
                        else:
                             st.write("-")
                    with sub_cols[2]:
                        if acc_status == 'banned':
                            if st.button("Unban", key=f"unban_{s['id']}"):
                                database.update_user_status(s['id'], 'active')
                                st.rerun()
                        else:
                            if st.button("Ban", key=f"ban_{s['id']}"):
                                database.update_user_status(s['id'], 'banned')
                                stop_student_app(s['id'])
                                st.rerun()
                    
                    with st.expander("Edit / Delete"):
                        with st.form(key=f"edit_form_{s['id']}"):
                            new_name = st.text_input("Name", value=s['name'])
                            new_user = st.text_input("Username", value=s['username'])
                            reset_pw = st.checkbox("Reset Password to 'password'")
                            
                            col_a, col_b = st.columns(2)
                            with col_a:
                                if st.form_submit_button("Save Changes"):
                                    pw = "password" if reset_pw else None
                                    success, msg = database.admin_update_user(s['id'], new_name, new_user, pw)
                                    if success:
                                        st.success("Updated!")
                                        time.sleep(0.5)
                                        st.rerun()
                                    else:
                                        st.error(msg)
                            with col_b:
                                if st.form_submit_button("Delete User", type="primary"):
                                    database.delete_user(s['id'])
                                    st.rerun()
                # Model access section
                with st.expander("Model Access"):
                    # Fetch current access rows so we can show override_prompt too
                    access_map = {}
                    for row in database.get_allowed_models_for_student(s['id']):
                        access_map[row['id']] = row
                    for m in all_models:
                        checked = m['id'] in access_map
                        new_val = st.checkbox(m['name'], value=checked, key=f"access_{s['id']}_{m['id']}")
                        if new_val:
                            override = st.text_area(
                                "Override instruction for this student + model",
                                value=access_map.get(m['id'], {}).get('override_prompt') or "",
                                key=f"override_{s['id']}_{m['id']}",
                                help="Appended to the model's system prompt only for this student."
                            )
                        if new_val != checked:
                            op = override if new_val else None
                            database.set_student_model_access(s['id'], m['id'], 1 if new_val else 0, op)
                            st.rerun()
                        elif new_val:
                            old_op = access_map.get(m['id'], {}).get('override_prompt') or ""
                            if override != old_op:
                                database.set_student_model_access(s['id'], m['id'], 1, override or None)
                                st.rerun()
                st.divider()

    with tab_models:
        st.header("Model Management")
        st.info("Add, edit or remove LLM endpoints. Model ID is the identifier sent in each API request (e.g. gpt-4o, deepseek-chat, Qwen/Qwen2.5-72B-Instruct).")

        models = database.get_models()
        if models:
            for m in models:
                with st.expander(f"{m['name']} — {m.get('model_name','')}"):
                    with st.form(key=f"edit_model_{m['id']}"):
                        name = st.text_input("Display Name", value=m['name'])
                        model_name = st.text_input("Model ID", value=m.get('model_name', ''),
                                                   help="e.g. gpt-4o, deepseek-chat, Qwen/Qwen2.5-72B-Instruct")
                        url = st.text_input("API Base URL", value=m['api_url'],
                                            help="e.g. https://api.openai.com/v1 or https://api.siliconflow.cn/v1")
                        key = st.text_input("API Key", value=m.get('api_key', ''))
                        prompt = st.text_area("System Prompt", value=m.get('system_prompt', ''),
                                             help="Invisible to students. Use this to enforce pedagogical rules, e.g. guide thinking instead of giving direct answers.")
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.form_submit_button("Save Changes"):
                                database.update_model(m['id'], name=name, model_name=model_name,
                                                     api_url=url, api_key=key or None,
                                                     system_prompt=prompt or None)
                                st.success("Updated")
                                st.rerun()
                        with col_b:
                            if st.form_submit_button("Delete Model", type="primary"):
                                database.delete_model(m['id'])
                                st.rerun()
        else:
            st.write("No models defined yet.")

        st.markdown("---")
        st.subheader("Add New Model")
        with st.form("add_model"):
            name = st.text_input("Display Name")
            model_name = st.text_input("Model ID", help="e.g. gpt-4o, deepseek-chat, Qwen/Qwen2.5-72B-Instruct")
            url = st.text_input("API Base URL", help="e.g. https://api.openai.com/v1")
            key = st.text_input("API Key (optional)")
            prompt = st.text_area("System Prompt (optional)",
                                  help="Pedagogical instructions invisible to students.")
            if st.form_submit_button("Create Model"):
                if name and model_name and url:
                    database.create_model(name, model_name, url, api_key=key or None,
                                          system_prompt=prompt or None)
                    st.success("Model created")
                    st.rerun()
                else:
                    st.error("Display Name, Model ID and API Base URL are required")
    
    with tab_kb:
        st.header("Knowledge Base")
        st.info("Upload subject materials. AI can generate practice questions from them and students can use them as reference context in Chat.")

        # Upload section
        with st.expander("Upload New Document", expanded=True):
            with st.form("upload_doc"):
                doc_name = st.text_input("Document Name / Title")
                subject = st.text_input("Subject (optional)", placeholder="e.g. Biology, History")
                uploaded = st.file_uploader("Choose file", type=["pdf", "docx", "txt"])
                if st.form_submit_button("Upload"):
                    if uploaded and doc_name:
                        docs_dir = os.path.join("data", "system", "docs")
                        os.makedirs(docs_dir, exist_ok=True)
                        fname = f"{uuid.uuid4()}_{uploaded.name}"
                        fpath = os.path.join(docs_dir, fname)
                        with open(fpath, "wb") as f:
                            f.write(uploaded.getvalue())
                        ft = uploaded.name.rsplit(".", 1)[-1].lower()
                        database.save_document(doc_name, fpath, ft, subject=subject or None)
                        st.success(f"Uploaded: {doc_name}")
                        st.rerun()
                    else:
                        st.error("Please enter a name and choose a file.")

        # List documents
        docs = database.get_documents()
        if not docs:
            st.write("No documents uploaded yet.")
        else:
            for doc in docs:
                with st.expander(f"{doc['name']}  [{doc['index_status']}]"):
                    st.write(f"File: `{os.path.basename(doc['file_path'])}`  |  Type: {doc['file_type']}  |  Subject: {doc.get('subject') or '-'}")

                    col_idx, col_del = st.columns([2, 1])
                    models_list = database.get_models()

                    with col_idx:
                        if doc['index_status'] != 'indexed':
                            if models_list:
                                idx_model_names = {m['id']: m['name'] for m in models_list}
                                idx_model_id = st.selectbox("Model for indexing", idx_model_names.keys(),
                                                            format_func=lambda i: idx_model_names[i],
                                                            key=f"idx_model_{doc['id']}")
                                if st.button("Build Index", key=f"build_idx_{doc['id']}"):
                                    idx_model = next((m for m in models_list if m['id'] == idx_model_id), None)
                                    with st.spinner("Building page index..."):
                                        index = rag_utils.build_page_index(
                                            doc['file_path'], doc['file_type'], model=idx_model
                                        )
                                        idx_path = rag_utils.save_index(doc['id'], index)
                                        database.update_document_index(doc['id'], idx_path)
                                    st.success(f"Indexed {index['page_count']} pages")
                                    st.rerun()
                            else:
                                st.warning("Add a model first to enable AI indexing.")
                        else:
                            idx = rag_utils.load_index(doc['index_path'])
                            pages = idx['page_count'] if idx else '?'
                            st.success(f"Index ready — {pages} pages")

                    with col_del:
                        if st.button("Delete Document", key=f"del_doc_{doc['id']}", type="primary"):
                            if doc.get('index_path') and os.path.exists(doc['index_path']):
                                os.remove(doc['index_path'])
                            if os.path.exists(doc['file_path']):
                                os.remove(doc['file_path'])
                            database.delete_document(doc['id'])
                            st.rerun()

                    # Question generation
                    if doc['index_status'] == 'indexed':
                        st.markdown("---")
                        st.subheader("Generate Questions")
                        with st.form(key=f"gen_q_{doc['id']}"):
                            q_types = st.multiselect(
                                "Question types",
                                ["Multiple Choice", "Fill-in-the-blank", "Short Answer", "True/False"],
                                default=["Multiple Choice", "Short Answer"]
                            )
                            q_count = st.slider("Number of questions per type", 1, 5, 3)
                            assign_all = st.checkbox("Assign to all students")
                            gen_model_names = {m['id']: m['name'] for m in models_list}
                            gen_model_id = st.selectbox("Model", gen_model_names.keys(),
                                                        format_func=lambda i: gen_model_names[i],
                                                        key=f"gen_model_{doc['id']}")
                            if st.form_submit_button("Generate"):
                                gen_model = next((m for m in models_list if m['id'] == gen_model_id), None)
                                if gen_model:
                                    idx = rag_utils.load_index(doc['index_path'])
                                    context = rag_utils.retrieve_context(idx, doc['name'], top_n=5)
                                    assigned_id = None
                                    all_students = database.get_all_students() if assign_all else []
                                    for qtype in q_types:
                                        prompt_text = (
                                            f"Based on the following document content, generate {q_count} "
                                            f"{qtype} questions for students studying {doc.get('subject') or 'this subject'}.\n"
                                            f"Format each question clearly numbered.\n"
                                            f"For Multiple Choice, include 4 options (A-D) and mark the answer.\n"
                                            f"For Fill-in-the-blank, use ___ for the blank and provide the answer.\n"
                                            f"For True/False, state True or False as the answer.\n\n"
                                            f"Document content:\n{context}"
                                        )
                                        with st.spinner(f"Generating {qtype} questions..."):
                                            raw = call_model_api_single(gen_model, prompt_text)
                                        if assign_all and all_students:
                                            for s in all_students:
                                                database.save_generated_question(
                                                    doc['id'], qtype, raw, assigned_to=s['id']
                                                )
                                        else:
                                            database.save_generated_question(doc['id'], qtype, raw)
                                    st.success("Questions generated and saved!")
                                    st.rerun()

                    # Show saved questions
                    existing_qs = database.get_questions_for_document(doc['id'])
                    if existing_qs:
                        st.markdown("---")
                        st.subheader("Saved Questions")
                        for q in existing_qs:
                            with st.expander(f"[{q['question_type']}] {q['question'][:60]}..."):
                                st.markdown(q['question'])
                                if st.button("Delete", key=f"del_q_{q['id']}"):
                                    database.delete_question(q['id'])
                                    st.rerun()

    with tab_system:
        st.header("System Customization")
        st.info("Customize the login page branding for your school.")
        
        sys_settings = load_system_settings()
        
        with st.form("sys_branding"):
            school_name = st.text_input("School / Platform Name", value=sys_settings.get("school_name", "DSE AI Learner Platform"))
            logo_url = st.text_input("Logo URL (Image Address)", value=sys_settings.get("logo_url", ""), help="Enter a URL to your school logo (png/jpg).")
            # Or upload logic could be added here but simple URL or local path is easier for now
            bg_url = st.text_input("Background Image URL", value=sys_settings.get("background_url", ""), help="Enter a URL for the login page background.")
            
            if st.form_submit_button("Save Branding"):
                new_settings = {
                    "school_name": school_name,
                    "logo_url": logo_url,
                    "background_url": bg_url
                }
                save_system_settings(new_settings)
                st.success("System settings updated! Refresh the page to see changes.")
def render_student_workspace(user):
    username = user['username']
    config = load_config(username)

    st.sidebar.title(f"{user['name']}")
    st.sidebar.markdown("---")

    menu = st.sidebar.radio(
        "Navigation",
        ["Chat", "Notebook", "Profile"],
        index=0,
        label_visibility="collapsed"
    )
    st.sidebar.markdown("---")

    # Model selector
    allowed_models = database.get_allowed_models_for_student(user['id'])
    selected_model = None
    if allowed_models:
        options = {m['id']: m['name'] for m in allowed_models}
        sel = config.get('model_id')
        idx = list(options.keys()).index(sel) if sel in options else 0
        chosen_id = st.sidebar.selectbox(
            "Model", list(options.keys()),
            format_func=lambda i: options[i], index=idx
        )
        config['model_id'] = chosen_id
        save_config(username, config)
        selected_model = next((m for m in allowed_models if m['id'] == chosen_id), None)
    else:
        st.sidebar.write("No models available")

    if menu == "Profile":
        render_profile(user)

    elif menu == "Chat":
        if "session_id" not in st.session_state:
            st.session_state.session_id = str(uuid.uuid4())
        if "messages" not in st.session_state:
            st.session_state.messages = []

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if "image_path" in msg:
                    img_path = get_image_path(username, msg["image_path"])
                    if os.path.exists(img_path):
                        st.image(img_path, width=300)

        uploaded_file = st.sidebar.file_uploader(
            "Attach image", type=["jpg", "png", "jpeg"], label_visibility="visible"
        )

        user_input = st.chat_input("Your message...")

        if user_input:
            with st.chat_message("user"):
                st.markdown(user_input)
                if uploaded_file:
                    st.image(uploaded_file, width=300)

            msg_data = {"role": "user", "content": user_input}
            if uploaded_file:
                msg_data["image_path"] = save_image(username, uploaded_file.getvalue())
            st.session_state.messages.append(msg_data)

            if selected_model:
                # Build message list for multi-turn (text only for context)
                chat_messages = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages
                ]
                response_text = call_model_api(selected_model, chat_messages)
            else:
                response_text = "[No model available. Ask your teacher to grant model access.]"

            with st.chat_message("assistant"):
                st.markdown(response_text)
            st.session_state.messages.append({"role": "assistant", "content": response_text})
            save_session(username, st.session_state.session_id, st.session_state.messages)
            st.session_state.last_qa = (user_input, response_text)
            st.rerun()

        if "last_qa" in st.session_state and selected_model:
            q, a = st.session_state.last_qa
            if st.button("Add Last Q&A to Notebook"):
                with st.spinner("Summarizing..."):
                    summary = call_model_api_single(
                        selected_model,
                        f"Summarize the key concept or mistake in 1-2 sentences.\nQ: {q}\nA: {a}"
                    )
                    add_to_notebook(username, q, a, summary)
                st.success("Added to Notebook!")
                del st.session_state.last_qa

    elif menu == "Notebook":
        st.header("Your Notebook")
        notebook = load_notebook(username)
        if not notebook:
            st.info("No entries yet.")
        else:
            notebook.sort(key=lambda x: x['timestamp'], reverse=True)
            for entry in notebook:
                with st.expander(f"{entry['title']} - {entry['timestamp'][:16]}"):
                    st.write("**Question:**")
                    st.write(entry['question'])
                    st.write("**Answer:**")
                    st.write(entry['answer'])
                    if entry.get('summary'):
                        st.write("**Summary:**")
                        st.write(entry['summary'])
                    if st.button("Delete", key=f"delete_note_{entry['id']}"):
                        delete_notebook_entry(username, entry['id'])
                        st.rerun()
                

# --- Main Entry ---

if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user:
    # Sidebar Logout
    with st.sidebar:
        if st.button("Logout"):
            st.session_state.user = None
            st.rerun()
            
    user = st.session_state.user
    if user['role'] == 'teacher':
        render_teacher_dashboard()
    else:
        render_student_workspace(user)
else:
    render_login()
