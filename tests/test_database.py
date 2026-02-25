import os
import sqlite3
import tempfile
import pytest

import database
from database import (
    init_db,
    create_model,
    get_models,
    update_model,
    delete_model,
    create_user,
    set_student_model_access,
    get_allowed_models_for_student,
)

# use temp db file to avoid conflicts
@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    fd, path = tempfile.mkstemp()
    os.close(fd)
    monkeypatch.setattr('database.DB_FILE', path)
    init_db()
    yield
    os.remove(path)


def test_model_crud():
    assert create_model('m1', 'http://example.com')
    models = get_models()
    assert len(models) == 1
    m = models[0]
    assert m['name'] == 'm1'
    update_model(m['id'], name='mx')
    models = get_models()
    assert models[0]['name'] == 'mx'
    delete_model(m['id'])
    assert get_models() == []


def test_student_access():
    create_model('m1', 'http://example.com')
    m = get_models()[0]
    create_user('stu', 'pw', 'student', 'Stu')
    # get student id
    conn = sqlite3.connect(database.DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", ('stu',))
    sid = c.fetchone()[0]
    conn.close()
    set_student_model_access(sid, m['id'], True)
    allowed = get_allowed_models_for_student(sid)
    assert len(allowed) == 1
    assert allowed[0]['name'] == 'mx' or allowed[0]['name'] == 'm1'
