import streamlit as st
import json
import os
import glob
import uuid
import socket
import base64
import mimetypes
from datetime import datetime
import database
import rag_utils
from openai import OpenAI

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = "data"
SYSTEM_SETTINGS_FILE = os.path.join(DATA_DIR, "system", "settings.json")

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]; s.close(); return ip
    except Exception: return "127.0.0.1"

SERVER_IP = get_local_ip()
DEFAULT_OLLAMA_URL = f"http://{SERVER_IP}:11434/v1"
DEFAULT_API_URL = f"http://{SERVER_IP}:3001/api/v1"

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
    client = OpenAI(api_key=model.get("api_key") or "not-required", base_url=model["api_url"])
    system_parts = []
    if model.get("system_prompt"): system_parts.append(model["system_prompt"])
    if model.get("override_prompt"): system_parts.append(model["override_prompt"])
    full_msgs = []
    if system_parts: full_msgs.append({"role": "system", "content": "\n\n".join(system_parts)})
    full_msgs.extend(messages)
    try:
        resp = client.chat.completions.create(model=model.get("model_name") or "gpt-3.5-turbo", messages=full_msgs)
        return resp.choices[0].message.content
    except Exception as e:
        return f"[Model Error]: {e}"

def call_model_api_single(model, prompt):
    return call_model_api(model, [{"role": "user", "content": prompt}])

# ---------------------------------------------------------------------------
# Student data helpers
# ---------------------------------------------------------------------------

def get_user_dir(username): return os.path.join(DATA_DIR, username)

def save_session(username, session_id, messages):
    if not messages: return
    title = "New Chat"
    for m in messages:
        if m["role"] == "user":
            title = m["content"][:30] + ("..." if len(m["content"]) > 30 else "")
            break
    history_dir = os.path.join(get_user_dir(username), "history")
    os.makedirs(history_dir, exist_ok=True)
    to_save = [{k: v for k, v in m.items() if k != "image_data"} for m in messages]
    with open(os.path.join(history_dir, f"{session_id}.json"), "w", encoding="utf-8") as f:
        json.dump({"id": session_id, "title": title, "updated_at": datetime.now().isoformat(),
                   "messages": to_save}, f, ensure_ascii=False, indent=2)

def load_session(username, session_id):
    path = os.path.join(get_user_dir(username), "history", f"{session_id}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f); return d.get("messages", []), d.get("title", "New Chat")
    except Exception: return [], "New Chat"

def delete_session(username, session_id):
    path = os.path.join(get_user_dir(username), "history", f"{session_id}.json")
    if os.path.exists(path): os.remove(path)

def save_image(username, image_bytes):
    images_dir = os.path.join(get_user_dir(username), "images")
    os.makedirs(images_dir, exist_ok=True)
    filename = f"{uuid.uuid4()}.png"
    with open(os.path.join(images_dir, filename), "wb") as f: f.write(image_bytes)
    return filename

def get_image_path(username, filename):
    return os.path.join(get_user_dir(username), "images", filename)

def get_notebook_path(username): return os.path.join(get_user_dir(username), "notebook.json")

def load_notebook(username):
    path = get_notebook_path(username)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return []

def save_notebook(username, data):
    path = get_notebook_path(username)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

def add_to_notebook(username, question, answer, summary=None):
    nb = load_notebook(username)
    nb.append({"id": str(uuid.uuid4()), "timestamp": datetime.now().isoformat(),
               "title": (summary or question)[:50], "question": question,
               "answer": answer, "summary": summary})
    save_notebook(username, nb)

def delete_notebook_entry(username, entry_id):
    save_notebook(username, [e for e in load_notebook(username) if e["id"] != entry_id])

def update_notebook_entry_title(username, entry_id, new_title):
    nb = load_notebook(username)
    for e in nb:
        if e["id"] == entry_id: e["title"] = new_title
    save_notebook(username, nb)

# ---------------------------------------------------------------------------
# CSS + startup
# ---------------------------------------------------------------------------

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }

/* ── Sidebar ───────────────────────────────────────── */
section[data-testid="stSidebar"] { background: #f8faff !important; border-right: 1px solid #e2e8f0; }
section[data-testid="stSidebar"] .block-container { padding: 1rem 0.75rem; }
section[data-testid="stSidebar"] .stRadio > label { display:none; }
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] { display:flex; flex-direction:column; gap:2px; }
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
    padding: 0.55rem 0.9rem; border-radius: 8px; font-size: 0.875rem;
    font-weight: 500; cursor: pointer; width:100%; transition: background 0.15s;
    color: #374151;
}
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:hover { background: #ede9fe; }
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:has(input:checked) {
    background: #ede9fe; color: #5b21b6; font-weight:600;
}
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] input { display:none; }

/* ── Main area ──────────────────────────────────────── */
.main .block-container { padding-top: 1.25rem; padding-bottom: 2rem; max-width: 1200px; }

