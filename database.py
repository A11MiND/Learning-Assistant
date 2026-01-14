import sqlite3
import hashlib
import os
from datetime import datetime

DB_FILE = "dse_ai.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Users Table
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
    
    # Deployments Table (for tracking ports and PIDs)
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
    
    # Seed Teacher Account if not exists
    c.execute("SELECT * FROM users WHERE role='teacher'")
    if not c.fetchone():
        create_user("teacher", "admin", "teacher", "Teacher Admin")
        
    # Check for account_status column (Migration)
    try:
        c.execute("SELECT account_status FROM users LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE users ADD COLUMN account_status TEXT DEFAULT 'active'")
        
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
