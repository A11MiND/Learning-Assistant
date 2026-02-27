import database
fns_needed = [
    'log_message','get_chat_logs_for_student','get_analytics_daily_counts',
    'get_analytics_per_student','get_analytics_top_words','get_analytics_totals',
    'get_sessions_for_student','save_system_image','get_system_image_path',
    'get_system_image_b64','hash_password','update_user_profile','admin_update_user',
    'update_user_status','get_all_users','get_all_teachers','get_all_students',
    'get_all_classes','get_folders','get_all_folders','create_folder','delete_folder',
    'get_allowed_models_for_student','get_rag_docs_for_model',
    'get_questions_for_student','save_generated_question',
]
missing = [f for f in fns_needed if not hasattr(database, f)]
if missing:
    print('MISSING:', missing)
else:
    print(f'All {len(fns_needed)} required functions present in database module - OK')
