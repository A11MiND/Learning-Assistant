import sqlite3
import hashlib
import os
import json
import csv
import io
from datetime import datetime

DB_FILE = "dse_ai.db"

# ---------------------------------------------------------------------------
# Schema & Init
# ---------------------------------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            name TEXT NOT NULL,
            account_status TEXT DEFAULT 'active',
            reset_token TEXT,
            reset_token_expiry TEXT,
            created_at TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            subject TEXT,
            teacher_id INTEGER,
            created_at TEXT,
            FOREIGN KEY(teacher_id) REFERENCES users(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS class_students (
            class_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            PRIMARY KEY(class_id, student_id),
            FOREIGN KEY(class_id) REFERENCES classes(id),
            FOREIGN KEY(student_id) REFERENCES users(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            model_name TEXT NOT NULL DEFAULT '',
            api_url TEXT NOT NULL,
            api_key TEXT,
            system_prompt TEXT,
            created_by INTEGER,
            created_at TEXT,
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS student_model_access (
            user_id INTEGER NOT NULL,
            model_id INTEGER NOT NULL,
            allowed INTEGER NOT NULL DEFAULT 1,
            override_prompt TEXT,
            PRIMARY KEY(user_id, model_id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(model_id) REFERENCES models(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS class_model_access (
            class_id INTEGER NOT NULL,
            model_id INTEGER NOT NULL,
            allowed INTEGER NOT NULL DEFAULT 1,
            override_prompt TEXT,
            PRIMARY KEY(class_id, model_id),
            FOREIGN KEY(class_id) REFERENCES classes(id),
            FOREIGN KEY(model_id) REFERENCES models(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER,
            created_by INTEGER,
            created_at TEXT,
            FOREIGN KEY(parent_id) REFERENCES folders(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            subject TEXT,
            folder_id INTEGER,
            index_status TEXT DEFAULT 'pending',
            index_path TEXT,
            uploaded_by INTEGER,
            created_at TEXT,
            FOREIGN KEY(folder_id) REFERENCES folders(id),
            FOREIGN KEY(uploaded_by) REFERENCES users(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS model_rag_links (
            model_id INTEGER NOT NULL,
            document_id INTEGER NOT NULL,
            PRIMARY KEY(model_id, document_id),
            FOREIGN KEY(model_id) REFERENCES models(id),
            FOREIGN KEY(document_id) REFERENCES documents(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS generated_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER,
            question_type TEXT NOT NULL,
            question TEXT NOT NULL,
            options TEXT,
            answer TEXT,
            assigned_to INTEGER,
            created_at TEXT,
            FOREIGN KEY(document_id) REFERENCES documents(id),
            FOREIGN KEY(assigned_to) REFERENCES users(id)
        )
    ''')

    # Legacy deployments table (kept for backward compat)
    c.execute('''
        CREATE TABLE IF NOT EXISTS deployments (
            user_id INTEGER PRIMARY KEY,
            port INTEGER UNIQUE NOT NULL,
            pid INTEGER,
            status TEXT,
            updated_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')

    conn.commit()

    # Migrations for existing DBs
    _migrate(c, conn)

    # Seed default accounts
    _seed_accounts(conn, c)

    conn.commit()
    conn.close()


def _migrate(c, conn):
    migrations = [
        ("users", "email", "ALTER TABLE users ADD COLUMN email TEXT"),
        ("users", "account_status", "ALTER TABLE users ADD COLUMN account_status TEXT DEFAULT 'active'"),
        ("users", "reset_token", "ALTER TABLE users ADD COLUMN reset_token TEXT"),
        ("users", "reset_token_expiry", "ALTER TABLE users ADD COLUMN reset_token_expiry TEXT"),
        ("models", "model_name", "ALTER TABLE models ADD COLUMN model_name TEXT NOT NULL DEFAULT ''"),
        ("models", "created_by", "ALTER TABLE models ADD COLUMN created_by INTEGER"),
        ("student_model_access", "override_prompt", "ALTER TABLE student_model_access ADD COLUMN override_prompt TEXT"),
        ("documents", "folder_id", "ALTER TABLE documents ADD COLUMN folder_id INTEGER"),
    ]
    for table, col, sql in migrations:
        try:
            c.execute(f"SELECT {col} FROM {table} LIMIT 1")
        except sqlite3.OperationalError:
            try:
                c.execute(sql)
                conn.commit()
            except Exception:
                pass


def _seed_accounts(conn, c):
    seeds = [
        ("admin123", "admin123@123.com", "admin123", "admin", "System Admin"),
        ("teacher", "teacher@teacher.com", "teacher", "teacher", "Default Teacher"),
        ("student01", "student01@student01.com", "student01", "student", "Student One"),
    ]
    for username, email, password, role, name in seeds:
        c.execute("SELECT id FROM users WHERE username=?", (username,))
        if not c.fetchone():
            c.execute(
                "INSERT OR IGNORE INTO users (username, email, password, role, name, account_status, created_at) "
                "VALUES (?,?,?,?,?,'active',?)",
                (username, email, hash_password(password), role, name, datetime.now().isoformat())
            )
    conn.commit()


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def create_user(username, password, role, name, email=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("SELECT id FROM users WHERE LOWER(username)=?", (username.lower(),))
        if c.fetchone():
            return False, "Username already taken"
        if email:
            c.execute("SELECT id FROM users WHERE LOWER(email)=?", (email.lower(),))
            if c.fetchone():
                return False, "Email already registered"
        c.execute(
            "INSERT INTO users (username, email, password, role, name, account_status, created_at) "
            "VALUES (?,?,?,?,?,'active',?)",
            (username, email, hash_password(password), role, name, datetime.now().isoformat())
        )
        conn.commit()
        return True, "OK"
    except sqlite3.IntegrityError as e:
        return False, str(e)
    finally:
        conn.close()


def verify_user(login, password):
    """login can be username or email."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT * FROM users WHERE (LOWER(username)=? OR LOWER(email)=?) AND password=?",
        (login.lower(), login.lower(), hash_password(password))
    )
    user = c.fetchone()
    conn.close()
    return dict(user) if user else None


def get_user_by_id(user_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id,username,email,name,role,account_status,created_at FROM users ORDER BY role,username")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_users_by_role(role):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id,username,email,name,role,account_status,created_at FROM users WHERE role=? ORDER BY username", (role,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_students():
    return get_users_by_role("student")


def get_all_teachers():
    return get_users_by_role("teacher")


def update_user_profile(user_id, new_username=None, new_password=None, new_name=None, new_email=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        if new_username:
            c.execute("UPDATE users SET username=? WHERE id=?", (new_username, user_id))
        if new_password:
            c.execute("UPDATE users SET password=? WHERE id=?", (hash_password(new_password), user_id))
        if new_name:
            c.execute("UPDATE users SET name=? WHERE id=?", (new_name, user_id))
        if new_email:
            c.execute("UPDATE users SET email=? WHERE id=?", (new_email, user_id))
        conn.commit()
        return True, "Updated"
    except sqlite3.IntegrityError:
        return False, "Username or email already taken"
    finally:
        conn.close()


def admin_update_user(user_id, name, username, email=None, password=None, role=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("UPDATE users SET name=?, username=? WHERE id=?", (name, username, user_id))
        if email is not None:
            c.execute("UPDATE users SET email=? WHERE id=?", (email, user_id))
        if password:
            c.execute("UPDATE users SET password=? WHERE id=?", (hash_password(password), user_id))
        if role:
            c.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
        conn.commit()
        return True, "Updated"
    except sqlite3.IntegrityError:
        return False, "Username or email already taken"
    finally:
        conn.close()


def update_user_status(user_id, status):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET account_status=? WHERE id=?", (status, user_id))
    conn.commit()
    conn.close()


def delete_user(user_id):
    user = get_user_by_id(user_id)
    if user:
        username = user["username"]
        user_dir = os.path.join("data", username)
        if os.path.exists(user_dir):
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            try:
                os.rename(user_dir, os.path.join("data", f"deleted_{ts}_{username}"))
            except OSError:
                pass
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    c.execute("DELETE FROM class_students WHERE student_id=?", (user_id,))
    c.execute("DELETE FROM student_model_access WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def import_students_from_csv(csv_text):
    """
    Parse CSV with columns: username,email,name,password
    Returns (success_count, errors list).
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    ok = 0
    errors = []
    for i, row in enumerate(reader, start=2):
        username = (row.get("username") or "").strip()
        email = (row.get("email") or "").strip()
        name = (row.get("name") or "").strip()
        password = (row.get("password") or "").strip()
        if not username or not password:
            errors.append(f"Row {i}: username and password are required")
            continue
        success, msg = create_user(username, password, "student", name or username, email or None)
        if success:
            ok += 1
        else:
            errors.append(f"Row {i} ({username}): {msg}")
    return ok, errors


# ---------------------------------------------------------------------------
# Class CRUD
# ---------------------------------------------------------------------------

def create_class(name, teacher_id, subject=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO classes (name, subject, teacher_id, created_at) VALUES (?,?,?,?)",
        (name, subject, teacher_id, datetime.now().isoformat())
    )
    cid = c.lastrowid
    conn.commit()
    conn.close()
    return cid


def get_classes_for_teacher(teacher_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM classes WHERE teacher_id=? ORDER BY name", (teacher_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_classes():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT cl.*, u.name as teacher_name, u.username as teacher_username
        FROM classes cl LEFT JOIN users u ON cl.teacher_id = u.id
        ORDER BY u.username, cl.name
    """)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_class(class_id, name=None, subject=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if name:
        c.execute("UPDATE classes SET name=? WHERE id=?", (name, class_id))
    if subject is not None:
        c.execute("UPDATE classes SET subject=? WHERE id=?", (subject, class_id))
    conn.commit()
    conn.close()


def delete_class(class_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM class_students WHERE class_id=?", (class_id,))
    c.execute("DELETE FROM class_model_access WHERE class_id=?", (class_id,))
    c.execute("DELETE FROM classes WHERE id=?", (class_id,))
    conn.commit()
    conn.close()


def add_student_to_class(class_id, student_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO class_students (class_id, student_id) VALUES (?,?)",
        (class_id, student_id)
    )
    conn.commit()
    conn.close()


def remove_student_from_class(class_id, student_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM class_students WHERE class_id=? AND student_id=?", (class_id, student_id))
    conn.commit()
    conn.close()


def get_students_in_class(class_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT u.id,u.username,u.email,u.name,u.account_status FROM users u "
        "JOIN class_students cs ON u.id=cs.student_id WHERE cs.class_id=? ORDER BY u.name",
        (class_id,)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_classes_for_student(student_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT cl.* FROM classes cl JOIN class_students cs ON cl.id=cs.class_id "
        "WHERE cs.student_id=?", (student_id,)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Model CRUD
# ---------------------------------------------------------------------------

def create_model(name, model_name, api_url, api_key=None, system_prompt=None, created_by=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO models (name, model_name, api_url, api_key, system_prompt, created_by, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (name, model_name, api_url, api_key, system_prompt, created_by, datetime.now().isoformat())
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_models(created_by=None):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if created_by is not None:
        c.execute("SELECT * FROM models WHERE created_by=? OR created_by IS NULL ORDER BY name", (created_by,))
    else:
        c.execute("SELECT * FROM models ORDER BY name")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_model(model_id, name=None, model_name=None, api_url=None, api_key=None, system_prompt=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fields, vals = [], []
    for col, val in [("name",name),("model_name",model_name),("api_url",api_url),
                     ("api_key",api_key),("system_prompt",system_prompt)]:
        if val is not None:
            fields.append(f"{col}=?")
            vals.append(val)
    if not fields:
        conn.close()
        return
    vals.append(model_id)
    c.execute(f"UPDATE models SET {', '.join(fields)} WHERE id=?", tuple(vals))
    conn.commit()
    conn.close()


def delete_model(model_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for tbl in ("student_model_access", "class_model_access", "model_rag_links"):
        c.execute(f"DELETE FROM {tbl} WHERE model_id=?", (model_id,))
    c.execute("DELETE FROM models WHERE id=?", (model_id,))
    conn.commit()
    conn.close()


def set_student_model_access(user_id, model_id, allowed, override_prompt=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO student_model_access (user_id, model_id, allowed, override_prompt) VALUES (?,?,?,?) "
        "ON CONFLICT(user_id, model_id) DO UPDATE SET allowed=excluded.allowed, override_prompt=excluded.override_prompt",
        (user_id, model_id, 1 if allowed else 0, override_prompt)
    )
    conn.commit()
    conn.close()


def set_class_model_access(class_id, model_id, allowed, override_prompt=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO class_model_access (class_id, model_id, allowed, override_prompt) VALUES (?,?,?,?) "
        "ON CONFLICT(class_id, model_id) DO UPDATE SET allowed=excluded.allowed, override_prompt=excluded.override_prompt",
        (class_id, model_id, 1 if allowed else 0, override_prompt)
    )
    conn.commit()
    conn.close()


def get_allowed_models_for_student(user_id):
    """
    Returns models granted to this student via:
    1. Direct student_model_access (allowed=1)
    2. Class membership in class_model_access (allowed=1)
    Individual grants take precedence over class grants.
    """
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # Individual direct grants
    c.execute(
        "SELECT m.*, a.override_prompt FROM models m "
        "JOIN student_model_access a ON m.id=a.model_id "
        "WHERE a.user_id=? AND a.allowed=1", (user_id,)
    )
    direct = {r["id"]: dict(r) for r in c.fetchall()}
    # Class grants
    c.execute(
        "SELECT m.*, ca.override_prompt FROM models m "
        "JOIN class_model_access ca ON m.id=ca.model_id "
        "JOIN class_students cs ON ca.class_id=cs.class_id "
        "WHERE cs.student_id=? AND ca.allowed=1", (user_id,)
    )
    for r in c.fetchall():
        if r["id"] not in direct:
            direct[r["id"]] = dict(r)
    conn.close()
    return list(direct.values())


def get_class_model_access(class_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT model_id, allowed, override_prompt FROM class_model_access WHERE class_id=?", (class_id,))
    rows = c.fetchall()
    conn.close()
    return {r["model_id"]: dict(r) for r in rows}


def get_student_model_access_map(user_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT model_id, allowed, override_prompt FROM student_model_access WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return {r["model_id"]: dict(r) for r in rows}


# ---------------------------------------------------------------------------
# Model RAG links
# ---------------------------------------------------------------------------

def set_model_rag_links(model_id, doc_ids):
    """Replace all RAG links for a model with the given doc_id list."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM model_rag_links WHERE model_id=?", (model_id,))
    for did in doc_ids:
        c.execute("INSERT OR IGNORE INTO model_rag_links (model_id, document_id) VALUES (?,?)", (model_id, did))
    conn.commit()
    conn.close()


def get_rag_docs_for_model(model_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT d.* FROM documents d JOIN model_rag_links l ON d.id=l.document_id "
        "WHERE l.model_id=? AND d.index_status='indexed'", (model_id,)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_rag_link_ids_for_model(model_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT document_id FROM model_rag_links WHERE model_id=?", (model_id,))
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Folder CRUD
# ---------------------------------------------------------------------------

def create_folder(name, parent_id=None, created_by=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO folders (name, parent_id, created_by, created_at) VALUES (?,?,?,?)",
        (name, parent_id, created_by, datetime.now().isoformat())
    )
    fid = c.lastrowid
    conn.commit()
    conn.close()
    return fid


def get_folders(parent_id=None):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if parent_id is None:
        c.execute("SELECT * FROM folders WHERE parent_id IS NULL ORDER BY name")
    else:
        c.execute("SELECT * FROM folders WHERE parent_id=? ORDER BY name", (parent_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_folders():
    """Return every folder regardless of hierarchy, ordered by name."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM folders ORDER BY name")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_folder(folder_id):
    """Recursively delete folder and move its documents to root (folder_id=NULL)."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE documents SET folder_id=NULL WHERE folder_id=?", (folder_id,))
    # Recursively handle children
    c.execute("SELECT id FROM folders WHERE parent_id=?", (folder_id,))
    children = [r[0] for r in c.fetchall()]
    conn.commit()
    conn.close()
    for child in children:
        delete_folder(child)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE folders SET parent_id=NULL WHERE parent_id=?", (folder_id,))
    c.execute("DELETE FROM folders WHERE id=?", (folder_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Document CRUD
# ---------------------------------------------------------------------------

def save_document(name, file_path, file_type, subject=None, folder_id=None, uploaded_by=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO documents (name, file_path, file_type, subject, folder_id, uploaded_by, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (name, file_path, file_type, subject, folder_id, uploaded_by, datetime.now().isoformat())
    )
    doc_id = c.lastrowid
    conn.commit()
    conn.close()
    return doc_id


def get_documents(folder_id=None, include_unfoldered=False):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if folder_id is not None:
        c.execute("SELECT * FROM documents WHERE folder_id=? ORDER BY name", (folder_id,))
    elif include_unfoldered:
        c.execute("SELECT * FROM documents WHERE folder_id IS NULL ORDER BY name")
    else:
        c.execute("SELECT * FROM documents ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_document(doc_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM documents WHERE id=?", (doc_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def update_document_index(doc_id, index_path, status="indexed"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE documents SET index_path=?, index_status=? WHERE id=?", (index_path, status, doc_id))
    conn.commit()
    conn.close()


def move_document_to_folder(doc_id, folder_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE documents SET folder_id=? WHERE id=?", (folder_id, doc_id))
    conn.commit()
    conn.close()


def delete_document(doc_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM model_rag_links WHERE document_id=?", (doc_id,))
    c.execute("DELETE FROM generated_questions WHERE document_id=?", (doc_id,))
    c.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Questions CRUD
# ---------------------------------------------------------------------------

def save_generated_question(document_id, question_type, question, options=None, answer=None, assigned_to=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO generated_questions (document_id, question_type, question, options, answer, assigned_to, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (document_id, question_type, question,
         json.dumps(options) if options else None,
         answer, assigned_to, datetime.now().isoformat())
    )
    qid = c.lastrowid
    conn.commit()
    conn.close()
    return qid


def get_questions_for_document(doc_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM generated_questions WHERE document_id=? ORDER BY created_at", (doc_id,))
    rows = c.fetchall()
    conn.close()
    return [_parse_q(dict(r)) for r in rows]


def get_questions_for_student(student_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT q.*,d.name as doc_name FROM generated_questions q "
        "LEFT JOIN documents d ON q.document_id=d.id "
        "WHERE q.assigned_to=? OR q.assigned_to IS NULL ORDER BY q.created_at DESC",
        (student_id,)
    )
    rows = c.fetchall()
    conn.close()
    return [_parse_q(dict(r)) for r in rows]


def _parse_q(d):
    if d.get("options"):
        try:
            d["options"] = json.loads(d["options"])
        except Exception:
            pass
    return d


def delete_question(question_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM generated_questions WHERE id=?", (question_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Legacy deployment helpers (kept for cleanup utilities)
# ---------------------------------------------------------------------------

def get_deployment(user_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM deployments WHERE user_id=?", (user_id,))
    dep = c.fetchone()
    conn.close()
    return dict(dep) if dep else None


def get_all_active_ports():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT port FROM deployments WHERE status='running'")
    ports = [r[0] for r in c.fetchall()]
    conn.close()
    return ports


def stop_deployment_record(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE deployments SET status='stopped', pid=NULL WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def cleanup_zombies():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT user_id, pid FROM deployments WHERE status='running'")
    rows = c.fetchall()
    conn.close()
    for row in rows:
        pid = row["pid"]
        if pid:
            try:
                os.kill(pid, 0)
            except OSError:
                stop_deployment_record(row["user_id"])
