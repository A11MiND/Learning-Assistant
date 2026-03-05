import sqlite3
import hashlib
import os
import json
import csv
import io
import re
import secrets
from datetime import datetime

# Optional bcrypt (Task 9)
try:
    import bcrypt as _bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False

# Optional Fernet encryption (Task 10)
try:
    from cryptography.fernet import Fernet as _Fernet
    HAS_FERNET = True
except ImportError:
    HAS_FERNET = False

# Task 11: configurable DB via environment variable
_db_url = os.environ.get("DATABASE_URL", "dse_ai.db")
DB_FILE = _db_url[10:] if _db_url.startswith("sqlite:///") else _db_url

# ---------------------------------------------------------------------------
# Fernet helpers (Task 10)
# ---------------------------------------------------------------------------

_FERNET_KEY_FILE = os.path.join("data", "system", ".fernet_key")


def _get_fernet():
    """Return a Fernet instance, or None if unavailable."""
    if not HAS_FERNET:
        return None
    key = os.environ.get("FERNET_KEY")
    if not key:
        if os.path.exists(_FERNET_KEY_FILE):
            with open(_FERNET_KEY_FILE, "rb") as f:
                key = f.read().strip()
        else:
            key = _Fernet.generate_key()
            os.makedirs(os.path.dirname(_FERNET_KEY_FILE), exist_ok=True)
            with open(_FERNET_KEY_FILE, "wb") as f:
                f.write(key)
    if isinstance(key, str):
        key = key.encode()
    try:
        return _Fernet(key)
    except Exception:
        return None


def encrypt_api_key(plaintext):
    """Encrypt API key. Prefix result with 'fernet:' so we can detect it."""
    if not plaintext:
        return plaintext
    f = _get_fernet()
    if f:
        return "fernet:" + f.encrypt(plaintext.encode()).decode()
    return plaintext


def decrypt_api_key(stored):
    """Decrypt API key. Handles both encrypted (fernet:...) and plain strings."""
    if not stored or not stored.startswith("fernet:"):
        return stored
    f = _get_fernet()
    if f:
        try:
            return f.decrypt(stored[7:].encode()).decode()
        except Exception:
            return stored
    return stored


