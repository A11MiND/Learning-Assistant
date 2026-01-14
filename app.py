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

st.set_page_config(page_title="DSE AI Tutor Platform", page_icon="🎓", layout="wide")

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
    
    title = sys_settings.get("school_name", "🔐 DSE AI Learner Login")
    st.title(title)
    
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            user = database.verify_user(username, password)
            if user:
                if user.get('account_status') == 'banned':
                    st.error("🚫 This account has been suspended.")
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
    st.header("👤 User Profile")
    
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
    st.title("👨‍🏫 Teacher Dashboard")
    
    tab_students, tab_system = st.tabs(["👥 Student Management", "⚙️ System Customization"])
    
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
        
        for s in students:
            with st.container():
                cols = st.columns([1, 2, 2, 1.5, 1.5, 4])
                cols[0].write(s['id'])
                cols[1].write(s['name'])
                cols[2].write(s['username'])
                
                # App Status
                dep = database.get_deployment(s['id'])
                app_status = "🔴 Stopped"
                app_url = ""
                is_running = False
                if dep and dep['status'] == 'running':
                    try:
                        os.kill(dep['pid'], 0)
                        app_status = f"🟢 (: {dep['port']})"
                        app_url = f"http://{SERVER_IP}:{dep['port']}"
                        is_running = True
                    except:
                        app_status = "⚠️ Zombie"
                cols[3].write(app_status)
                
                # Account Status
                acc_status = s.get('account_status', 'active')
                if acc_status == 'banned':
                    cols[4].markdown("🔴 **BANNED**")
                else:
                    cols[4].markdown("🟢 Active")
                
                # Actions
                with cols[5]:
                    # Row 1: App Control & Ban - ONE LINE
                    # Adjust ratio to fit buttons tightly
                    sub_cols = st.columns([1.2, 1.2, 1.2], gap="small")
                    
                    with sub_cols[0]:
                        if is_running:
                            if st.button("⏹️ Stop", key=f"stop_{s['id']}", use_container_width=True):
                                stop_student_app(s['id'])
                                st.rerun()
                        else:
                            if st.button("▶️ Run", key=f"run_{s['id']}", use_container_width=True):
                                 start_student_app(s['id'], s['username'])
                                 st.rerun()
                    with sub_cols[1]:
                        if app_url:
                            st.link_button("🔗 Open", app_url, use_container_width=True)
                        else:
                             st.button("🔗 Open", key=f"dis_{s['id']}", disabled=True, use_container_width=True)
                    with sub_cols[2]:
                        if acc_status == 'banned':
                            if st.button("🔓 Unban", key=f"unban_{s['id']}", use_container_width=True):
                                database.update_user_status(s['id'], 'active')
                                st.rerun()
                        else:
                            if st.button("🚫 Ban", key=f"ban_{s['id']}", use_container_width=True):
                                database.update_user_status(s['id'], 'banned')
                                stop_student_app(s['id']) # Stop app if banned
                                st.rerun()
                    
                    # Row 2: Edit & Delete
                    with st.expander("⚙️ Edit / Delete"):
                        with st.form(key=f"edit_form_{s['id']}"):
                            new_name = st.text_input("Name", value=s['name'])
                            new_user = st.text_input("Username", value=s['username'])
                            reset_pw = st.checkbox("Reset Password to 'password'")
                            
                            col_a, col_b = st.columns(2)
                            with col_a:
                                if st.form_submit_button("💾 Save Changes", use_container_width=True):
                                    pw = "password" if reset_pw else None
                                    success, msg = database.admin_update_user(s['id'], new_name, new_user, pw)
                                    if success:
                                        st.success("Updated!")
                                        time.sleep(0.5)
                                        st.rerun()
                                    else:
                                        st.error(msg)
                            with col_b:
                                if st.form_submit_button("🗑️ Delete User", type="primary", use_container_width=True):
                                    database.delete_user(s['id'])
                                    st.rerun()
                st.divider()

    with tab_system:
        st.header("🎨 System Customization")
        st.info("Customize the login page branding for your school.")
        
        sys_settings = load_system_settings()
        
        with st.form("sys_branding"):
            school_name = st.text_input("School / Platform Name", value=sys_settings.get("school_name", "DSE AI Learner Platform"))
            logo_url = st.text_input("Logo URL (Image Address)", value=sys_settings.get("logo_url", ""), help="Enter a URL to your school logo (png/jpg).")
            # Or upload logic could be added here but simple URL or local path is easier for now
            bg_url = st.text_input("Background Image URL", value=sys_settings.get("background_url", ""), help="Enter a URL for the login page background.")
            
            if st.form_submit_button("💾 Save Branding"):
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
    
    st.sidebar.title(f"🎓 {user['name']}")
    
    # Enhanced Menu UI
    st.sidebar.markdown("---")
    menu = st.sidebar.radio(
        "Navigation", 
        ["🛠️ App Designer", "🚀 Publish & Run", "👤 Profile"],
        index=0,
        label_visibility="collapsed"
    )
    st.sidebar.markdown("---")
    
    if menu == "👤 Profile":
        render_profile(user)
        
    elif menu == "🛠️ App Designer":
        st.header("🛠️ Design Your AI Tutor")
        
        # Config Form
        with st.form("app_config"):
            app_title = st.text_input("App Title", value=config.get("app_title", "My AI Tutor"))
            system_prompt = st.text_area("System Prompt", value=config.get("system_prompt", "You are a helpful tutor."))
            
            st.markdown("### 🤖 AI Backend Settings")
            
            # Ollama Settings
            col1, col2 = st.columns([3, 1])
            with col1:
                ollama_url = st.text_input("Ollama URL", value=config.get("ollama_url", DEFAULT_OLLAMA_URL))
            with col2:
                # Dynamic Model Loading
                st.write("") # Spacer
                st.write("") # Spacer
                if st.form_submit_button("🔄 Load Models"):
                    try:
                        res = requests.get(f"{ollama_url}/api/tags", timeout=2)
                        if res.status_code == 200:
                            models = [m['name'] for m in res.json()['models']]
                            st.session_state['ollama_models'] = models
                            st.toast("Models Loaded!", icon="✅")
                        else:
                            st.toast("Failed to load models", icon="❌")
                    except Exception as e:
                        st.toast(f"Error: {e}", icon="❌")
            
            model_options = st.session_state.get('ollama_models', [config.get("ollama_model", "qwen3-vl:8b")])
            ollama_model = st.selectbox("Select Ollama Model", model_options, index=0 if model_options else None)
            
            st.divider()
            
            # AnythingLLM Settings
            allm_url = st.text_input("AnythingLLM URL", value=config.get("url", DEFAULT_ANYTHINGLLM_URL))
            allm_key = st.text_input("AnythingLLM API Key", value=config.get("api_key", ""), type="password")
            
            if st.form_submit_button("🔍 Load Workspaces"):
                 if not allm_key:
                     st.warning("Please enter API Key first.")
                 else:
                    try:
                        headers = {
                            "Authorization": f"Bearer {allm_key}", 
                            "accept": "application/json"
                        }
                        # Use correct endpoint to list workspaces
                        res = requests.get(f"{allm_url}/workspaces", headers=headers, timeout=5)
                        if res.status_code == 200:
                             data = res.json()
                             # Expecting {"workspaces": [{"slug": "...", "name": "..."}, ...]}
                             workspaces = data.get("workspaces", [])
                             slug_options = {w['slug']: f"{w['name']} ({w['slug']})" for w in workspaces}
                             st.session_state['allm_workspaces'] = slug_options
                             st.toast(f"Loaded {len(workspaces)} workspaces!", icon="✅")
                        else:
                             st.toast(f"Connection Failed: {res.status_code} - {res.text[:50]}", icon="⚠️")
                    except Exception as e:
                        st.toast(f"Error: {e}", icon="❌")

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
            if st.form_submit_button("💾 Save Configuration", type="primary"):
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
                
    elif menu == "🚀 Publish & Run":
        st.header("🚀 Publish Your App")
        st.info("Publishing your app will launch it on a dedicated port, accessible to others on the network.")
        
        dep = database.get_deployment(user['id'])
        is_running = False
        if dep and dep['status'] == 'running':
            try:
                os.kill(dep['pid'], 0)
                is_running = True
            except:
                pass
        
        if is_running:
            st.success(f"✅ App is Running!")
            url = f"http://{SERVER_IP}:{dep['port']}"
            st.markdown(f"### 🔗 [Click to Open App]({url})")
            st.info("⚠️ Note: If URL not accessible, check if you are connected to the same network.")
            st.code(url, language="text")
            
            if st.button("🛑 Stop App"):
                stop_student_app(user['id'])
                st.rerun()
        else:
            if st.button("▶️ Publish & Launch"):
                with st.spinner("Launching your app..."):
                    port = start_student_app(user['id'], username)
                    st.success(f"App launched on port {port}!")
                    time.sleep(1)
                    st.rerun()

# --- Main Entry ---

if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user:
    # Sidebar Logout
    with st.sidebar:
        if st.button("🚪 Logout"):
            st.session_state.user = None
            st.rerun()
            
    user = st.session_state.user
    if user['role'] == 'teacher':
        render_teacher_dashboard()
    else:
        render_student_workspace(user)
else:
    render_login()
