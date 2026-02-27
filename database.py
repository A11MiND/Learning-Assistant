import sqlite3
import hashlib
import os
import json
from datetime import datetime

DB_FILE = "dse_ai.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT
        )
    ''')

    # Deployments table
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

    # Models table: teacher-registered LLM endpoints
    c.execute('''
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            model_name TEXT NOT NULL DEFAULT '',
            api_url TEXT NOT NULL,
            api_key TEXT,
            system_prompt TEXT,
            created_at TEXT
        )
    ''')

    # Student <-> model access table
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

    # Knowledge base documents uploaded by teacher
    c.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            subject TEXT,
            index_status TEXT DEFAULT 'pending',
            index_path TEXT,
            uploaded_by INTEGER,
            created_at TEXT,
            FOREIGN KEY(uploaded_by) REFERENCES users(id)
        )
    ''')

    # Teacher-generated (or AI-generated) practice questions
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

    # Seed teacher account if missing
    c.execute("SELECT * FROM users WHERE role='teacher'")
    if not c.fetchone():
        conn.commit()
        conn.close()
        create_user("teacher", "admin", "teacher", "Teacher Admin")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

    # Migrations
    try:
        c.execute("SELECT account_status FROM users LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE users ADD COLUMN account_status TEXT DEFAULT 'active'")

    try:
        c.execute("SELECT model_name FROM models LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE models ADD COLUMN model_name TEXT NOT NULL DEFAULT ''")

    try:
        c.execute("SELECT override_prompt FROM student_model_access LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE student_model_access ADD COLUMN override_prompt TEXT")

    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, password, role, name):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # Check for case-insensitive username existence
        c.execute("SELECT id FROM users WHERE LOWER(username) = ?", (username.lower(),))
        if c.fetchone():
            return False
            
        c.execute("INSERT INTO users (username, password, role, name, created_at) VALUES (?, ?, ?, ?, ?)",
                  (username, hash_password(password), role, name, datetime.now().isoformat()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def verify_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, hash_password(password)))
    user = c.fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_id(user_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return dict(user) if user else None

def update_user_profile(user_id, new_username=None, new_password=None, new_name=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        if new_username:
            c.execute("UPDATE users SET username = ? WHERE id = ?", (new_username, user_id))
        if new_password:
            c.execute("UPDATE users SET password = ? WHERE id = ?", (hash_password(new_password), user_id))
        if new_name:
            c.execute("UPDATE users SET name = ? WHERE id = ?", (new_name, user_id))
        conn.commit()
        return True, "Update successful"
    except sqlite3.IntegrityError:
        return False, "Username already taken"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def update_user_status(user_id, status):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET account_status = ? WHERE id = ?", (status, user_id))
    conn.commit()
    conn.close()

def admin_update_user(user_id, name, username, password=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("UPDATE users SET name = ?, username = ? WHERE id = ?", (name, username, user_id))
        if password:
            c.execute("UPDATE users SET password = ? WHERE id = ?", (hash_password(password), user_id))
        conn.commit()
        return True, "Update successful"
    except sqlite3.IntegrityError:
        return False, "Username already taken"
    finally:
        conn.close()

def get_all_students():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # Ensure account_status is returned even if defaulting
    c.execute("SELECT id, username, name, created_at, account_status FROM users WHERE role = 'student'")
    students = [dict(row) for row in c.fetchall()]
    conn.close()
    return students

def delete_user(user_id):
    # Get username before deletion for folder cleanup
    user = get_user_by_id(user_id)
    if user:
        import shutil
        username = user['username']
        user_dir = os.path.join("data", username)
        if os.path.exists(user_dir):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            deleted_dir = os.path.join("data", f"deleted_{timestamp}_{username}")
            try:
                os.rename(user_dir, deleted_dir)
            except OSError:
                pass # Fallback or log error

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    c.execute("DELETE FROM deployments WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# --- Deployment Management ---

def get_deployment(user_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM deployments WHERE user_id = ?", (user_id,))
    dep = c.fetchone()
    conn.close()
    return dict(dep) if dep else None

def update_deployment(user_id, port, pid, status="running"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO deployments (user_id, port, pid, status, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            port=excluded.port,
            pid=excluded.pid,
            status=excluded.status,
            updated_at=excluded.updated_at
    ''', (user_id, port, pid, status, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_all_active_ports():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT port FROM deployments WHERE status = 'running'")
    ports = [row[0] for row in c.fetchall()]
    conn.close()
    return ports

def stop_deployment_record(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE deployments SET status = 'stopped', pid = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# model-related helper functions
# ---------------------------------------------------------------------------

def create_model(name, model_name, api_url, api_key=None, system_prompt=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO models (name, model_name, api_url, api_key, system_prompt, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (name, model_name, api_url, api_key, system_prompt, datetime.now().isoformat())
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_models():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM models ORDER BY name")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_model(model_id, name=None, model_name=None, api_url=None, api_key=None, system_prompt=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fields = []
    vals = []
    if name is not None:
        fields.append("name = ?")
        vals.append(name)
    if model_name is not None:
        fields.append("model_name = ?")
        vals.append(model_name)
    if api_url is not None:
        fields.append("api_url = ?")
        vals.append(api_url)
    if api_key is not None:
        fields.append("api_key = ?")
        vals.append(api_key)
    if system_prompt is not None:
        fields.append("system_prompt = ?")
        vals.append(system_prompt)
    if not fields:
        conn.close()
        return
    vals.append(model_id)
    sql = "UPDATE models SET %s WHERE id = ?" % ", ".join(fields)
    c.execute(sql, tuple(vals))
    conn.commit()
    conn.close()


def delete_model(model_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM models WHERE id = ?", (model_id,))
    c.execute("DELETE FROM student_model_access WHERE model_id = ?", (model_id,))
    conn.commit()
    conn.close()


def set_student_model_access(user_id, model_id, allowed, override_prompt=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO student_model_access (user_id, model_id, allowed, override_prompt) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, model_id) DO UPDATE SET allowed=excluded.allowed, override_prompt=excluded.override_prompt",
        (user_id, model_id, 1 if allowed else 0, override_prompt)
    )
    conn.commit()
    conn.close()


def get_allowed_models_for_student(user_id):
    """Return list of allowed models, each including override_prompt from the access record."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT m.*, a.override_prompt FROM models m "
        "JOIN student_model_access a ON m.id = a.model_id "
        "WHERE a.user_id = ? AND a.allowed = 1", (user_id,)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_students_for_model(model_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT u.* FROM users u "
        "JOIN student_model_access a ON u.id = a.user_id "
        "WHERE a.model_id = ? AND a.allowed = 1", (model_id,)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ---------------------------------------------------------------------------
# document & question management
# ---------------------------------------------------------------------------

def save_document(name, file_path, file_type, subject=None, uploaded_by=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO documents (name, file_path, file_type, subject, uploaded_by, created_at) VALUES (?,?,?,?,?,?)",
        (name, file_path, file_type, subject, uploaded_by, datetime.now().isoformat())
    )
    doc_id = c.lastrowid
    conn.commit()
    conn.close()
    return doc_id


def get_documents():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM documents ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_document(doc_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def update_document_index(doc_id, index_path, status="indexed"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE documents SET index_path=?, index_status=? WHERE id=?",
              (index_path, status, doc_id))
    conn.commit()
    conn.close()


def delete_document(doc_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    c.execute("DELETE FROM generated_questions WHERE document_id=?", (doc_id,))
    conn.commit()
    conn.close()


def save_generated_question(document_id, question_type, question, options=None, answer=None, assigned_to=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO generated_questions "
        "(document_id, question_type, question, options, answer, assigned_to, created_at) "
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
    result = []
    for r in rows:
        d = dict(r)
        if d.get('options'):
            try:
                d['options'] = json.loads(d['options'])
            except Exception:
                pass
        result.append(d)
    return result


def get_questions_for_student(student_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT q.*, d.name as doc_name FROM generated_questions q "
        "LEFT JOIN documents d ON q.document_id = d.id "
        "WHERE q.assigned_to = ? OR q.assigned_to IS NULL "
        "ORDER BY q.created_at DESC",
        (student_id,)
    )
    rows = c.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        if d.get('options'):
            try:
                d['options'] = json.loads(d['options'])
            except Exception:
                pass
        result.append(d)
    return result


def delete_question(question_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM generated_questions WHERE id=?", (question_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------


def cleanup_zombies():
    """Check all running deployments and verify if process exists."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT user_id, pid FROM deployments WHERE status = 'running'")
    rows = c.fetchall()
    conn.close()

    for row in rows:
        pid = row['pid']
        if pid:
            try:
                os.kill(pid, 0)
            except OSError:
                # Process is dead
                stop_deployment_record(row['user_id'])
