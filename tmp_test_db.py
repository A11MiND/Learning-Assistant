import database
from database import init_db, create_user, create_model, set_student_model_access, get_allowed_models_for_student, get_models

init_db()
create_user('stud', 'pw', 'student', 'Stu')
create_user('teach', 'pw', 'teacher', 'Teach')
m1=create_model('test1','http://example.com')
m2=create_model('test2','http://example2.com',system_prompt='hello')
print('models',get_models())
conn=__import__('sqlite3').connect(database.DB_FILE)
c=conn.cursor();c.execute("SELECT id FROM users WHERE username=?",('stud',))
sid=c.fetchone()[0]
conn.close()
set_student_model_access(sid,1,True)
print('allowed for stud',get_allowed_models_for_student(sid))