/* ── Cards ──────────────────────────────────────────── */
.stat-card {
    background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
    padding: 1.25rem 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,.07);
    display:flex; flex-direction:column; gap:4px;
}
.stat-card .stat-val { font-size: 2rem; font-weight: 700; color: #1e1b4b; line-height:1; }
.stat-card .stat-lbl { font-size: 0.8rem; font-weight: 500; color: #6b7280; text-transform:uppercase; letter-spacing:.05em; }
.stat-card .stat-sub { font-size: 0.78rem; color: #9ca3af; }

/* ── Badges ─────────────────────────────────────────── */
.badge {
    display:inline-block; padding:2px 10px; border-radius:9999px;
    font-size: 0.7rem; font-weight:600; text-transform:uppercase; letter-spacing:.04em;
}
.badge-admin    { background:#ede9fe; color:#6d28d9; }
.badge-teacher  { background:#dbeafe; color:#1d4ed8; }
.badge-student  { background:#dcfce7; color:#166534; }
.badge-active   { background:#dcfce7; color:#166534; }
.badge-banned   { background:#fee2e2; color:#991b1b; }
.badge-indexed  { background:#dcfce7; color:#166534; }
.badge-pending  { background:#fef9c3; color:#854d0e; }
.badge-failed   { background:#fee2e2; color:#991b1b; }

/* ── User table row ────────────────────────────────── */
.user-row {
    background:#fff; border:1px solid #f1f5f9; border-radius:8px;
    padding: 0.5rem 0.75rem; margin-bottom:4px; transition: box-shadow 0.15s;
}
.user-row:hover { box-shadow: 0 2px 8px rgba(0,0,0,.08); }

/* ── Buttons ────────────────────────────────────────── */
.stButton > button { border-radius: 8px !important; font-weight: 500 !important; font-size: 0.875rem !important; }
.stButton > button[kind="primary"] { background: #6366f1 !important; border-color: #6366f1 !important; }
.stButton > button[kind="primary"]:hover { background: #4f46e5 !important; border-color: #4f46e5 !important; }

/* ── Tabs ───────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 2px solid #e5e7eb; }
.stTabs [data-baseweb="tab"] { font-weight: 500; border-radius: 6px 6px 0 0; padding: 0.5rem 1rem; }

/* ── Inputs ─────────────────────────────────────────── */
.stTextInput > div > div > input, .stTextArea textarea {
    border-radius: 8px !important; border-color: #d1d5db !important;
}

/* ── Expanders ──────────────────────────────────────── */
details { border: 1px solid #e5e7eb !important; border-radius: 10px !important; margin-bottom: 8px !important; }
details summary { padding: 0.75rem 1rem !important; font-weight: 500 !important; }

/* ── Hide Streamlit chrome ─────────────────────────── */
#MainMenu, footer { visibility: hidden; }
.stDeployButton { display: none; }

/* ── Login page ─────────────────────────────────────── */
.login-wrap { max-width: 440px; margin: 3rem auto; }
</style>
"""

# ---------------------------------------------------------------------------
# DB init & page config
# ---------------------------------------------------------------------------

database.init_db()
database.cleanup_zombies()
sys_settings = load_system_settings()

st.set_page_config(
    page_title=sys_settings.get("school_name", "AI Tutor Platform"),
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)
st.markdown(CSS, unsafe_allow_html=True)

# Background image (file upload takes priority over URL)
_bg_path = database.get_system_image_path("bg")
_bg_url = sys_settings.get("background_url", "")
if _bg_path:
    _b64 = database.get_system_image_b64("bg")
    st.markdown(f"""<style>.stApp{{background-image:url("{_b64}");background-size:cover;background-attachment:fixed;}}</style>""",
                unsafe_allow_html=True)
elif _bg_url:
    st.markdown(f"""<style>.stApp{{background-image:url("{_bg_url}");background-size:cover;background-attachment:fixed;}}</style>""",
                unsafe_allow_html=True)

if "user" not in st.session_state:
    st.session_state.user = None

# ---------------------------------------------------------------------------
# Helper: HTML badges, stat cards
# ---------------------------------------------------------------------------

def badge(text, cls=None):
    if cls is None: cls = text.lower().replace(" ", "-")
    return f'<span class="badge badge-{cls}">{text}</span>'

def stat_card(label, value, sub=""):
    return f"""<div class="stat-card"><div class="stat-lbl">{label}</div><div class="stat-val">{value}</div><div class="stat-sub">{sub}</div></div>"""

# ---------------------------------------------------------------------------
# Dialog Definitions
# ---------------------------------------------------------------------------

@st.dialog("Add User")
def dialog_add_user():
    with st.form("dlg_add_user", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nu = st.text_input("Username *")
            nn = st.text_input("Full Name")
        with c2:
            ne = st.text_input("Email")
            np_ = st.text_input("Password *", type="password")
        nr = st.selectbox("Role", ["student", "teacher", "admin"])
        sub = st.form_submit_button("Create User", use_container_width=True, type="primary")
    if sub:
        if not nu or not np_:
            st.error("Username and password are required.")
        else:
            ok, msg = database.create_user(nu.strip(), np_, nr, nn.strip() or nu.strip(),
                                           email=ne.strip() or None)
            if ok:
                st.success(f"User **{nu}** created!")
                st.rerun()
            else:
                st.error(msg)

    st.divider()
    st.markdown("**Or import students from CSV**")
    st.caption("Format: `username,email,name,password`")
    csv_f = st.file_uploader("CSV file", type=["csv"], key="dlg_csv")
    if csv_f:
        if st.button("Import CSV", use_container_width=True):
            text = csv_f.read().decode("utf-8")
            ok_count, errors = database.import_students_from_csv(text)
            st.success(f"Imported {ok_count} student(s).")
            for e in errors: st.warning(e)
            if ok_count: st.rerun()


@st.dialog("Edit User")
def dialog_edit_user():
    uid = st.session_state.get("_edit_uid")
    if not uid:
        st.error("No user selected."); return
    u = database.get_user_by_id(uid)
    if not u:
        st.error("User not found."); return
    with st.form("dlg_edit_user"):
        c1, c2 = st.columns(2)
        with c1:
            n_name = st.text_input("Full Name", u["name"])
            n_uname = st.text_input("Username", u["username"])
        with c2:
            n_email = st.text_input("Email", u.get("email") or "")
            n_pwd = st.text_input("New Password", type="password", placeholder="Leave blank to keep")
        n_role = st.selectbox("Role", ["student","teacher","admin"],
                              index=["student","teacher","admin"].index(u["role"]))
        cc1, cc2 = st.columns(2)
        with cc1: save = st.form_submit_button("Save Changes", use_container_width=True, type="primary")
        with cc2: cancel = st.form_submit_button("Cancel", use_container_width=True)
    if save:
        ok, msg = database.admin_update_user(uid, n_name, n_uname,
                                             email=n_email or None,
                                             password=n_pwd or None,
                                             role=n_role)
        if ok:
            st.success("Updated!")
            st.session_state.pop("_edit_uid", None)
            st.rerun()
        else:
            st.error(msg)
    if cancel:
        st.session_state.pop("_edit_uid", None)
        st.rerun()


@st.dialog("Confirm Delete")
def dialog_confirm_delete():
    uid = st.session_state.get("_del_uid")
    if not uid: return
    u = database.get_user_by_id(uid)
    if not u: st.session_state.pop("_del_uid", None); st.rerun(); return
    st.warning(f"Delete **{u['username']}** ({u['role']})? This cannot be undone.")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Yes, Delete", use_container_width=True, type="primary"):
            database.delete_user(uid)
            st.session_state.pop("_del_uid", None)
            st.success("Deleted.")
            st.rerun()
    with c2:
        if st.button("Cancel", use_container_width=True):
            st.session_state.pop("_del_uid", None)
            st.rerun()


@st.dialog("Create Class")
def dialog_create_class():
    tid = st.session_state.get("_create_class_tid")
    with st.form("dlg_create_class"):
        c_name = st.text_input("Class Name *")
        c_subj = st.text_input("Subject")
        sub = st.form_submit_button("Create", use_container_width=True, type="primary")
    if sub:
        if not c_name:
            st.error("Class name required.")
        else:
            database.create_class(c_name.strip(), tid, c_subj.strip() or None)
            st.session_state.pop("_create_class_tid", None)
            st.success("Class created!")
            st.rerun()


@st.dialog("Settings")
def dialog_settings():
    _render_settings_form(st.session_state.get("user"))


# ---------------------------------------------------------------------------
# Shared settings form
# ---------------------------------------------------------------------------

def _render_settings_form(user):
    if not user: return
    st.markdown("#### Change Password")
    with st.form("settings_pwd_form"):
        cur_pwd = st.text_input("Current Password", type="password")
        new_pwd = st.text_input("New Password", type="password")
        new_pwd2 = st.text_input("Confirm New Password", type="password")
        sub_pwd = st.form_submit_button("Update Password", use_container_width=True, type="primary")
    if sub_pwd:
        if not cur_pwd or not new_pwd:
            st.error("All fields required.")
        elif new_pwd != new_pwd2:
            st.error("New passwords do not match.")
        elif database.hash_password(cur_pwd) != user["password"]:
            st.error("Current password is incorrect.")
        else:
            ok, msg = database.update_user_profile(user["id"], new_password=new_pwd)
            if ok:
                st.success("Password updated!")
                # refresh session user
                st.session_state.user = database.get_user_by_id(user["id"])
            else:
                st.error(msg)

    st.markdown("#### Edit Profile")
    with st.form("settings_profile_form"):
        n_name = st.text_input("Display Name", user.get("name", ""))
        n_email = st.text_input("Email", user.get("email") or "")
        sub_p = st.form_submit_button("Update Profile", use_container_width=True, type="primary")
    if sub_p:
        ok, msg = database.update_user_profile(user["id"], new_name=n_name or None,
                                                new_email=n_email or None)
        if ok:
            st.success("Profile updated!")
            st.session_state.user = database.get_user_by_id(user["id"])
        else:
            st.error(msg)


# ===========================================================================
# LOGIN
# ===========================================================================

def render_login():
    school = sys_settings.get("school_name", "AI Tutor Platform")
    st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
    # Logo
    _logo = database.get_system_image_path("logo")
    if _logo:
        st.image(_logo, width=80)
    elif sys_settings.get("logo_url"):
        st.image(sys_settings["logo_url"], width=80)
    st.markdown(f"## {school}")
    tab_login, tab_register = st.tabs(["Sign In", "Register"])
    with tab_login:
        with st.form("login_form"):
            login_id = st.text_input("Username or Email")
            pwd = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")
        if submitted:
            user = database.verify_user(login_id, pwd)
            if user:
                if user.get("account_status") == "banned":
                    st.error("Your account has been suspended. Contact admin.")
                else:
                    st.session_state.user = user
                    st.rerun()
            else:
                st.error("Incorrect username/email or password.")
        st.caption("Forgot password? Contact your teacher or admin.")
    with tab_register:
        st.caption("Create a student account.")
        with st.form("reg_form"):
            c1, c2 = st.columns(2)
            with c1:
                r_user = st.text_input("Username *")
                r_name = st.text_input("Full Name")
            with c2:
                r_email = st.text_input("Email")
                r_pwd = st.text_input("Password *", type="password")
            r_pwd2 = st.text_input("Confirm Password", type="password")
            r_sub = st.form_submit_button("Create Account", use_container_width=True, type="primary")
        if r_sub:
            if not r_user or not r_pwd:
                st.error("Username and password required.")
            elif r_pwd != r_pwd2:
                st.error("Passwords do not match.")
            else:
                ok, msg = database.create_user(r_user.strip(), r_pwd, "student",
                                               r_name.strip() or r_user.strip(),
                                               email=r_email.strip() or None)
                if ok: st.success("Account created! You can now sign in.")
                else: st.error(f"Registration failed: {msg}")
    st.markdown("</div>", unsafe_allow_html=True)


# ===========================================================================
# ADMIN DASHBOARD
# ===========================================================================

def render_admin_dashboard(user):
    with st.sidebar:
        _logo = database.get_system_image_path("logo")
        if _logo: st.image(_logo, width=60)
        st.markdown(f"**{user['name']}**")
        st.caption("Administrator")
        st.divider()
        nav = st.radio("nav", [
            "👥  Users",
            "🏫  Classes",
            "🤝  Teacher-Students",
            "⚙️  System Settings",
        ], label_visibility="collapsed")
        st.divider()
        if st.button("Logout", use_container_width=True):
            st.session_state.user = None; st.rerun()

    if nav == "👥  Users":       _admin_users(user)
    elif nav == "🏫  Classes":   _admin_classes()
    elif nav == "🤝  Teacher-Students": _admin_teacher_students()
    elif nav == "⚙️  System Settings":  _admin_system_settings()


# ── Admin: User Management ──────────────────────────────────────────────────

def _admin_users(current_admin):
    st.markdown("## User Management")

    all_users = database.get_all_users()

    # Toolbar
    col_srch, col_filt, col_add = st.columns([3, 1.5, 1])
    with col_srch:
        search = st.text_input("", placeholder="Search name, username, email…",
                               key="user_search", label_visibility="collapsed")
    with col_filt:
        role_f = st.selectbox("", ["all","admin","teacher","student"],
                              label_visibility="collapsed", key="user_role_filter")
    with col_add:
        if st.button("＋ Add User", use_container_width=True, type="primary"):
            dialog_add_user()

    # Filter
    filtered = all_users
    if role_f != "all":
        filtered = [u for u in filtered if u["role"] == role_f]
    if search:
        q = search.lower()
        filtered = [u for u in filtered if any(q in (u.get(k) or "").lower()
                                                for k in ["username","name","email","role"])]

    # Totals
    st.caption(f"Showing **{len(filtered)}** of **{len(all_users)}** users")

    # Pagination
    PAGE_SIZE = 50
    total_pages = max(1, (len(filtered) + PAGE_SIZE - 1) // PAGE_SIZE)
    if "user_page" not in st.session_state or st.session_state.get("_user_search_last") != search:
        st.session_state.user_page = 0
        st.session_state["_user_search_last"] = search
    page = min(st.session_state.user_page, total_pages - 1)
    page_users = filtered[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    # Table header
    h0, h1, h2, h3, h4, h_act = st.columns([3, 2.5, 1.2, 1.2, 1.2, 2])
    for col, hdr in zip([h0,h1,h2,h3,h4,h_act], ["Name / Username","Email","Role","Status","Joined","Actions"]):
        col.markdown(f"<small><b style='color:#6b7280;text-transform:uppercase;letter-spacing:.05em'>{hdr}</b></small>",
                     unsafe_allow_html=True)
    st.markdown("<hr style='margin:4px 0 8px;border-color:#e5e7eb'>", unsafe_allow_html=True)

    for u in page_users:
        c0, c1, c2, c3, c4, c_act = st.columns([3, 2.5, 1.2, 1.2, 1.2, 2])
        with c0:
            st.markdown(f"**{u['name']}**")
            st.caption(f"@{u['username']}")
        with c1:
            st.caption(u.get("email") or "—")
        with c2:
            st.markdown(badge(u["role"]), unsafe_allow_html=True)
        with c3:
            status = u.get("account_status", "active")
            st.markdown(badge(status), unsafe_allow_html=True)
        with c4:
            joined = (u.get("created_at") or "")[:10]
            st.caption(joined or "—")
        with c_act:
            ba, bb, bc = st.columns(3)
            with ba:
                if st.button("✏️", key=f"edit_{u['id']}", help="Edit"):
                    st.session_state["_edit_uid"] = u["id"]
                    dialog_edit_user()
            with bb:
                if status == "active":
                    if st.button("🚫", key=f"ban_{u['id']}", help="Ban"):
                        database.update_user_status(u["id"], "banned"); st.rerun()
                else:
                    if st.button("✅", key=f"unban_{u['id']}", help="Unban"):
                        database.update_user_status(u["id"], "active"); st.rerun()
            with bc:
                if u["id"] != current_admin["id"]:
                    if st.button("🗑️", key=f"del_{u['id']}", help="Delete"):
                        st.session_state["_del_uid"] = u["id"]
                        dialog_confirm_delete()
        st.markdown("<hr style='margin:2px 0;border-color:#f1f5f9'>", unsafe_allow_html=True)

    # Pagination controls
    if total_pages > 1:
        p1, p2, p3 = st.columns([1, 3, 1])
        with p1:
            if st.button("← Prev", disabled=page == 0):
                st.session_state.user_page = max(0, page - 1); st.rerun()
        with p2:
            st.markdown(f"<p style='text-align:center;color:#6b7280'>Page {page+1} / {total_pages}</p>",
                        unsafe_allow_html=True)
        with p3:
            if st.button("Next →", disabled=page >= total_pages - 1):
                st.session_state.user_page = min(total_pages - 1, page + 1); st.rerun()


# ── Admin: Class Management ─────────────────────────────────────────────────

def _admin_classes():
    st.markdown("## Class Management")
    all_classes = database.get_all_classes()
    if not all_classes:
        st.info("No classes yet. Teachers create classes in their dashboard."); return

    for cls in all_classes:
        label = f"**{cls['name']}** — {cls.get('teacher_name','?')} | {cls.get('subject','')}"
        with st.expander(label, expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                n_name = st.text_input("Class Name", cls["name"], key=f"acln_{cls['id']}")
            with c2:
                n_subj = st.text_input("Subject", cls.get("subject") or "", key=f"acls_{cls['id']}")
            students = database.get_students_in_class(cls["id"])
            st.caption("Students: " + (", ".join(s["username"] for s in students) or "(none)"))
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("Save", key=f"aclsave_{cls['id']}", type="primary"):
                    database.update_class(cls["id"], name=n_name, subject=n_subj); st.rerun()
            with col2:
                if st.button("Delete Class", key=f"acldel_{cls['id']}"):
                    database.delete_class(cls["id"]); st.rerun()


# ── Admin: Teacher-Student Relationships ────────────────────────────────────

def _admin_teacher_students():
    st.markdown("## Teacher-Student Relationships")
    teachers = database.get_all_teachers()
    all_students = database.get_all_students()
    if not teachers:
        st.info("No teachers yet."); return

    for teacher in teachers:
        st.markdown(f"### {teacher['name']} (@{teacher['username']})")
        classes = database.get_classes_for_teacher(teacher["id"])
        if not classes:
            st.caption("No classes."); continue
        for cls in classes:
            with st.expander(f"Class: {cls['name']}", expanded=False):
                enrolled = database.get_students_in_class(cls["id"])
                enrolled_ids = {s["id"] for s in enrolled}
                cols = st.columns(3)
                for i, s in enumerate(all_students):
                    with cols[i % 3]:
                        checked = st.checkbox(s["username"], value=s["id"] in enrolled_ids,
                                              key=f"ats_{cls['id']}_{s['id']}")
                        if checked != (s["id"] in enrolled_ids):
                            if checked: database.add_student_to_class(cls["id"], s["id"])
                            else: database.remove_student_from_class(cls["id"], s["id"])
                            st.rerun()


# ── Admin: System Settings ──────────────────────────────────────────────────

def _admin_system_settings():
    st.markdown("## System Settings")
    settings = load_system_settings()

    with st.form("sys_settings_form"):
        school_name = st.text_input("Platform / School Name",
                                    value=settings.get("school_name", "AI Tutor Platform"))
        st.divider()
        st.markdown("**Logo**")
        logo_file = st.file_uploader("Upload logo image", type=["png","jpg","jpeg","svg","webp"],
                                     key="logo_upload")
        logo_url = st.text_input("…or logo URL", value=settings.get("logo_url", ""))
        st.divider()
        st.markdown("**Background Image**")
        bg_file = st.file_uploader("Upload background image", type=["png","jpg","jpeg","webp"],
                                   key="bg_upload")
        bg_url = st.text_input("…or background URL", value=settings.get("background_url", ""))
        saved = st.form_submit_button("Save Settings", use_container_width=True, type="primary")

    if saved:
        settings["school_name"] = school_name
        if logo_file:
            ext = logo_file.name.rsplit(".", 1)[-1].lower()
            database.save_system_image("logo", logo_file.read(), ext)
            settings.pop("logo_url", None)
        elif logo_url:
            settings["logo_url"] = logo_url
        if bg_file:
            ext = bg_file.name.rsplit(".", 1)[-1].lower()
            database.save_system_image("bg", bg_file.read(), ext)
            settings.pop("background_url", None)
        elif bg_url:
            settings["background_url"] = bg_url
        save_system_settings(settings)
        st.success("Settings saved! Refresh to see changes.")

    # Preview
    _logo = database.get_system_image_path("logo")
    if _logo:
        st.markdown("**Current Logo:**"); st.image(_logo, width=100)
    _bg = database.get_system_image_path("bg")
    if _bg:
        st.markdown("**Current Background:**"); st.image(_bg, width=300)


# ===========================================================================
# TEACHER DASHBOARD
# ===========================================================================

def render_teacher_dashboard(user):
    with st.sidebar:
        _logo = database.get_system_image_path("logo")
        if _logo: st.image(_logo, width=60)
        st.markdown(f"**{user['name']}**")
        st.caption("Teacher")
        st.divider()
        nav = st.radio("nav", [
            "📊  Dashboard",
            "🏫  My Classes",
            "🤖  Models",
            "📁  Knowledge Base",
            "⚙️  Settings",
        ], label_visibility="collapsed")
        st.divider()
        if st.button("Logout", use_container_width=True):
            st.session_state.user = None; st.rerun()

    if nav == "📊  Dashboard":      _teacher_analytics(user)
    elif nav == "🏫  My Classes":   _teacher_classes(user)
    elif nav == "🤖  Models":       _teacher_models(user)
    elif nav == "📁  Knowledge Base": _teacher_kb(user)
    elif nav == "⚙️  Settings":     _render_settings_inline(user)


# ── Teacher: Analytics Dashboard ────────────────────────────────────────────

def _teacher_analytics(user):
    try:
        from streamlit_echarts import st_echarts
        has_echarts = True
    except ImportError:
        has_echarts = False

    st.markdown("## Class Analytics Dashboard")

    teacher_id = user["id"]
    classes = database.get_classes_for_teacher(teacher_id)
    all_students = database.get_all_students()

    if not classes:
        st.info("Create a class and enrol students to see analytics here.")
        return

    # Scope selectors
    col_cls, col_stu = st.columns(2)
    with col_cls:
        class_opts = {0: "All My Classes"} | {c["id"]: c["name"] for c in classes}
        sel_class = st.selectbox("Class", list(class_opts.keys()),
                                 format_func=lambda k: class_opts[k], key="ana_class")
    with col_stu:
        if sel_class == 0:
            all_cls_ids = [c["id"] for c in classes]
            enrolled = []
            seen = set()
            for cid in all_cls_ids:
                for s in database.get_students_in_class(cid):
                    if s["id"] not in seen:
                        enrolled.append(s); seen.add(s["id"])
        else:
            enrolled = database.get_students_in_class(sel_class)
        stu_opts = {0: "All Students"} | {s["id"]: s["username"] for s in enrolled}
        sel_stu = st.selectbox("Student", list(stu_opts.keys()),
                               format_func=lambda k: stu_opts[k], key="ana_stu")

    if sel_stu == 0:
        uid_list = [s["id"] for s in enrolled] or None
    else:
        uid_list = [sel_stu]

    # Totals
    totals = database.get_analytics_totals(uid_list)
    act_students = len([s for s in enrolled if s.get("account_status") == "active"])

    sm1, sm2, sm3 = st.columns(3)
    with sm1:
        st.markdown(stat_card("Total Messages", totals["messages"], "student messages logged"),
                    unsafe_allow_html=True)
    with sm2:
        st.markdown(stat_card("Est. Tokens Used", f"{totals['tokens']:,}", "based on word count"),
                    unsafe_allow_html=True)
    with sm3:
        st.markdown(stat_card("Active Students", act_students, f"{len(enrolled)} enrolled"),
                    unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Daily charts
    daily = database.get_analytics_daily_counts(uid_list, days=14)
    dates = [d["day"] for d in daily]
    msgs = [d["messages"] for d in daily]
    tokens = [d["tokens"] or 0 for d in daily]

    if has_echarts and daily:
        ch1, ch2 = st.columns(2)
        with ch1:
            st.caption("Messages per Day (last 14 days)")
            st_echarts({
                "tooltip": {"trigger": "axis"},
                "grid": {"bottom": 60},
                "xAxis": {"type": "category", "data": dates, "axisLabel": {"rotate": 45, "fontSize": 10}},
                "yAxis": {"type": "value", "name": "Messages", "nameTextStyle": {"fontSize": 10}},
                "series": [{"type": "bar", "data": msgs, "itemStyle": {"color": "#6366f1"},
                            "name": "Messages", "barMaxWidth": 40}]
            }, height="260px", key="echarts_daily_msgs")
        with ch2:
            st.caption("Estimated Token Usage per Day")
            st_echarts({
                "tooltip": {"trigger": "axis"},
                "grid": {"bottom": 60},
                "xAxis": {"type": "category", "data": dates, "axisLabel": {"rotate": 45, "fontSize": 10}},
                "yAxis": {"type": "value", "name": "Tokens", "nameTextStyle": {"fontSize": 10}},
                "series": [{"type": "line", "data": tokens, "smooth": True, "name": "Tokens",
                            "itemStyle": {"color": "#a855f7"}, "areaStyle": {"opacity": 0.15}}]
            }, height="260px", key="echarts_daily_tokens")
    elif daily:
        st.line_chart({"Messages": msgs, "Tokens": [t // 10 for t in tokens]})

    # Top words + per-student
    ch3, ch4 = st.columns(2)

    with ch3:
        words = database.get_analytics_top_words(uid_list, limit=15)
        if words and has_echarts:
            st.caption("Top Words in Student Messages")
            wlist = [w for w, _ in reversed(words)]
            clist = [c for _, c in reversed(words)]
            st_echarts({
                "tooltip": {"trigger": "axis"},
                "grid": {"left": 80, "right": 20},
                "xAxis": {"type": "value"},
                "yAxis": {"type": "category", "data": wlist, "axisLabel": {"fontSize": 11}},
                "series": [{"type": "bar", "data": clist, "itemStyle": {"color": "#22c55e"},
                            "barMaxWidth": 30}]
            }, height="340px", key="echarts_words")
        elif words:
            st.bar_chart({w: c for w, c in words})
        else:
            st.info("No message data yet.")

    with ch4:
        if sel_class != 0:
            per_stu = database.get_analytics_per_student(sel_class)
        else:
            per_stu = []
            seen_ids = set()
            for c in classes:
                for row in database.get_analytics_per_student(c["id"]):
                    if row["username"] not in seen_ids:
                        per_stu.append(row); seen_ids.add(row["username"])
            per_stu.sort(key=lambda x: x["messages"], reverse=True)

        if per_stu and has_echarts:
            st.caption("Messages per Student")
            names = [r["username"] for r in per_stu]
            mcounts = [r["messages"] for r in per_stu]
            st_echarts({
                "tooltip": {"trigger": "axis"},
                "grid": {"bottom": 70},
                "xAxis": {"type": "category", "data": names, "axisLabel": {"rotate": 35, "fontSize": 10}},
                "yAxis": {"type": "value", "name": "Messages"},
                "series": [{"type": "bar", "data": mcounts, "itemStyle": {"color": "#f59e0b"},
                            "barMaxWidth": 40}]
            }, height="340px", key="echarts_per_stu")
        elif per_stu:
            st.bar_chart({r["username"]: r["messages"] for r in per_stu})
        else:
            st.info("No students enrolled yet.")

    # Chat history browser
    st.divider()
    st.markdown("### Chat History Browser")

    if sel_stu != 0:
        sessions = database.get_sessions_for_student(sel_stu)
        if not sessions:
            st.info("No chat logs for this student yet.")
        else:
            for sess in sessions[:20]:
                sid = sess["session_id"]
                label = f"Session {sid[:8]}… | {sess['started_at'][:16]} | {sess['msg_count']} msgs"
                with st.expander(label, expanded=False):
                    logs = database.get_chat_logs_for_student(sel_stu, limit=500)
                    sess_logs = [l for l in logs if l["session_id"] == sid]
                    for log in reversed(sess_logs):
                        who = "You" if log["role"] == "user" else "AI"
                        st.markdown(f"**{who}:** {log['content']}")
                    if sess_logs and st.button("Analyse with AI", key=f"ana_sess_{sid}"):
                        models = database.get_models()
                        if not models:
                            st.warning("No models configured.")
                        else:
                            context = "\\n".join(f"{l['role'].upper()}: {l['content']}"
                                                 for l in reversed(sess_logs))
                            with st.spinner("Analysing…"):
                                result = call_model_api_single(models[0], (
                                    "Analyse this student-AI tutoring conversation. "
                                    "Identify: 1) Main topics discussed, 2) Concepts the student struggled with, "
                                    "3) Learning progress, 4) Recommendations for the teacher.\\n\\n" + context[:4000]
                                ))
                            st.markdown(result)
    else:
        if enrolled:
            st.caption("Select a specific student to browse their chat history.")
        else:
            st.info("No students enrolled in the selected scope.")


# ── Teacher: My Classes ─────────────────────────────────────────────────────

def _teacher_classes(user):
    st.markdown("## My Classes")
    teacher_id = user["id"]

    col_h, col_btn = st.columns([5, 1])
    with col_btn:
        if st.button("＋ New Class", type="primary", use_container_width=True):
            st.session_state["_create_class_tid"] = teacher_id
            dialog_create_class()

    classes = database.get_classes_for_teacher(teacher_id)
    all_students = database.get_all_students()
    all_models = database.get_models()

    if not classes:
        st.info("No classes yet. Click **＋ New Class** to get started."); return

    for cls in classes:
        enrolled_count = len(database.get_students_in_class(cls["id"]))
        label = f"**{cls['name']}** | {cls.get('subject','')} | {enrolled_count} student(s)"
        with st.expander(label, expanded=False):
            c1, c2 = st.columns(2)
            with c1: n_name = st.text_input("Class Name", cls["name"], key=f"tcln_{cls['id']}")
            with c2: n_subj = st.text_input("Subject", cls.get("subject") or "", key=f"tcls_{cls['id']}")
            if st.button("Save", key=f"tclsave_{cls['id']}", type="primary"):
                database.update_class(cls["id"], name=n_name, subject=n_subj); st.rerun()

            st.markdown("**Enrolled Students**")
            enrolled = database.get_students_in_class(cls["id"])
            enrolled_ids = {s["id"] for s in enrolled}
            cols3 = st.columns(3)
            for i, s in enumerate(all_students):
                with cols3[i % 3]:
                    checked = st.checkbox(s["username"], value=s["id"] in enrolled_ids,
                                          key=f"tcs_{cls['id']}_{s['id']}")
                    if checked != (s["id"] in enrolled_ids):
                        if checked: database.add_student_to_class(cls["id"], s["id"])
                        else: database.remove_student_from_class(cls["id"], s["id"])
                        st.rerun()

            st.markdown("**Model Access for this Class**")
            cls_access = database.get_class_model_access(cls["id"])
            for m in all_models:
                cur = cls_access.get(m["id"], {})
                ma_col, op_col, sv_col = st.columns([1, 3, 1])
                with ma_col:
                    allowed = st.checkbox(m["name"], value=bool(cur.get("allowed", 0)),
                                          key=f"tma_{cls['id']}_{m['id']}")
                with op_col:
                    override = st.text_input("", value=cur.get("override_prompt") or "",
                                             key=f"tmop_{cls['id']}_{m['id']}",
                                             placeholder="Override prompt (optional)",
                                             label_visibility="collapsed")
                with sv_col:
                    if st.button("Set", key=f"tmaset_{cls['id']}_{m['id']}"):
                        database.set_class_model_access(cls["id"], m["id"], allowed, override or None)
                        st.success("Saved")

            st.divider()
            if st.button("🗑️ Delete Class", key=f"tcldel_{cls['id']}"):
                database.delete_class(cls["id"]); st.rerun()


# ── Teacher: Model Management ────────────────────────────────────────────────

def _teacher_models(user):
    st.markdown("## Model Management")
    all_models = database.get_models()
    all_docs = database.get_documents()
    indexed_docs = [d for d in all_docs if d["index_status"] == "indexed"]
    doc_map = {d["id"]: d["name"] for d in indexed_docs}
    all_students = database.get_all_students()

    with st.expander("＋ Add New Model", expanded=not all_models):
        with st.form("add_model_form"):
            c1, c2 = st.columns(2)
            with c1:
                m_name = st.text_input("Display Name *")
                m_model_name = st.text_input("Model Name (e.g. llama3)")
                m_url = st.text_input("API Base URL", value=DEFAULT_OLLAMA_URL)
            with c2:
                m_key = st.text_input("API Key (if required)", type="password")
                m_prompt = st.text_area("System Prompt (optional)")
            if st.form_submit_button("Add Model", use_container_width=True, type="primary"):
                if m_name and m_url:
                    ok = database.create_model(m_name, m_model_name, m_url,
                                               m_key or None, m_prompt or None,
                                               created_by=user["id"])
                    if ok: st.success("Model added!"); st.rerun()
                    else: st.error("Model name already exists.")
                else: st.warning("Display name and API URL required.")

    if not all_models:
        st.info("No models yet."); return

    for m in all_models:
        with st.expander(f"**{m['name']}** — {m.get('model_name','')} | {m['api_url']}", expanded=False):
            tab_cfg, tab_rag, tab_access = st.tabs(["Configuration", "Knowledge Base Links", "Student Access"])
            with tab_cfg:
                c1, c2 = st.columns(2)
                with c1:
                    n_name = st.text_input("Display Name", m["name"], key=f"mn_{m['id']}")
                    n_mn = st.text_input("Model Name", m.get("model_name",""), key=f"mmn_{m['id']}")
                    n_url = st.text_input("API URL", m["api_url"], key=f"mu_{m['id']}")
                with c2:
                    n_key = st.text_input("API Key", m.get("api_key") or "",
                                          type="password", key=f"mk_{m['id']}")
                    n_prompt = st.text_area("System Prompt", m.get("system_prompt") or "",
                                           key=f"mp_{m['id']}")

                # Test connection
                test_col, save_col, del_col = st.columns([1.5, 1.5, 1])
                with test_col:
                    if st.button("🔌 Test Connection", key=f"test_{m['id']}"):
                        with st.spinner("Testing…"):
                            try:
                                from openai import OpenAI as _OAI
                                _c = _OAI(api_key=n_key or "not-required", base_url=n_url)
                                _c.models.list()
                                st.toast("✅ Connection successful!", icon="✅")
                            except Exception as e:
                                err = str(e)
                                # Try a simple chat completion as fallback
                                try:
                                    from openai import OpenAI as _OAI2
                                    _c2 = _OAI2(api_key=n_key or "not-required", base_url=n_url)
                                    _c2.chat.completions.create(
                                        model=n_mn or "gpt-3.5-turbo",
                                        messages=[{"role":"user","content":"ping"}],
                                        max_tokens=1
                                    )
                                    st.toast("✅ Connection successful (chat ok)!", icon="✅")
                                except Exception as e2:
                                    st.toast(f"❌ Connection failed: {e2}", icon="❌")
                with save_col:
                    if st.button("💾 Save", key=f"msave_{m['id']}", type="primary"):
                        database.update_model(m["id"], n_name, n_mn, n_url,
                                              n_key or None, n_prompt or None)
                        st.success("Saved"); st.rerun()
                with del_col:
                    if st.button("🗑️ Delete", key=f"mdel_{m['id']}"):
                        database.delete_model(m["id"]); st.rerun()

            with tab_rag:
                if indexed_docs:
                    cur_links = database.get_rag_link_ids_for_model(m["id"])
                    linked = st.multiselect(
                        "Select indexed KB files to link to this model:",
                        list(doc_map.keys()),
                        default=[d for d in cur_links if d in doc_map],
                        format_func=lambda i: doc_map.get(i, str(i)),
                        key=f"mrag_{m['id']}"
                    )
                    if st.button("Save RAG Links", key=f"mragsave_{m['id']}", type="primary"):
                        database.set_model_rag_links(m["id"], linked)
                        st.success("Links saved")
                else:
                    st.info("No indexed documents yet. Index files in the Knowledge Base tab.")

            with tab_access:
                for s in all_students:
                    access_map = database.get_student_model_access_map(s["id"])
                    cur = access_map.get(m["id"], {})
                    a_col, op_col, sv_col = st.columns([1, 3, 1])
                    with a_col:
                        allowed = st.checkbox(s["username"], value=bool(cur.get("allowed", 0)),
                                              key=f"sma_{m['id']}_{s['id']}")
                    with op_col:
                        override = st.text_input("", value=cur.get("override_prompt") or "",
                                                 key=f"smop_{m['id']}_{s['id']}",
                                                 placeholder="Override prompt",
                                                 label_visibility="collapsed")
                    with sv_col:
                        if st.button("Set", key=f"smaset_{m['id']}_{s['id']}"):
                            database.set_student_model_access(s["id"], m["id"], allowed, override or None)
                            st.success("Set")


# ── Teacher: Knowledge Base ─────────────────────────────────────────────────

def _teacher_kb(user):
    st.markdown("## Knowledge Base")
    col_left, col_right = st.columns([1, 3])

    with col_left:
        st.markdown("**Folders**")
        folders = database.get_folders(parent_id=None)
        if st.button("＋ New Folder", use_container_width=True):
            st.session_state.kb_new_folder = True

        if st.session_state.get("kb_new_folder"):
            with st.form("new_folder_form"):
                fname = st.text_input("Folder Name")
                if st.form_submit_button("Create"):
                    if fname:
                        database.create_folder(fname, created_by=user["id"])
                        st.session_state.kb_new_folder = False; st.rerun()

        btn_type = "primary" if st.session_state.get("kb_folder_id") is None else "secondary"
        if st.button("📂 All Files", key="kb_root", type=btn_type, use_container_width=True):
            st.session_state.kb_folder_id = None; st.rerun()

        for folder in folders:
            ftype = "primary" if st.session_state.get("kb_folder_id") == folder["id"] else "secondary"
            fc1, fc2 = st.columns([3, 1])
            with fc1:
                if st.button(f"📁 {folder['name']}", key=f"kbf_{folder['id']}",
                             type=ftype, use_container_width=True):
                    st.session_state.kb_folder_id = folder["id"]; st.rerun()
            with fc2:
                if st.button("✕", key=f"kbfdel_{folder['id']}", help="Delete folder"):
                    database.delete_folder(folder["id"])
                    if st.session_state.get("kb_folder_id") == folder["id"]:
                        st.session_state.kb_folder_id = None
                    st.rerun()

    with col_right:
        current_folder_id = st.session_state.get("kb_folder_id")
        folder_label = "All Files" if current_folder_id is None else next(
            (f["name"] for f in folders if f["id"] == current_folder_id), "Folder")
        st.markdown(f"**{folder_label}**")

        with st.expander("⬆️ Upload Document", expanded=False):
            up_file = st.file_uploader("Select file (PDF, DOCX, TXT)", type=["pdf","docx","txt"],
                                       key="kb_upload")
            up_subj = st.text_input("Subject tag", key="kb_subj")
            if up_file and st.button("Upload", type="primary"):
                docs_dir = os.path.join(DATA_DIR, "documents")
                os.makedirs(docs_dir, exist_ok=True)
                fpath = os.path.join(docs_dir, f"{uuid.uuid4()}_{up_file.name}")
                with open(fpath, "wb") as f: f.write(up_file.read())
                database.save_document(up_file.name, fpath, up_file.name.rsplit(".",1)[-1].lower(),
                                       subject=up_subj or None, folder_id=current_folder_id,
                                       uploaded_by=user["id"])
                st.success(f"Uploaded: {up_file.name}"); st.rerun()

        docs = database.get_documents(folder_id=current_folder_id)
        if not docs:
            st.info("No files here."); return

        all_folders_list = database.get_all_folders()
        folder_opts = {"(root)": None} | {f["name"]: f["id"] for f in all_folders_list}

        for doc in docs:
            status_html = badge(doc["index_status"],
                                "indexed" if doc["index_status"]=="indexed"
                                else "failed" if doc["index_status"]=="failed" else "pending")
            with st.expander(f"{doc['name']}  {status_html}", expanded=False):
                ic1, ic2, ic3 = st.columns([1.5, 2, 1])
                with ic1:
                    if doc["index_status"] != "indexed":
                        if st.button("⚙️ Index", key=f"idx_{doc['id']}", type="primary"):
                            if doc.get("file_path") and os.path.exists(doc["file_path"]):
                                prog = st.progress(0, text="Extracting…")
                                try:
                                    prog.progress(30, text="Extracting pages…")
                                    index = rag_utils.build_page_index(doc["file_path"], doc["file_type"])
                                    prog.progress(70, text="Saving index…")
                                    index_path = rag_utils.save_index(doc["id"], index)
                                    database.update_document_index(doc["id"], index_path, "indexed")
                                    prog.progress(100, text="Done!")
                                    st.success("Indexed"); st.rerun()
                                except Exception as e:
                                    prog.empty()
                                    st.error(f"Error: {e}")
                                    database.update_document_index(doc["id"], None, "failed")
                            else:
                                st.error("File not found on disk.")
                    else:
                        st.success("✓ Indexed")
                with ic2:
                    sel_folder = st.selectbox("Move to folder", list(folder_opts.keys()),
                                              key=f"movef_{doc['id']}")
                    if st.button("Move", key=f"movebtn_{doc['id']}"):
                        database.move_document_to_folder(doc["id"], folder_opts[sel_folder])
                        st.rerun()
                with ic3:
                    if st.button("🗑️ Delete", key=f"deldoc_{doc['id']}"):
                        for p in [doc.get("file_path"), doc.get("index_path")]:
                            if p and os.path.exists(p):
                                try: os.remove(p)
                                except Exception: pass
                        database.delete_document(doc["id"]); st.rerun()

        # Question generation
        with st.expander("🧠 Generate Practice Questions", expanded=False):
            all_indexed = [d for d in database.get_documents() if d["index_status"]=="indexed"]
            all_models = database.get_models()
            all_students_l = database.get_all_students()
            if not all_indexed:
                st.info("Index documents first.")
            elif not all_models:
                st.info("Add a model first.")
            else:
                q_doc = st.selectbox("Document", all_indexed, format_func=lambda d: d["name"])
                q_types = st.multiselect("Question types",
                    ["Multiple Choice","Fill-in-the-blank","Short Answer","True/False"],
                    default=["Multiple Choice"])
                q_model = st.selectbox("Model", all_models, format_func=lambda m: m["name"])
                q_stus = st.multiselect("Assign to students",
                    [s["username"] for s in all_students_l])
                if st.button("Generate Questions", type="primary"):
                    if q_doc and q_types and q_model:
                        context = ""
                        if q_doc.get("index_path") and os.path.exists(q_doc["index_path"]):
                            context = rag_utils.retrieve_context(q_doc["index_path"],
                                                                  "overview", top_n=5)
                        with st.spinner("Generating…"):
                            result = call_model_api_single(q_model,
                                f"Generate 3 practice questions for EACH type: {', '.join(q_types)}.\\n"
                                f"Label each, include answer. Format cleanly.\\n\\nDocument:\\n{context}")
                        st.markdown(result)
                        aids = [s["id"] for s in all_students_l if s["username"] in q_stus] or [None]
                        for aid in aids:
                            database.save_generated_question(q_doc["id"], ", ".join(q_types),
                                                             result, assigned_to=aid)
                        st.success("Saved.")


# ── Teacher / Student: Settings ─────────────────────────────────────────────

def _render_settings_inline(user):
    st.markdown("## Settings")
    _render_settings_form(user)


# ===========================================================================
# STUDENT WORKSPACE
# ===========================================================================

def render_student_workspace(user):
    username = user["username"]
    allowed_models = database.get_allowed_models_for_student(user["id"])

    with st.sidebar:
        _logo = database.get_system_image_path("logo")
        if _logo: st.image(_logo, width=60)
        st.markdown(f"**{user['name']}**")
        st.caption("Student")
        st.divider()

        if allowed_models:
            model_opts = {m["id"]: m["name"] for m in allowed_models}
            if "student_model_id" not in st.session_state:
                st.session_state.student_model_id = allowed_models[0]["id"]
            sel_mid = st.selectbox("Model", list(model_opts.keys()),
                                   format_func=lambda i: model_opts[i],
                                   index=list(model_opts.keys()).index(st.session_state.student_model_id)
                                         if st.session_state.student_model_id in model_opts else 0)
            st.session_state.student_model_id = sel_mid
        else:
            st.warning("No models assigned. Ask your teacher."); sel_mid = None

        if st.button("＋ New Chat", use_container_width=True, type="primary"):
            st.session_state.messages = []
            st.session_state.session_id = str(uuid.uuid4()); st.rerun()

        st.markdown("**Recent Chats**")
        history_dir = os.path.join(get_user_dir(username), "history")
        os.makedirs(history_dir, exist_ok=True)
        files = sorted(glob.glob(os.path.join(history_dir, "*.json")),
                       key=os.path.getmtime, reverse=True)
        for fpath in files[:20]:
            sid = os.path.basename(fpath).replace(".json", "")
            try:
                with open(fpath, "r", encoding="utf-8") as f: meta = json.load(f)
                title = meta.get("title", "Untitled")
            except Exception: title = "Corrupted"
            hc1, hc2 = st.columns([4, 1])
            with hc1:
                btn_title = title if len(title) < 22 else title[:19] + "…"
                if st.button(btn_title, key=f"open_{sid}", use_container_width=True, help=title):
                    msgs, _ = load_session(username, sid)
                    st.session_state.messages = msgs
                    st.session_state.session_id = sid; st.rerun()
            with hc2:
                if st.button("✕", key=f"hdel_{sid}", help="Delete"):
                    delete_session(username, sid)
                    if st.session_state.get("session_id") == sid:
                        st.session_state.messages = []
                        st.session_state.session_id = str(uuid.uuid4())
                    st.rerun()

        st.divider()
        if st.button("⚙️ Settings", use_container_width=True):
            dialog_settings()
        if st.button("Logout", use_container_width=True):
            st.session_state.user = None; st.rerun()

    # Determine current model
    current_model = None
    if sel_mid:
        for m in allowed_models:
            if m["id"] == sel_mid: current_model = m; break

    tab_chat, tab_practice, tab_notebook = st.tabs(["💬 Chat", "📝 Practice", "📓 Notebook"])

    # ── Chat Tab ──────────────────────────────────────────────────────────────
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
                    if os.path.exists(img_p): st.image(img_p, width=300)

        uploaded_file = st.file_uploader("Attach image", type=["jpg","png","jpeg"],
                                         label_visibility="collapsed", key="chat_upload")
        user_input = st.chat_input("Ask your AI Tutor…")

        if user_input:
            with st.chat_message("user"):
                st.markdown(user_input)
                if uploaded_file: st.image(uploaded_file, width=300)

            msg_data = {"role": "user", "content": user_input}
            if uploaded_file:
                msg_data["image_path"] = save_image(username, uploaded_file.getvalue())
            st.session_state.messages.append(msg_data)

            # Log user message
            database.log_message(user["id"], st.session_state.session_id,
                                  current_model["id"] if current_model else None,
                                  "user", user_input)

            if current_model:
                rag_inject = ""
                rag_docs = database.get_rag_docs_for_model(current_model["id"])
                for rdoc in rag_docs:
                    if rdoc.get("index_path") and os.path.exists(rdoc["index_path"]):
                        snippet = rag_utils.retrieve_context(rdoc["index_path"], user_input)
                        if snippet: rag_inject += snippet + "\\n\\n"
                chat_msgs = [{"role": m["role"], "content": m["content"]}
                              for m in st.session_state.messages]
                if rag_inject:
                    chat_msgs[-1]["content"] = (
                        f"[Relevant context:]\\n{rag_inject.strip()}\\n\\n"
                        f"[Question:] {user_input}"
                    )
                with st.chat_message("assistant"):
                    with st.spinner("Thinking…"):
                        response_text = call_model_api(current_model, chat_msgs)
                    st.markdown(response_text)
            else:
                response_text = "[No model assigned. Ask your teacher to grant access.]"
                with st.chat_message("assistant"): st.markdown(response_text)

            st.session_state.messages.append({"role": "assistant", "content": response_text})
            save_session(username, st.session_state.session_id, st.session_state.messages)

            # Log assistant message
            database.log_message(user["id"], st.session_state.session_id,
                                  current_model["id"] if current_model else None,
                                  "assistant", response_text)

            st.session_state.last_qa = (user_input, response_text)
            st.rerun()

        if "last_qa" in st.session_state and current_model:
            q, a = st.session_state.last_qa
            if st.button("📓 Add Last Q&A to Notebook"):
                with st.spinner("Summarising…"):
                    summary = call_model_api_single(current_model,
                        f"Summarise the key concept or mistake in 1-2 sentences.\\nQ: {q}\\nA: {a}")
                    add_to_notebook(username, q, a, summary)
                st.success("Added to Notebook!")
                del st.session_state.last_qa

    # ── Practice Tab ──────────────────────────────────────────────────────────
    with tab_practice:
        st.markdown("## Practice Questions")
        assigned_qs = database.get_questions_for_student(user["id"])
        if assigned_qs:
            st.markdown("### Assigned by Teacher")
            for q in assigned_qs:
                with st.expander(f"[{q['question_type']}] {q.get('doc_name','')}"):
                    st.markdown(q["question"])
            st.divider()

        st.markdown("### Generate from My Notebook")
        notebook = load_notebook(username)
        if not notebook:
            st.info("Your notebook is empty. Add entries from the Chat tab first.")
        else:
            notebook.sort(key=lambda x: x["timestamp"], reverse=True)
            opts = {e["id"]: f"{e['title']} ({e['timestamp'][:10]})" for e in notebook}
            sel_ids = st.multiselect("Select entries:", list(opts.keys()),
                                     format_func=lambda x: opts[x])
            q_types = st.multiselect("Question types",
                ["Multiple Choice","Fill-in-the-blank","Short Answer","True/False"],
                default=["Multiple Choice","Short Answer"])
            if st.button("Generate", type="primary"):
                if not sel_ids: st.warning("Select at least one entry.")
                elif not q_types: st.warning("Select at least one type.")
                elif not current_model: st.warning("No model available.")
                else:
                    entries = [n for n in notebook if n["id"] in sel_ids]
                    ctx = "".join(f"\\n---\\nTopic: {e['title']}\\nKey: {e.get('summary','')}\\nQ: {e['question']}\\n"
                                  for e in entries)
                    with st.spinner("Generating…"):
                        result = call_model_api_single(current_model,
                            f"Generate 3 practice questions for EACH type: {', '.join(q_types)}.\\n"
                            f"Number, label type, include answer.\\n\\n{ctx}")
                    st.markdown(result)

    # ── Notebook Tab ──────────────────────────────────────────────────────────
    with tab_notebook:
        st.markdown("## My Notebook")
        notebook = load_notebook(username)
        if not notebook:
            st.info("No entries yet. Add from Chat tab.")
        else:
            notebook.sort(key=lambda x: x["timestamp"], reverse=True)
            for entry in notebook:
                with st.expander(f"{entry['title']}  —  {entry['timestamp'][:16]}"):
                    new_title = st.text_input("Title", value=entry["title"],
                                              key=f"nbt_{entry['id']}")
                    if new_title != entry["title"]:
                        update_notebook_entry_title(username, entry["id"], new_title); st.rerun()
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("**Question**"); st.info(entry["question"])
                    with c2:
                        st.markdown("**Answer**"); st.info(entry["answer"])
                    if entry.get("summary"):
                        st.markdown("**Key Learning**"); st.warning(entry["summary"])
                    if st.button("🗑️ Delete", key=f"nbdel_{entry['id']}"):
                        delete_notebook_entry(username, entry["id"]); st.rerun()
        if st.button("Refresh"): st.rerun()


# ===========================================================================
# MAIN ROUTER
# ===========================================================================

if st.session_state.user is None:
    render_login()
else:
    user = st.session_state.user
    role = user.get("role")
    if role == "admin":      render_admin_dashboard(user)
    elif role == "teacher":  render_teacher_dashboard(user)
    else:                    render_student_workspace(user)
