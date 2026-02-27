import streamlit as st
import json
import os
import glob
import uuid
import socket
from datetime import datetime
import database
import rag_utils
from openai import OpenAI

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATA_DIR = "data"
SYSTEM_SETTINGS_FILE = os.path.join(DATA_DIR, "system", "settings.json")

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
DEFAULT_OLLAMA_URL = f"http://{SERVER_IP}:11434"
DEFAULT_ANYTHINGLLM_URL = f"http://{SERVER_IP}:3001/api/v1"

# ---------------------------------------------------------------------------
# System settings
# ---------------------------------------------------------------------------

def load_system_settings():
    if os.path.exists(SYSTEM_SETTINGS_FILE):
        try:
            with open(SYSTEM_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_system_settings(settings):
    os.makedirs(os.path.dirname(SYSTEM_SETTINGS_FILE), exist_ok=True)
    with open(SYSTEM_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)

# ---------------------------------------------------------------------------
# Model API
# ---------------------------------------------------------------------------

def call_model_api(model, messages):
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
    return call_model_api(model, [{"role": "user", "content": prompt}])

# ---------------------------------------------------------------------------
# Student data helpers
# ---------------------------------------------------------------------------

def get_user_dir(username):
    return os.path.join(DATA_DIR, username)

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
    to_save = []
    for m in messages:
        mc = m.copy()
        mc.pop("image_data", None)
        to_save.append(mc)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump({
            "id": session_id,
            "title": title,
            "updated_at": datetime.now().isoformat(),
            "messages": to_save
        }, f, ensure_ascii=False, indent=2)

def load_session(username, session_id):
    file_path = os.path.join(get_user_dir(username), "history", f"{session_id}.json")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("messages", []), data.get("title", "New Chat")
    except Exception:
        return [], "New Chat"

def delete_session(username, session_id):
    file_path = os.path.join(get_user_dir(username), "history", f"{session_id}.json")
    if os.path.exists(file_path):
        os.remove(file_path)

def save_image(username, image_bytes):
    images_dir = os.path.join(get_user_dir(username), "images")
    os.makedirs(images_dir, exist_ok=True)
    filename = f"{uuid.uuid4()}.png"
    with open(os.path.join(images_dir, filename), "wb") as f:
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
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_to_notebook(username, question, answer, summary=None):
    nb = load_notebook(username)
    nb.append({
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "title": (summary or question)[:50],
        "question": question,
        "answer": answer,
        "summary": summary
    })
    save_notebook(username, nb)

def delete_notebook_entry(username, entry_id):
    nb = [e for e in load_notebook(username) if e["id"] != entry_id]
    save_notebook(username, nb)

def update_notebook_entry_title(username, entry_id, new_title):
    nb = load_notebook(username)
    for e in nb:
        if e["id"] == entry_id:
            e["title"] = new_title
    save_notebook(username, nb)

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

database.init_db()
database.cleanup_zombies()

sys_settings = load_system_settings()
st.set_page_config(
    page_title=sys_settings.get("school_name", "DSE AI Tutor Platform"),
    layout="wide"
)

# Background CSS
if sys_settings.get("background_url"):
    st.markdown(f"""<style>
.stApp {{
    background-image: url("{sys_settings['background_url']}");
    background-size: cover; background-attachment: fixed;
}}
</style>""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state bootstrap
# ---------------------------------------------------------------------------

if "user" not in st.session_state:
    st.session_state.user = None

# ===========================================================================
# LOGIN / REGISTER
# ===========================================================================

def render_login():
    school = sys_settings.get("school_name", "DSE AI Tutor Platform")
    if sys_settings.get("logo_url"):
        st.image(sys_settings["logo_url"], width=120)
    st.title(school)

    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        with st.form("login_form"):
            login_id = st.text_input("Username or Email")
            pwd = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)
        if submitted:
            user = database.verify_user(login_id, pwd)
            if user:
                if user.get("account_status") == "banned":
                    st.error("Your account has been banned. Please contact admin.")
                else:
                    st.session_state.user = user
                    st.rerun()
            else:
                st.error("Invalid username/email or password.")
        st.caption("Forgot password? Contact your teacher or admin.")

    with tab_register:
        st.write("Register a new student account.")
        with st.form("reg_form"):
            r_user = st.text_input("Username")
            r_email = st.text_input("Email")
            r_name = st.text_input("Full Name")
            r_pwd = st.text_input("Password", type="password")
            r_pwd2 = st.text_input("Confirm Password", type="password")
            r_submit = st.form_submit_button("Register", use_container_width=True)
        if r_submit:
            if not r_user or not r_pwd:
                st.error("Username and password are required.")
            elif r_pwd != r_pwd2:
                st.error("Passwords do not match.")
            else:
                ok, msg = database.create_user(r_user, r_pwd, "student", r_name or r_user,
                                               email=r_email or None)
                if ok:
                    st.success("Account created! You can now log in.")
                else:
                    st.error(f"Registration failed: {msg}")

# ===========================================================================
# ADMIN DASHBOARD
# ===========================================================================

def render_admin_dashboard(user):
    with st.sidebar:
        st.subheader(f"Admin: {user['name']}")
        nav = st.radio("Navigation", [
            "👥 Users",
            "🏫 Classes",
            "🤝 Teacher-Students",
            "⚙️ System Settings"
        ], label_visibility="collapsed")
        st.divider()
        if st.button("Logout", use_container_width=True):
            st.session_state.user = None
            st.rerun()

    if nav == "👥 Users":
        _admin_users(user)
    elif nav == "🏫 Classes":
        _admin_classes()
    elif nav == "🤝 Teacher-Students":
        _admin_teacher_students()
    elif nav == "⚙️ System Settings":
        _admin_system_settings()


def _admin_users(current_admin):
    st.header("User Management")

    col_a, col_b = st.columns([2, 1])

    with col_a:
        st.subheader("All Users")
        all_users = database.get_all_users()
        role_filter = st.selectbox("Filter by role", ["all", "admin", "teacher", "student"])
        if role_filter != "all":
            all_users = [u for u in all_users if u["role"] == role_filter]

        for u in all_users:
            with st.expander(f"{u['username']} | {u['role']} | {u.get('account_status','active')}"):
                n_name = st.text_input("Name", u["name"], key=f"un_{u['id']}")
                n_uname = st.text_input("Username", u["username"], key=f"uu_{u['id']}")
                n_email = st.text_input("Email", u.get("email") or "", key=f"ue_{u['id']}")
                n_pwd = st.text_input("New Password (leave blank to keep)", type="password", key=f"up_{u['id']}")
                n_role = st.selectbox("Role", ["student","teacher","admin"],
                                      index=["student","teacher","admin"].index(u["role"]),
                                      key=f"ur_{u['id']}")
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("Save", key=f"usave_{u['id']}"):
                        ok, msg = database.admin_update_user(
                            u["id"], n_name, n_uname,
                            email=n_email or None,
                            password=n_pwd or None,
                            role=n_role
                        )
                        if ok:
                            st.success("Updated")
                            st.rerun()
                        else:
                            st.error(msg)
                with col2:
                    status = u.get("account_status", "active")
                    if status == "active":
                        if st.button("Ban", key=f"uban_{u['id']}"):
                            database.update_user_status(u["id"], "banned")
                            st.rerun()
                    else:
                        if st.button("Unban", key=f"uunban_{u['id']}"):
                            database.update_user_status(u["id"], "active")
                            st.rerun()
                with col3:
                    if u["id"] != current_admin["id"]:
                        if st.button("Delete", key=f"udel_{u['id']}", type="primary"):
                            database.delete_user(u["id"])
                            st.rerun()

    with col_b:
        st.subheader("Add User")
        with st.form("add_user_form"):
            nu = st.text_input("Username")
            ne = st.text_input("Email")
            nn = st.text_input("Full Name")
            np_ = st.text_input("Password", type="password")
            nr = st.selectbox("Role", ["student", "teacher", "admin"])
            if st.form_submit_button("Create User"):
                if nu and np_:
                    ok, msg = database.create_user(nu, np_, nr, nn or nu, email=ne or None)
                    if ok:
                        st.success("Created")
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.warning("Username and password required.")

        st.divider()
        st.subheader("Import Students (CSV)")
        st.caption("CSV format: username,email,name,password")
        csv_file = st.file_uploader("Upload CSV", type=["csv"], key="csv_import")
        if csv_file and st.button("Import"):
            text = csv_file.read().decode("utf-8")
            ok_count, errors = database.import_students_from_csv(text)
            st.success(f"Imported {ok_count} student(s).")
            if errors:
                for e in errors:
                    st.warning(e)
            st.rerun()


def _admin_classes():
    st.header("Class Management (All Teachers)")
    all_classes = database.get_all_classes()
    teachers = database.get_all_teachers()
    teacher_map = {t["id"]: t["name"] for t in teachers}

    if not all_classes:
        st.info("No classes yet. Teachers can create classes in their dashboard.")
        return

    for cls in all_classes:
        with st.expander(f"{cls['name']} — Teacher: {cls.get('teacher_name', '?')} | Subject: {cls.get('subject', '')}"):
            n_name = st.text_input("Class Name", cls["name"], key=f"cln_{cls['id']}")
            n_subj = st.text_input("Subject", cls.get("subject") or "", key=f"cls_{cls['id']}")
            if st.button("Save Changes", key=f"clsave_{cls['id']}"):
                database.update_class(cls["id"], name=n_name, subject=n_subj)
                st.success("Updated")
                st.rerun()

            students = database.get_students_in_class(cls["id"])
            st.markdown(f"**Students ({len(students)}):** " +
                        ", ".join(s["username"] for s in students) if students else "**Students:** (none)")

            if st.button("Delete Class", key=f"cldel_{cls['id']}", type="primary"):
                database.delete_class(cls["id"])
                st.rerun()


def _admin_teacher_students():
    st.header("Teacher-Student Relationships")
    teachers = database.get_all_teachers()
    all_students = database.get_all_students()
    student_map = {s["id"]: s["username"] for s in all_students}

    if not teachers:
        st.info("No teachers found.")
        return

    for teacher in teachers:
        st.subheader(f"Teacher: {teacher['name']} ({teacher['username']})")
        classes = database.get_classes_for_teacher(teacher["id"])
        if not classes:
            st.caption("No classes.")
            continue
        for cls in classes:
            with st.expander(f"Class: {cls['name']}"):
                enrolled = database.get_students_in_class(cls["id"])
                enrolled_ids = {s["id"] for s in enrolled}
                for s in all_students:
                    is_in = s["id"] in enrolled_ids
                    checked = st.checkbox(
                        s["username"],
                        value=is_in,
                        key=f"ats_{teacher['id']}_{cls['id']}_{s['id']}"
                    )
                    if checked != is_in:
                        if checked:
                            database.add_student_to_class(cls["id"], s["id"])
                        else:
                            database.remove_student_from_class(cls["id"], s["id"])
                        st.rerun()


def _admin_system_settings():
    st.header("System Settings")
    settings = load_system_settings()

    with st.form("sys_settings_form"):
        school_name = st.text_input("School / Platform Name",
                                    value=settings.get("school_name", "DSE AI Tutor Platform"))
        logo_url = st.text_input("Logo URL", value=settings.get("logo_url", ""))
        bg_url = st.text_input("Background Image URL", value=settings.get("background_url", ""))
        if st.form_submit_button("Save Settings"):
            settings["school_name"] = school_name
            settings["logo_url"] = logo_url
            settings["background_url"] = bg_url
            save_system_settings(settings)
            st.success("Settings saved. Refresh the page to see changes.")


# ===========================================================================
# TEACHER DASHBOARD
# ===========================================================================

def render_teacher_dashboard(user):
    with st.sidebar:
        st.subheader(f"Teacher: {user['name']}")
        nav = st.radio("Navigation", [
            "🏫 My Classes",
            "🤖 Models",
            "📁 Knowledge Base"
        ], label_visibility="collapsed")
        st.divider()
        if st.button("Logout", use_container_width=True):
            st.session_state.user = None
            st.rerun()

    if nav == "🏫 My Classes":
        _teacher_classes(user)
    elif nav == "🤖 Models":
        _teacher_models(user)
    elif nav == "📁 Knowledge Base":
        _teacher_kb(user)


def _teacher_classes(user):
    st.header("My Classes")
    teacher_id = user["id"]

    # Create class
    with st.expander("Create New Class", expanded=False):
        with st.form("new_class_form"):
            c_name = st.text_input("Class Name")
            c_subj = st.text_input("Subject (optional)")
            if st.form_submit_button("Create"):
                if c_name:
                    database.create_class(c_name, teacher_id, c_subj or None)
                    st.success("Class created")
                    st.rerun()

    classes = database.get_classes_for_teacher(teacher_id)
    all_students = database.get_all_students()
    all_models = database.get_models()
    model_map = {m["id"]: m["name"] for m in all_models}

    if not classes:
        st.info("No classes yet. Create one above.")
        return

    for cls in classes:
        with st.expander(f"Class: {cls['name']} | Subject: {cls.get('subject','')}", expanded=False):
            n_name = st.text_input("Class Name", cls["name"], key=f"tcln_{cls['id']}")
            n_subj = st.text_input("Subject", cls.get("subject") or "", key=f"tcls_{cls['id']}")
            if st.button("Save", key=f"tclsave_{cls['id']}"):
                database.update_class(cls["id"], name=n_name, subject=n_subj)
                st.success("Saved")
                st.rerun()

            st.markdown("---")
            st.markdown("**Students in this class**")
            enrolled = database.get_students_in_class(cls["id"])
            enrolled_ids = {s["id"] for s in enrolled}
            for s in all_students:
                is_in = s["id"] in enrolled_ids
                checked = st.checkbox(
                    s["username"],
                    value=is_in,
                    key=f"tcs_{cls['id']}_{s['id']}"
                )
                if checked != is_in:
                    if checked:
                        database.add_student_to_class(cls["id"], s["id"])
                    else:
                        database.remove_student_from_class(cls["id"], s["id"])
                    st.rerun()

            st.markdown("---")
            st.markdown("**Model Access for this Class**")
            cls_access = database.get_class_model_access(cls["id"])
            for m in all_models:
                cur = cls_access.get(m["id"], {})
                col1, col2 = st.columns([3, 2])
                with col1:
                    allowed = st.checkbox(
                        m["name"],
                        value=bool(cur.get("allowed", 0)),
                        key=f"tma_{cls['id']}_{m['id']}"
                    )
                with col2:
                    override = st.text_input(
                        "Override prompt",
                        value=cur.get("override_prompt") or "",
                        key=f"tmop_{cls['id']}_{m['id']}",
                        label_visibility="collapsed",
                        placeholder="Override prompt (optional)"
                    )
                save_key = f"tmasave_{cls['id']}_{m['id']}"
                if st.button("Apply", key=save_key):
                    database.set_class_model_access(cls["id"], m["id"], allowed, override or None)
                    st.success("Saved")

            st.markdown("---")
            if st.button("Delete Class", key=f"tcldel_{cls['id']}", type="primary"):
                database.delete_class(cls["id"])
                st.rerun()


def _teacher_models(user):
    st.header("Model Management")
    all_models = database.get_models()
    all_docs = database.get_documents()
    indexed_docs = [d for d in all_docs if d["index_status"] == "indexed"]
    doc_map = {d["id"]: d["name"] for d in indexed_docs}

    # --- Create model ---
    with st.expander("Add New Model", expanded=False):
        with st.form("add_model_form"):
            m_name = st.text_input("Display Name")
            m_model_name = st.text_input("Model Name (e.g. llama3)")
            m_url = st.text_input("API URL", value=DEFAULT_OLLAMA_URL + "/v1")
            m_key = st.text_input("API Key (leave blank if not needed)")
            m_prompt = st.text_area("System Prompt (optional)")
            if st.form_submit_button("Add Model"):
                if m_name and m_url:
                    ok = database.create_model(
                        m_name, m_model_name, m_url, m_key or None,
                        m_prompt or None, created_by=user["id"]
                    )
                    if ok:
                        st.success("Model added")
                        st.rerun()
                    else:
                        st.error("Model name already exists.")
                else:
                    st.warning("Display name and API URL required.")

    if not all_models:
        st.info("No models yet.")
        return

    for m in all_models:
        with st.expander(f"Model: {m['name']}", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                n_name = st.text_input("Display Name", m["name"], key=f"mn_{m['id']}")
                n_model_name = st.text_input("Model Name", m.get("model_name",""), key=f"mmn_{m['id']}")
                n_url = st.text_input("API URL", m["api_url"], key=f"mu_{m['id']}")
            with col2:
                n_key = st.text_input("API Key", m.get("api_key") or "", type="password", key=f"mk_{m['id']}")
                n_prompt = st.text_area("System Prompt", m.get("system_prompt") or "", key=f"mp_{m['id']}")

            # RAG link
            if indexed_docs:
                cur_links = database.get_rag_link_ids_for_model(m["id"])
                linked = st.multiselect(
                    "Linked Knowledge Base Files",
                    list(doc_map.keys()),
                    default=[d for d in cur_links if d in doc_map],
                    format_func=lambda i: doc_map.get(i, str(i)),
                    key=f"mrag_{m['id']}"
                )
            else:
                linked = []
                st.caption("No indexed KB files yet. Index files in Knowledge Base tab.")

            col3, col4 = st.columns(2)
            with col3:
                if st.button("Save", key=f"msave_{m['id']}"):
                    database.update_model(m["id"], n_name, n_model_name, n_url,
                                          n_key or None, n_prompt or None)
                    database.set_model_rag_links(m["id"], linked)
                    st.success("Saved")
                    st.rerun()
            with col4:
                if st.button("Delete", key=f"mdel_{m['id']}", type="primary"):
                    database.delete_model(m["id"])
                    st.rerun()

            # Per-student access
            with st.expander("Individual Student Access", expanded=False):
                all_students = database.get_all_students()
                for s in all_students:
                    access_map = database.get_student_model_access_map(s["id"])
                    cur = access_map.get(m["id"], {})
                    col_a, col_b, col_c = st.columns([1, 2, 1])
                    with col_a:
                        allowed = st.checkbox(
                            s["username"],
                            value=bool(cur.get("allowed", 0)),
                            key=f"sma_{m['id']}_{s['id']}"
                        )
                    with col_b:
                        override = st.text_input(
                            "Override",
                            value=cur.get("override_prompt") or "",
                            key=f"smop_{m['id']}_{s['id']}",
                            label_visibility="collapsed",
                            placeholder="Override prompt"
                        )
                    with col_c:
                        if st.button("Set", key=f"smaset_{m['id']}_{s['id']}"):
                            database.set_student_model_access(s["id"], m["id"], allowed, override or None)
                            st.success("Set")


def _teacher_kb(user):
    st.header("Knowledge Base")
    col_left, col_right = st.columns([1, 3])

    with col_left:
        st.markdown("**Folders**")
        folders = database.get_folders(parent_id=None)
        if st.button("+ New Folder"):
            st.session_state.kb_new_folder = True

        if st.session_state.get("kb_new_folder"):
            with st.form("new_folder_form"):
                fname = st.text_input("Folder Name")
                if st.form_submit_button("Create"):
                    if fname:
                        database.create_folder(fname, created_by=user["id"])
                        st.session_state.kb_new_folder = False
                        st.rerun()

        # Root / unfoldered
        if st.button("All Files (root)", key="kb_root",
                     type="primary" if st.session_state.get("kb_folder_id") is None else "secondary"):
            st.session_state.kb_folder_id = None
            st.rerun()

        for folder in folders:
            col_f1, col_f2 = st.columns([3, 1])
            with col_f1:
                if st.button(folder["name"], key=f"kbf_{folder['id']}",
                             type="primary" if st.session_state.get("kb_folder_id") == folder["id"] else "secondary"):
                    st.session_state.kb_folder_id = folder["id"]
                    st.rerun()
            with col_f2:
                if st.button("Del", key=f"kbfdel_{folder['id']}"):
                    database.delete_folder(folder["id"])
                    if st.session_state.get("kb_folder_id") == folder["id"]:
                        st.session_state.kb_folder_id = None
                    st.rerun()

    with col_right:
        current_folder_id = st.session_state.get("kb_folder_id")
        folder_label = "All Files" if current_folder_id is None else next(
            (f["name"] for f in folders if f["id"] == current_folder_id), "Folder"
        )
        st.markdown(f"**{folder_label}**")

        # Upload
        with st.expander("Upload Document", expanded=False):
            up_file = st.file_uploader("Select file (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"],
                                       key="kb_upload")
            up_subj = st.text_input("Subject tag (optional)", key="kb_subj")
            up_folder = current_folder_id
            if up_file and st.button("Upload"):
                docs_dir = os.path.join(DATA_DIR, "documents")
                os.makedirs(docs_dir, exist_ok=True)
                file_path = os.path.join(docs_dir, f"{uuid.uuid4()}_{up_file.name}")
                with open(file_path, "wb") as f:
                    f.write(up_file.read())
                database.save_document(
                    up_file.name, file_path, up_file.name.split(".")[-1].lower(),
                    subject=up_subj or None,
                    folder_id=up_folder,
                    uploaded_by=user["id"]
                )
                st.success(f"Uploaded: {up_file.name}")
                st.rerun()

        # File list
        docs = database.get_documents(folder_id=current_folder_id)
        if not docs:
            st.info("No files here.")
        else:
            for doc in docs:
                with st.expander(f"{doc['name']} [{doc['index_status']}]"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if doc["index_status"] != "indexed":
                            if st.button("Index", key=f"idx_{doc['id']}"):
                                if doc.get("file_path") and os.path.exists(doc["file_path"]):
                                    prog = st.progress(0, text="Indexing...")
                                    try:
                                        prog.progress(30, text="Extracting pages...")
                                        index = rag_utils.build_page_index(
                                            doc["file_path"], doc["file_type"]
                                        )
                                        prog.progress(70, text="Saving index...")
                                        index_path = rag_utils.save_index(doc["id"], index)
                                        database.update_document_index(doc["id"], index_path, "indexed")
                                        prog.progress(100, text="Done!")
                                        st.success("Indexed")
                                        st.rerun()
                                    except Exception as e:
                                        prog.empty()
                                        st.error(f"Index error: {e}")
                                        database.update_document_index(doc["id"], None, "failed")
                                else:
                                    st.error("File not found on disk.")
                        else:
                            st.success("Indexed")
                    with col2:
                        # Move to folder
                        all_folders = database.get_all_folders()
                        folder_options = {"(root)": None}
                        folder_options.update({f["name"]: f["id"] for f in all_folders})
                        sel_folder = st.selectbox(
                            "Move to",
                            list(folder_options.keys()),
                            key=f"movef_{doc['id']}"
                        )
                        if st.button("Move", key=f"movebtn_{doc['id']}"):
                            database.move_document_to_folder(doc["id"], folder_options[sel_folder])
                            st.rerun()
                    with col3:
                        if st.button("Delete", key=f"deldoc_{doc['id']}", type="primary"):
                            if doc.get("file_path") and os.path.exists(doc["file_path"]):
                                os.remove(doc["file_path"])
                            idx_path = (doc.get("index_path") or "")
                            if idx_path and os.path.exists(idx_path):
                                os.remove(idx_path)
                            database.delete_document(doc["id"])
                            st.rerun()

        # Question generation
        with st.expander("Generate Practice Questions from Document"):
            all_indexed = database.get_documents()
            indexed = [d for d in all_indexed if d["index_status"] == "indexed"]
            all_models = database.get_models()
            all_students = database.get_all_students()

            if not indexed:
                st.info("Index documents first.")
            elif not all_models:
                st.info("Add a model first.")
            else:
                q_doc = st.selectbox("Document", indexed, format_func=lambda d: d["name"])
                q_types = st.multiselect("Question types",
                                         ["Multiple Choice", "Fill-in-the-blank", "Short Answer", "True/False"],
                                         default=["Multiple Choice"])
                q_model = st.selectbox("Model to use", all_models, format_func=lambda m: m["name"])
                q_students = st.multiselect("Assign to students (optional)",
                                            [s["username"] for s in all_students])
                if st.button("Generate Questions"):
                    if q_doc and q_types and q_model:
                        idx_path = q_doc.get("index_path")
                        context = ""
                        if idx_path and os.path.exists(idx_path):
                            context = rag_utils.retrieve_context(idx_path, "overview of document", top_k=5)
                        type_str = ", ".join(q_types)
                        prompt = (
                            f"Generate 3 practice questions for EACH type: {type_str}.\n"
                            f"Label each, include answer. Format cleanly.\n\nDocument:\n{context}"
                        )
                        with st.spinner("Generating..."):
                            result = call_model_api_single(q_model, prompt)
                        st.markdown(result)
                        assigned_ids = [s["id"] for s in all_students if s["username"] in q_students]
                        if not assigned_ids:
                            assigned_ids = [None]
                        for aid in assigned_ids:
                            database.save_generated_question(
                                q_doc["id"], ", ".join(q_types), result,
                                assigned_to=aid
                            )
                        st.success("Saved to database.")


# ===========================================================================
# STUDENT WORKSPACE
# ===========================================================================

def render_student_workspace(user):
    username = user["username"]
    allowed_models = database.get_allowed_models_for_student(user["id"])

    with st.sidebar:
        st.subheader(user["name"])

        if allowed_models:
            model_options = {m["id"]: m["name"] for m in allowed_models}
            if "student_model_id" not in st.session_state:
                st.session_state.student_model_id = allowed_models[0]["id"]
            selected_model_id = st.selectbox(
                "Select Model",
                list(model_options.keys()),
                format_func=lambda i: model_options[i],
                index=list(model_options.keys()).index(st.session_state.student_model_id)
                      if st.session_state.student_model_id in model_options else 0,
                key="sidebar_model_select"
            )
            st.session_state.student_model_id = selected_model_id
        else:
            st.warning("No models assigned. Ask your teacher.")
            selected_model_id = None

        if st.button("New Chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.session_id = str(uuid.uuid4())
            st.rerun()

        st.markdown("**Chat History**")
        history_dir = os.path.join(get_user_dir(username), "history")
        os.makedirs(history_dir, exist_ok=True)
        files = sorted(glob.glob(os.path.join(history_dir, "*.json")),
                       key=os.path.getmtime, reverse=True)
        for fpath in files:
            sid = os.path.basename(fpath).replace(".json", "")
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                title = meta.get("title", "Untitled")
            except Exception:
                title = "Corrupted"
            c1, c2 = st.columns([4, 1])
            with c1:
                btn_title = title if len(title) < 22 else title[:19] + "..."
                if st.button(btn_title, key=f"open_{sid}", use_container_width=True, help=title):
                    msgs, _ = load_session(username, sid)
                    st.session_state.messages = msgs
                    st.session_state.session_id = sid
                    st.rerun()
            with c2:
                if st.button("Del", key=f"hdel_{sid}"):
                    delete_session(username, sid)
                    if st.session_state.get("session_id") == sid:
                        st.session_state.messages = []
                        st.session_state.session_id = str(uuid.uuid4())
                    st.rerun()

        st.divider()
        if st.button("Logout", use_container_width=True):
            st.session_state.user = None
            st.rerun()

    # Determine active model object
    current_model = None
    if selected_model_id:
        for m in allowed_models:
            if m["id"] == selected_model_id:
                current_model = m
                break

    tab_chat, tab_practice, tab_notebook = st.tabs(["Chat", "Practice", "Notebook"])

    # ---- CHAT TAB ----
    with tab_chat:
        if "session_id" not in st.session_state:
            st.session_state.session_id = str(uuid.uuid4())
        if "messages" not in st.session_state:
            st.session_state.messages = []

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if "image_path" in msg:
                    img_p = get_image_path(username, msg["image_path"])
                    if os.path.exists(img_p):
                        st.image(img_p, width=300)

        uploaded_file = st.file_uploader(
            "Attach image (optional)", type=["jpg", "png", "jpeg"],
            label_visibility="visible", key="chat_upload"
        )
        user_input = st.chat_input("Ask your AI Tutor...")

        if user_input:
            with st.chat_message("user"):
                st.markdown(user_input)
                if uploaded_file:
                    st.image(uploaded_file, width=300)

            msg_data = {"role": "user", "content": user_input}
            if uploaded_file:
                msg_data["image_path"] = save_image(username, uploaded_file.getvalue())
            st.session_state.messages.append(msg_data)

            response_text = ""
            if current_model:
                rag_inject = ""
                rag_docs = database.get_rag_docs_for_model(current_model["id"])
                if rag_docs:
                    for rdoc in rag_docs:
                        if rdoc.get("index_path") and os.path.exists(rdoc["index_path"]):
                            snippet = rag_utils.retrieve_context(rdoc["index_path"], user_input)
                            if snippet:
                                rag_inject += snippet + "\n\n"
                chat_messages = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages
                ]
                if rag_inject:
                    chat_messages[-1]["content"] = (
                        f"[Relevant document context:]\n{rag_inject.strip()}\n\n"
                        f"[Student question:] {user_input}"
                    )
                response_text = call_model_api(current_model, chat_messages)
            else:
                response_text = "[No model assigned. Ask your teacher to grant access.]"

            with st.chat_message("assistant"):
                st.markdown(response_text)
            st.session_state.messages.append({"role": "assistant", "content": response_text})
            save_session(username, st.session_state.session_id, st.session_state.messages)
            st.session_state.last_qa = (user_input, response_text)
            st.rerun()

        if "last_qa" in st.session_state and current_model:
            q, a = st.session_state.last_qa
            if st.button("Add Last Q&A to Notebook"):
                with st.spinner("Summarizing..."):
                    summary = call_model_api_single(
                        current_model,
                        f"Summarize the key concept or mistake in 1-2 sentences.\nQ: {q}\nA: {a}"
                    )
                    add_to_notebook(username, q, a, summary)
                st.success("Added to Notebook!")
                del st.session_state.last_qa

    # ---- PRACTICE TAB ----
    with tab_practice:
        st.header("Practice Questions")

        assigned_qs = database.get_questions_for_student(user["id"])
        if assigned_qs:
            st.subheader("Assigned by Teacher")
            for q in assigned_qs:
                with st.expander(f"[{q['question_type']}] {q.get('doc_name', '')}"):
                    st.markdown(q["question"])
            st.divider()

        st.subheader("Generate from My Notebook")
        notebook = load_notebook(username)
        if not notebook:
            st.info("Your notebook is empty. Add entries from the Chat tab first.")
        else:
            notebook.sort(key=lambda x: x["timestamp"], reverse=True)
            options = {e["id"]: f"{e['title']} ({e['timestamp'][:10]})" for e in notebook}
            selected_ids = st.multiselect(
                "Select entries:",
                list(options.keys()),
                format_func=lambda x: options[x]
            )
            q_types = st.multiselect(
                "Question types",
                ["Multiple Choice", "Fill-in-the-blank", "Short Answer", "True/False"],
                default=["Multiple Choice", "Short Answer"]
            )
            if st.button("Generate Questions"):
                if not selected_ids:
                    st.warning("Select at least one entry.")
                elif not q_types:
                    st.warning("Select at least one question type.")
                elif not current_model:
                    st.warning("No model available.")
                else:
                    selected_entries = [n for n in notebook if n["id"] in selected_ids]
                    context_text = "".join(
                        f"\n---\nTopic: {e['title']}\nKey Point: {e.get('summary','')}\n"
                        f"Original Q: {e['question']}\n"
                        for e in selected_entries
                    )
                    type_str = ", ".join(q_types)
                    prompt = (
                        f"Generate 3 practice questions for EACH type: {type_str}.\n"
                        f"Number each. Label type. Include answer.\n"
                        f"Multiple Choice: 4 options (A-D), mark correct.\n"
                        f"Fill-in-the-blank: use ___, provide answer.\n"
                        f"True/False: state verdict.\n\nNotebook entries:\n{context_text}"
                    )
                    with st.spinner("Generating..."):
                        result = call_model_api_single(current_model, prompt)
                    st.markdown(result)

    # ---- NOTEBOOK TAB ----
    with tab_notebook:
        st.header("Your Notebook")
        notebook = load_notebook(username)
        if not notebook:
            st.info("No entries yet. Add from Chat tab.")
        else:
            notebook.sort(key=lambda x: x["timestamp"], reverse=True)
            for entry in notebook:
                with st.expander(f"{entry['title']} - {entry['timestamp'][:16]}"):
                    new_title = st.text_input("Title", value=entry["title"],
                                              key=f"nbtitle_{entry['id']}")
                    if new_title != entry["title"]:
                        update_notebook_entry_title(username, entry["id"], new_title)
                        st.rerun()
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Question**")
                        st.info(entry["question"])
                    with col2:
                        st.markdown("**Answer**")
                        st.info(entry["answer"])
                    if entry.get("summary"):
                        st.markdown("**Key Learning**")
                        st.warning(entry["summary"])
                    if st.button("Delete Entry", key=f"nbdel_{entry['id']}"):
                        delete_notebook_entry(username, entry["id"])
                        st.rerun()

        if st.button("Refresh"):
            st.rerun()


# ===========================================================================
# MAIN ROUTER
# ===========================================================================

if st.session_state.user is None:
    render_login()
else:
    user = st.session_state.user
    role = user.get("role")
    if role == "admin":
        render_admin_dashboard(user)
    elif role == "teacher":
        render_teacher_dashboard(user)
    else:
        render_student_workspace(user)