# ---------------------------------------------------------------------------
# Schema & Init
# ---------------------------------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
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
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            subject TEXT,
            teacher_id INTEGER,
            created_at TEXT,
            FOREIGN KEY(teacher_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS class_students (
            class_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            PRIMARY KEY(class_id, student_id),
            FOREIGN KEY(class_id) REFERENCES classes(id),
            FOREIGN KEY(student_id) REFERENCES users(id)
        )
    """)

    # is_active: 1 = published (visible to teachers), 0 = draft
    # managed_by: 'admin' = created in admin hub, 'teacher' = teacher's own model
    c.execute("""
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            model_name TEXT NOT NULL DEFAULT '',
            api_url TEXT NOT NULL,
            api_key TEXT,
            system_prompt TEXT,
            is_active INTEGER DEFAULT 1,
            managed_by TEXT DEFAULT 'admin',
            created_by INTEGER,
            created_at TEXT,
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS student_model_access (
            user_id INTEGER NOT NULL,
            model_id INTEGER NOT NULL,
            allowed INTEGER NOT NULL DEFAULT 1,
            override_prompt TEXT,
            PRIMARY KEY(user_id, model_id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(model_id) REFERENCES models(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS class_model_access (
            class_id INTEGER NOT NULL,
            model_id INTEGER NOT NULL,
            allowed INTEGER NOT NULL DEFAULT 1,
            override_prompt TEXT,
            PRIMARY KEY(class_id, model_id),
            FOREIGN KEY(class_id) REFERENCES classes(id),
            FOREIGN KEY(model_id) REFERENCES models(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER,
            created_by INTEGER,
            created_at TEXT,
            FOREIGN KEY(parent_id) REFERENCES folders(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
    """)

    c.execute("""
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
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS model_rag_links (
            model_id INTEGER NOT NULL,
            document_id INTEGER NOT NULL,
            PRIMARY KEY(model_id, document_id),
            FOREIGN KEY(model_id) REFERENCES models(id),
            FOREIGN KEY(document_id) REFERENCES documents(id)
        )
    """)

    c.execute("""
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
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS deployments (
            user_id INTEGER PRIMARY KEY,
            port INTEGER UNIQUE NOT NULL,
            pid INTEGER,
            status TEXT,
            updated_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            model_id INTEGER,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            token_estimate INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(model_id) REFERENCES models(id)
        )
    """)

    # Task 2: Registration auth keys
    c.execute("""
        CREATE TABLE IF NOT EXISTS system_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_value TEXT UNIQUE NOT NULL,
            target_role TEXT NOT NULL DEFAULT 'teacher',
            used_by INTEGER,
            created_at TEXT,
            used_at TEXT,
            FOREIGN KEY(used_by) REFERENCES users(id)
        )
    """)

    conn.commit()
    _migrate(c, conn)
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
        ("models", "is_active", "ALTER TABLE models ADD COLUMN is_active INTEGER DEFAULT 1"),
        ("models", "managed_by", "ALTER TABLE models ADD COLUMN managed_by TEXT DEFAULT 'admin'"),
        ("student_model_access", "override_prompt", "ALTER TABLE student_model_access ADD COLUMN override_prompt TEXT"),
        ("documents", "folder_id", "ALTER TABLE documents ADD COLUMN folder_id INTEGER"),
        ("chat_logs", "token_estimate", "ALTER TABLE chat_logs ADD COLUMN token_estimate INTEGER DEFAULT 0"),
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
# Password helpers (Task 9: bcrypt with SHA-256 fallback + auto-upgrade)
# ---------------------------------------------------------------------------

def hash_password(password):
    """Hash password using bcrypt if available, else SHA-256."""
    if HAS_BCRYPT:
        return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")
    return hashlib.sha256(password.encode()).hexdigest()


def _verify_password(plain, stored):
    """Verify plain password against stored hash (bcrypt or SHA-256)."""
    if stored.startswith("$2b$") or stored.startswith("$2a$"):
        if HAS_BCRYPT:
            return _bcrypt.checkpw(plain.encode("utf-8"), stored.encode("utf-8"))
        return False
    return hashlib.sha256(plain.encode()).hexdigest() == stored


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
    """Login can be username or email. Auto-upgrades SHA-256 -> bcrypt on success."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT * FROM users WHERE (LOWER(username)=? OR LOWER(email)=?)",
        (login.lower(), login.lower())
    )
    user = c.fetchone()
    if user and _verify_password(password, user["password"]):
        user_dict = dict(user)
        # Auto-upgrade SHA-256 -> bcrypt (seamless)
        if HAS_BCRYPT and not user["password"].startswith("$2"):
            new_hash = hash_password(password)
            c.execute("UPDATE users SET password=? WHERE id=?", (new_hash, user["id"]))
            conn.commit()
            user_dict["password"] = new_hash
        conn.close()
        return user_dict
    conn.close()
    return None


def get_user_by_id(user_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    return dict(user) if user else None


def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY role, username")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_users_by_role(role):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE role=? ORDER BY username", (role,))
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
    fields, vals = [], []
    if new_username:
        fields.append("username=?"); vals.append(new_username)
    if new_password:
        fields.append("password=?"); vals.append(hash_password(new_password))
    if new_name:
        fields.append("name=?"); vals.append(new_name)
    if new_email is not None:
        fields.append("email=?"); vals.append(new_email or None)
    if not fields:
        conn.close()
        return True, "No changes"
    vals.append(user_id)
    try:
        c.execute(f"UPDATE users SET {', '.join(fields)} WHERE id=?", tuple(vals))
        conn.commit()
        return True, "OK"
    except sqlite3.IntegrityError as e:
        return False, str(e)
    finally:
        conn.close()


def admin_update_user(user_id, name, username, email=None, password=None, role=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fields = ["name=?", "username=?"]
    vals = [name, username]
    if email is not None:
        fields.append("email=?"); vals.append(email)
    if password:
        fields.append("password=?"); vals.append(hash_password(password))
    if role:
        fields.append("role=?"); vals.append(role)
    vals.append(user_id)
    try:
        c.execute(f"UPDATE users SET {', '.join(fields)} WHERE id=?", tuple(vals))
        conn.commit()
        return True, "OK"
    except sqlite3.IntegrityError as e:
        return False, str(e)
    finally:
        conn.close()


def update_user_status(user_id, status):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET account_status=? WHERE id=?", (status, user_id))
    conn.commit()
    conn.close()


def delete_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for tbl in ("student_model_access", "class_students", "chat_logs"):
        c.execute(f"DELETE FROM {tbl} WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM generated_questions WHERE assigned_to=?", (user_id,))
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()


def import_students_from_csv(csv_text):
    """Parse CSV 'username,email,name,password' and bulk-create students."""
    reader = csv.reader(io.StringIO(csv_text))
    ok_count = 0
    errors = []
    for i, row in enumerate(reader, 1):
        row = [c.strip() for c in row]
        if not row or (len(row) == 1 and not row[0]):
            continue
        if row[0].lower() in ("username", "user"):
            continue  # header
        if len(row) < 4:
            errors.append(f"Row {i}: expected 4 columns, got {len(row)}: {row}")
            continue
        username, email, name, password = row[0], row[1], row[2], row[3]
        ok, msg = create_user(username, password, "student", name or username, email=email or None)
        if ok:
            ok_count += 1
        else:
            errors.append(f"Row {i} ({username}): {msg}")
    return ok_count, errors


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
    class_id = c.lastrowid
    conn.commit()
    conn.close()
    return class_id


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
    c.execute(
        "SELECT c.*, u.name as teacher_name FROM classes c "
        "LEFT JOIN users u ON c.teacher_id=u.id ORDER BY c.name"
    )
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
    for tbl in ("class_students", "class_model_access"):
        c.execute(f"DELETE FROM {tbl} WHERE class_id=?", (class_id,))
    c.execute("DELETE FROM classes WHERE id=?", (class_id,))
    conn.commit()
    conn.close()


def add_student_to_class(class_id, student_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT OR IGNORE INTO class_students (class_id, student_id) VALUES (?,?)",
            (class_id, student_id)
        )
        conn.commit()
    finally:
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
        "SELECT u.* FROM users u JOIN class_students cs ON u.id=cs.student_id "
        "WHERE cs.class_id=? ORDER BY u.username",
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
        "SELECT c.* FROM classes c JOIN class_students cs ON c.id=cs.class_id "
        "WHERE cs.student_id=? ORDER BY c.name",
        (student_id,)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Model CRUD (Task 4: Model Hub + Task 10: Fernet encryption)
# ---------------------------------------------------------------------------

def create_model(name, model_name, api_url, api_key=None, system_prompt=None,
                 created_by=None, is_active=1, managed_by="admin"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO models (name, model_name, api_url, api_key, system_prompt, "
            "is_active, managed_by, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (name, model_name, api_url, encrypt_api_key(api_key), system_prompt,
             is_active, managed_by, created_by, datetime.now().isoformat())
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_models(created_by=None, include_inactive=True):
    """Return all (or filtered) models, with api_key decrypted."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if created_by is not None:
        c.execute(
            "SELECT * FROM models WHERE (created_by=? OR created_by IS NULL) ORDER BY name",
            (created_by,)
        )
    elif include_inactive:
        c.execute("SELECT * FROM models ORDER BY name")
    else:
        c.execute("SELECT * FROM models WHERE is_active=1 ORDER BY name")
    rows = c.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["api_key"] = decrypt_api_key(d.get("api_key"))
        result.append(d)
    return result


def get_published_models():
    """Models that are is_active=1. Shown to teachers for class/student grants."""
    return get_models(include_inactive=False)


def update_model(model_id, name=None, model_name=None, api_url=None,
                 api_key=None, system_prompt=None, is_active=None, managed_by=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fields, vals = [], []
    for col, val in [("name", name), ("model_name", model_name), ("api_url", api_url),
                     ("system_prompt", system_prompt)]:
        if val is not None:
            fields.append(f"{col}=?"); vals.append(val)
    if api_key is not None:
        fields.append("api_key=?"); vals.append(encrypt_api_key(api_key))
    if is_active is not None:
        fields.append("is_active=?"); vals.append(is_active)
    if managed_by is not None:
        fields.append("managed_by=?"); vals.append(managed_by)
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


# ---------------------------------------------------------------------------
# System Keys CRUD (Task 2: Registration auth codes)
# ---------------------------------------------------------------------------

def create_system_key(target_role="teacher"):
    """Generate a new registration key. Returns the key string."""
    key = secrets.token_hex(12).upper()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO system_keys (key_value, target_role, created_at) VALUES (?,?,?)",
        (key, target_role, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return key


def create_system_keys_bulk(n, target_role="teacher"):
    """Generate n registration keys at once. Returns list of key strings."""
    return [create_system_key(target_role) for _ in range(n)]


def list_system_keys(used=None):
    """Return all keys. used=True/False/None to filter."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if used is True:
        c.execute(
            "SELECT k.*, u.username as used_by_username FROM system_keys k "
            "LEFT JOIN users u ON k.used_by=u.id WHERE k.used_by IS NOT NULL "
            "ORDER BY k.created_at DESC"
        )
    elif used is False:
        c.execute(
            "SELECT k.*, NULL as used_by_username FROM system_keys k "
            "WHERE k.used_by IS NULL ORDER BY k.created_at DESC"
        )
    else:
        c.execute(
            "SELECT k.*, u.username as used_by_username FROM system_keys k "
            "LEFT JOIN users u ON k.used_by=u.id ORDER BY k.created_at DESC"
        )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def use_system_key(key_value, user_id):
    """Mark a key as used. Returns (ok, target_role)."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT * FROM system_keys WHERE UPPER(key_value)=? AND used_by IS NULL",
        (key_value.upper().strip(),)
    )
    row = c.fetchone()
    if not row:
        conn.close()
        return False, None
    c.execute(
        "UPDATE system_keys SET used_by=?, used_at=? WHERE id=?",
        (user_id, datetime.now().isoformat(), row["id"])
    )
    conn.commit()
    conn.close()
    return True, row["target_role"]


def delete_system_key(key_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM system_keys WHERE id=?", (key_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Model Access
# ---------------------------------------------------------------------------

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
    """Union of class grants + direct grants. Returns full model dicts (key decrypted)."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT DISTINCT m.* FROM models m WHERE m.is_active=1 AND m.id IN ("
        "  SELECT sma.model_id FROM student_model_access sma "
        "  WHERE sma.user_id=? AND sma.allowed=1 "
        "  UNION "
        "  SELECT cma.model_id FROM class_model_access cma "
        "  JOIN class_students cs ON cma.class_id=cs.class_id "
        "  WHERE cs.student_id=? AND cma.allowed=1"
        ") ORDER BY m.name",
        (user_id, user_id)
    )
    rows = c.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["api_key"] = decrypt_api_key(d.get("api_key"))
        result.append(d)
    return result


def get_class_model_access(class_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM class_model_access WHERE class_id=?", (class_id,))
    rows = c.fetchall()
    conn.close()
    return {r["model_id"]: dict(r) for r in rows}


def get_student_model_access_map(user_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM student_model_access WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return {r["model_id"]: dict(r) for r in rows}


# ---------------------------------------------------------------------------
# RAG Links
# ---------------------------------------------------------------------------

def set_model_rag_links(model_id, doc_ids):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM model_rag_links WHERE model_id=?", (model_id,))
    for did in doc_ids:
        c.execute(
            "INSERT OR IGNORE INTO model_rag_links (model_id, document_id) VALUES (?,?)",
            (model_id, did)
        )
    conn.commit()
    conn.close()


def get_rag_docs_for_model(model_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT d.* FROM documents d JOIN model_rag_links mrl ON d.id=mrl.document_id "
        "WHERE mrl.model_id=? AND d.index_status='indexed'",
        (model_id,)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_rag_link_ids_for_model(model_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT document_id FROM model_rag_links WHERE model_id=?", (model_id,))
    rows = c.fetchall()
    conn.close()
    return [r["document_id"] for r in rows]


# ---------------------------------------------------------------------------
# Folders
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
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM folders ORDER BY name")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_folder(folder_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE documents SET folder_id=NULL WHERE folder_id=?", (folder_id,))
    c.execute("UPDATE folders SET parent_id=NULL WHERE parent_id=?", (folder_id,))
    c.execute("DELETE FROM folders WHERE id=?", (folder_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

def save_document(name, file_path, file_type, subject=None, folder_id=None, uploaded_by=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO documents (name, file_path, file_type, subject, folder_id, "
        "index_status, uploaded_by, created_at) VALUES (?,?,?,?,?,'pending',?,?)",
        (name, file_path, file_type, subject, folder_id, uploaded_by, datetime.now().isoformat())
    )
    did = c.lastrowid
    conn.commit()
    conn.close()
    return did


def get_documents(folder_id=None, include_unfoldered=False):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if folder_id is not None:
        c.execute("SELECT * FROM documents WHERE folder_id=? ORDER BY name", (folder_id,))
    elif include_unfoldered:
        c.execute("SELECT * FROM documents WHERE folder_id IS NULL ORDER BY name")
    else:
        c.execute("SELECT * FROM documents ORDER BY name")
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
    c.execute("UPDATE documents SET index_path=?, index_status=? WHERE id=?",
              (index_path, status, doc_id))
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
# Questions
# ---------------------------------------------------------------------------

def save_generated_question(document_id, question_type, question,
                             options=None, answer=None, assigned_to=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO generated_questions (document_id, question_type, question, options, answer, "
        "assigned_to, created_at) VALUES (?,?,?,?,?,?,?)",
        (document_id, question_type, question,
         json.dumps(options) if options else None, answer,
         assigned_to, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_questions_for_document(doc_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM generated_questions WHERE document_id=? ORDER BY created_at DESC", (doc_id,))
    rows = c.fetchall()
    conn.close()
    return [_parse_q(dict(r)) for r in rows]


def get_questions_for_student(student_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT gq.*, d.name as doc_name FROM generated_questions gq "
        "LEFT JOIN documents d ON gq.document_id=d.id "
        "WHERE gq.assigned_to=? OR gq.assigned_to IS NULL ORDER BY gq.created_at DESC",
        (student_id,)
    )
    rows = c.fetchall()
    conn.close()
    return [_parse_q(dict(r)) for r in rows]


def _parse_q(d):
    if d.get("options") and isinstance(d["options"], str):
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
# Deployments (kept for backward compat)
# ---------------------------------------------------------------------------

def get_deployment(user_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM deployments WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_active_ports():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT port FROM deployments WHERE status='running'")
    rows = c.fetchall()
    conn.close()
    return [r["port"] for r in rows]


def stop_deployment_record(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE deployments SET status='stopped', updated_at=? WHERE user_id=?",
              (datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()


def cleanup_zombies():
    """Called at startup to mark stale deployments as stopped."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE deployments SET status='stopped' WHERE status='running'")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Chat Logs & Analytics
# ---------------------------------------------------------------------------

def log_message(user_id, session_id, model_id, role, content):
    token_estimate = int(len(content.split()) * 1.3)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO chat_logs (user_id, session_id, model_id, role, content, token_estimate, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (user_id, session_id, model_id, role, content, token_estimate, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_chat_logs_for_student(user_id, limit=200):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT * FROM chat_logs WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_chat_logs_for_class(class_id, limit=1000):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT cl.* FROM chat_logs cl "
        "JOIN class_students cs ON cl.user_id=cs.student_id "
        "WHERE cs.class_id=? ORDER BY cl.created_at DESC LIMIT ?",
        (class_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_analytics_daily_counts(user_ids, days=14):
    from datetime import timedelta
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    if user_ids:
        placeholders = ",".join("?" * len(user_ids))
        c.execute(
            f"SELECT DATE(created_at) as day, COUNT(*) as messages, "
            f"COALESCE(SUM(token_estimate),0) as tokens "
            f"FROM chat_logs WHERE role='user' AND user_id IN ({placeholders}) "
            f"AND created_at >= ? GROUP BY DATE(created_at) ORDER BY day",
            tuple(user_ids) + (cutoff,)
        )
    else:
        c.execute(
            "SELECT DATE(created_at) as day, COUNT(*) as messages, "
            "COALESCE(SUM(token_estimate),0) as tokens "
            "FROM chat_logs WHERE role='user' AND created_at >= ? "
            "GROUP BY DATE(created_at) ORDER BY day",
            (cutoff,)
        )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_analytics_per_student(class_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT u.username, COUNT(cl.id) as messages, "
        "COALESCE(SUM(cl.token_estimate),0) as tokens "
        "FROM users u "
        "JOIN class_students cs ON u.id=cs.student_id "
        "LEFT JOIN chat_logs cl ON u.id=cl.user_id AND cl.role='user' "
        "WHERE cs.class_id=? GROUP BY u.id ORDER BY messages DESC",
        (class_id,)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_analytics_top_words(user_ids, limit=20):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if user_ids:
        placeholders = ",".join("?" * len(user_ids))
        c.execute(
            f"SELECT content FROM chat_logs WHERE role='user' AND user_id IN ({placeholders})",
            tuple(user_ids)
        )
    else:
        c.execute("SELECT content FROM chat_logs WHERE role='user'")
    rows = c.fetchall()
    conn.close()
    stop = {"the", "a", "an", "is", "in", "it", "of", "to", "and", "or", "for", "with",
            "this", "that", "what", "how", "why", "can", "i", "my", "me", "do", "does",
            "did", "be", "are", "was", "were", "please", "help", "have", "has", "had",
            "will", "would", "could", "should", "if", "so", "about", "from", "on", "at",
            "by", "we", "you", "they", "he", "she", "not", "but", "get"}
    freq = {}
    for (text,) in rows:
        for w in re.findall(r"[a-zA-Z]{3,}", text.lower()):
            if w not in stop:
                freq[w] = freq.get(w, 0) + 1
    return sorted(freq.items(), key=lambda x: x[1], reverse=True)[:limit]


def get_analytics_totals(user_ids):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if user_ids:
        placeholders = ",".join("?" * len(user_ids))
        c.execute(
            f"SELECT COUNT(*) as messages, COALESCE(SUM(token_estimate),0) as tokens, "
            f"COUNT(DISTINCT session_id) as sessions FROM chat_logs "
            f"WHERE role='user' AND user_id IN ({placeholders})",
            tuple(user_ids)
        )
    else:
        c.execute(
            "SELECT COUNT(*) as messages, COALESCE(SUM(token_estimate),0) as tokens, "
            "COUNT(DISTINCT session_id) as sessions FROM chat_logs WHERE role='user'"
        )
    row = c.fetchone()
    conn.close()
    return dict(row) if row else {"messages": 0, "tokens": 0, "sessions": 0}


def get_sessions_for_student(user_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT session_id, MIN(created_at) as started_at, COUNT(*) as msg_count, "
        "MAX(CASE WHEN role='user' THEN content ELSE '' END) as last_user_msg "
        "FROM chat_logs WHERE user_id=? GROUP BY session_id ORDER BY started_at DESC",
        (user_id,)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# System image helpers
# ---------------------------------------------------------------------------

SYSTEM_DIR = os.path.join("data", "system")


def save_system_image(name, file_bytes, ext):
    os.makedirs(SYSTEM_DIR, exist_ok=True)
    for f in os.listdir(SYSTEM_DIR):
        if f.startswith(name + "."):
            try:
                os.remove(os.path.join(SYSTEM_DIR, f))
            except OSError:
                pass
    path = os.path.join(SYSTEM_DIR, f"{name}.{ext}")
    with open(path, "wb") as fh:
        fh.write(file_bytes)
    return path


def get_system_image_path(name):
    if not os.path.exists(SYSTEM_DIR):
        return None
    for f in os.listdir(SYSTEM_DIR):
        base, ext = os.path.splitext(f)
        if base == name and ext.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
            return os.path.join(SYSTEM_DIR, f)
    return None


def get_system_image_b64(name):
    import base64
    import mimetypes
    path = get_system_image_path(name)
    if not path:
        return None
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as fh:
        data = base64.b64encode(fh.read()).decode()
    return f"data:{mime};base64,{data}"
