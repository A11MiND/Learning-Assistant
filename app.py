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

# ---- model API helper ----
def call_model_api(model, user_input):
    """Send a request to the configured model with system prompt."""
    # model is dict with keys: api_url, api_key, system_prompt
    prompt = user_input
    if model.get("system_prompt"):
        prompt = model["system_prompt"] + "\n\n" + user_input
    headers = {"Content-Type": "application/json"}
    if model.get("api_key"):
        headers["Authorization"] = f"Bearer {model['api_key']}"
    payload = {"prompt": prompt}
    try:
        resp = requests.post(model["api_url"], json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        # support common keys
        return data.get("response") or data.get("output") or data.get("text") or str(data)
    except Exception as e:
        return f"[Model Error]: {e}"

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
    
    tab_students, tab_models, tab_system = st.tabs(["Student Management", "Model Management", "System Customization"])
    
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
                    allowed = {m['id'] for m in database.get_allowed_models_for_student(s['id'])}
                    for m in all_models:
                        checked = m['id'] in allowed
                        new_val = st.checkbox(m['name'], value=checked, key=f"access_{s['id']}_{m['id']}")
                        if new_val != checked:
                            database.set_student_model_access(s['id'], m['id'], 1 if new_val else 0)
                            st.rerun()
                st.divider()

    with tab_models:
        st.header("Model Management")
        st.info("Add, edit or remove large language models and their system prompts.")
        
        # list existing models
        models = database.get_models()
        if models:
            for m in models:
                with st.expander(f"{m['name']} (ID {m['id']})"):
                    with st.form(key=f"edit_model_{m['id']}"):
                        name = st.text_input("Display Name", value=m['name'])
                        url = st.text_input("API URL", value=m['api_url'])
                        key = st.text_input("API Key", value=m.get('api_key',''))
                        prompt = st.text_area("System Prompt", value=m.get('system_prompt',''))
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.form_submit_button("Save Changes"):
                                database.update_model(m['id'], name=name, api_url=url, api_key=key or None, system_prompt=prompt or None)
                                st.success("Updated")
                                st.experimental_rerun()
                        with col_b:
                            if st.form_submit_button("Delete Model", type="primary"):
                                database.delete_model(m['id'])
                                st.experimental_rerun()
        else:
            st.write("No models defined yet.")
        
        st.markdown("---")
        st.subheader("Add New Model")
        with st.form("add_model"):
            name = st.text_input("Display Name")
            url = st.text_input("API URL")
            key = st.text_input("API Key (optional)")
            prompt = st.text_area("System Prompt (optional)")
            if st.form_submit_button("Create Model"):
                if name and url:
                    database.create_model(name, url, api_key=key or None, system_prompt=prompt or None)
                    st.success("Model created")
                    st.experimental_rerun()
                else:
                    st.error("Name and URL are required")
    
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
    
    # Menu UI (simplified: chat & notebook & profile)
    st.sidebar.markdown("---")
    menu = st.sidebar.radio(
        "Navigation", 
        ["Chat", "Notebook", "Profile"],
        index=0,
        label_visibility="collapsed"
    )
    st.sidebar.markdown("---")
    
    # model selection dropdown for students
    allowed_models = database.get_allowed_models_for_student(user['id'])
    if allowed_models:
        sel = config.get('model_id')
        options = {m['id']: m['name'] for m in allowed_models}
        chosen = st.sidebar.selectbox("Model", options.keys(), format_func=lambda i: options[i], index=list(options.keys()).index(sel) if sel in options else 0)
        config['model_id'] = chosen
        save_config(username, config)
    else:
        st.sidebar.write("No models available")
    
    if menu == "Profile":
        render_profile(user)
    
    elif menu == "Chat":
        # Chat Logic
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
                elif "image" in msg:
                    st.image(msg["image"], width=300)
                elif msg.get("has_image"):
                    st.caption("[Image from history]")

        with st.popover("Attach Image", help="Attach an image file"):
            uploaded_file = st.file_uploader("Upload Image", type=["jpg", "png", "jpeg"], label_visibility="collapsed")

        if uploaded_file:
            with st.expander("Image Attached", expanded=True):
                st.image(uploaded_file, width=150)

        user_input = st.chat_input("Your message...")

        if user_input:
            with st.chat_message("user"):
                st.markdown(user_input)
                if uploaded_file:
                    st.image(uploaded_file, width=300)
            msg_data = {"role": "user", "content": user_input}
            if uploaded_file:
                image_bytes = uploaded_file.getvalue()
                filename = save_image(username, image_bytes)
                msg_data["image_path"] = filename
            st.session_state.messages.append(msg_data)

            # determine model
            model = None
            if config.get('model_id'):
                models = database.get_models()
                for m in models:
                    if m['id'] == config['model_id']:
                        model = m
                        break
            if not model and allowed_models:
                model = allowed_models[0]

            response_text = ""
            if model:
                response_text = call_model_api(model, user_input)
            else:
                response_text = "[No model available]"

            with st.chat_message("assistant"):
                st.markdown(response_text)
            st.session_state.messages.append({"role": "assistant", "content": response_text})
            save_session(username, st.session_state.session_id, st.session_state.messages)
            st.session_state.last_qa = (user_input, response_text)
            st.rerun()

        if "last_qa" in st.session_state:
            q, a = st.session_state.last_qa
            if st.button("Add Last Q&A to Notebook"):
                with st.spinner("Analyzing and summarizing..."):
                    summary_prompt = f"Analyze this student's question and the answer. Summarize the key mistake or concept." \
                                     f"\n\nQuestion: {q}\nAnswer: {a}"
                    summary = call_model_api(model, summary_prompt) if model else ""
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

            # Workspace selection dropdown
            workspace_options = st.session_state.get('allm_workspaces', {})
            current_slug = config.get("slug", "default")
            
            # If current slug not in loaded list, add it manually to options so it shows up
            if current_slug and current_slug not in workspace_options:
                workspace_options[current_slug] = f"{current_slug} (Current)"
                
            selected_slug_key = st.selectbox(
                "Select Workspace", 
                options=list(workspace_options.keys()),
                format_func=lambda x: workspace_options[x],
                index=list(workspace_options.keys()).index(current_slug) if current_slug in workspace_options else 0
            ) 
            allm_slug = selected_slug_key if selected_slug_key else st.text_input("Workspace Slug (Manual)", value=current_slug)
            
            st.markdown("---")
            if st.form_submit_button("Save Configuration", type="primary"):
                new_config = {
                    "app_title": app_title,
                    "system_prompt": system_prompt,
                    "ollama_url": ollama_url,
                    "ollama_model": ollama_model,
                    "url": allm_url,
                    "api_key": allm_key,
                    "slug": allm_slug
                }
                save_config(username, new_config)
                st.success("Configuration Saved!")
                

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
