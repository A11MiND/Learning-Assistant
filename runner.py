import streamlit as st
import sys
import os
import json
import requests
import uuid
import socket
from datetime import datetime
import database
import rag_utils
from openai import OpenAI

# ---- OpenAI-compatible model API helpers ----

def call_model_api(model, messages):
    """
    Multi-turn chat call.
    model: dict with api_url, api_key, model_name, system_prompt, override_prompt (optional)
    messages: list of {"role": ..., "content": ...}
    """
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
    """Single-turn convenience wrapper."""
    return call_model_api(model, [{"role": "user", "content": prompt}])

# --- Constants ---
DATA_DIR = "data"

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
DEFAULT_ANY_LLM_URL = f"http://{SERVER_IP}:3001/api/v1"

# --- Helper Functions ---
def get_user_dir(username):
    return os.path.join(DATA_DIR, username)

def load_config(username):
    config_file = os.path.join(get_user_dir(username), "config.json")
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def load_session(username, session_id):
    history_dir = os.path.join(get_user_dir(username), "history")
    file_path = os.path.join(history_dir, f"{session_id}.json")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("messages", []), data.get("title", "New Chat")
    except:
        return [], "New Chat"

def delete_session(username, session_id):
    history_dir = os.path.join(get_user_dir(username), "history")
    file_path = os.path.join(history_dir, f"{session_id}.json")
    if os.path.exists(file_path):
        os.remove(file_path)
        return True
    return False

def save_image(username, image_bytes):
    images_dir = os.path.join(get_user_dir(username), "images")
    os.makedirs(images_dir, exist_ok=True)
    filename = f"{uuid.uuid4()}.png"
    file_path = os.path.join(images_dir, filename)
    with open(file_path, "wb") as f:
        f.write(image_bytes)
    return filename

def get_image_path(username, filename):
    return os.path.join(get_user_dir(username), "images", filename)

def save_session(username, session_id, messages):
    if not messages: return
    
    title = "New Chat"
    for msg in messages:
        if msg["role"] == "user":
            title = msg["content"][:30] + "..." if len(msg["content"]) > 30 else msg["content"]
            break
            
    history_dir = os.path.join(get_user_dir(username), "history")
    os.makedirs(history_dir, exist_ok=True)
    file_path = os.path.join(history_dir, f"{session_id}.json")
    
    messages_to_save = []
    for msg in messages:
        msg_copy = msg.copy()
        if "image_data" in msg_copy: 
             del msg_copy["image_data"] # Don't save bytes to JSON
        messages_to_save.append(msg_copy)
        
    data = {
        "id": session_id,
        "title": title,
        "updated_at": datetime.now().isoformat(),
        "messages": messages_to_save
    }
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- Notebook Functions (JSON Based) ---
def get_notebook_path(username):
    return os.path.join(get_user_dir(username), "notebook.json")

def load_notebook(username):
    path = get_notebook_path(username)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return []

def save_notebook(username, notebook_data):
    path = get_notebook_path(username)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(notebook_data, f, ensure_ascii=False, indent=2)

def add_to_notebook(username, question, answer, summary=None):
    notebook = load_notebook(username)
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "title": summary[:50] if summary else question[:50],
        "question": question,
        "answer": answer,
        "summary": summary
    }
    notebook.append(entry)
    save_notebook(username, notebook)

def delete_notebook_entry(username, entry_id):
    notebook = load_notebook(username)
    notebook = [n for n in notebook if n['id'] != entry_id]
    save_notebook(username, notebook)

def update_notebook_entry_title(username, entry_id, new_title):
    notebook = load_notebook(username)
    for n in notebook:
        if n['id'] == entry_id:
            n['title'] = new_title
            break
    save_notebook(username, notebook)

def call_ollama_vision(base_url, model_name, image_bytes, prompt):
    """Kept for backward compatibility — prefer call_model_api for new code."""
    url = f"{base_url}/api/generate"
    import base64
    img_b64 = base64.b64encode(image_bytes).decode('utf-8')
    payload = {
        "model": model_name,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False
    }
    try:
        response = requests.post(url, json=payload, timeout=180)
        response.raise_for_status()
        return response.json().get("response", "")
    except Exception as e:
        return f"[Vision Error]: {str(e)}"

# --- Main Execution ---

# Parse Command Line Arguments to get User ID
# Usage: streamlit run runner.py -- user_id=123
user_id_arg = None
for arg in sys.argv:
    if arg.startswith("user_id="):
        user_id_arg = arg.split("=")[1]
        break

if not user_id_arg:
    st.error("No User ID provided. This app must be launched from the main platform.")
    st.stop()

# Load User Data
user = database.get_user_by_id(user_id_arg)
if not user:
    st.error("User not found.")
    st.stop()

username = user["username"]
config = load_config(username)

# App Config
app_title = config.get("app_title", f"{user['name']}'s AI Tutor")
st.set_page_config(page_title=app_title, layout="wide")

# --- UI ---
st.title(app_title)

# Sidebar (History + model selector)
with st.sidebar:
    # model selector: show only allowed models for this student
    allowed_models = database.get_allowed_models_for_student(user['id'])
    if allowed_models:
        sel = config.get('model_id')
        options = {m['id']: m['name'] for m in allowed_models}
        idx = 0
        if sel in options:
            idx = list(options.keys()).index(sel)
        choice = st.selectbox("Model", options.keys(), format_func=lambda i: options[i], index=idx)
        if choice != sel:
            config['model_id'] = choice
            save_config(username, config)
    else:
        st.write("No models assigned by teacher.")
    
    st.header("Chat History")
    if st.button("New Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()
        
    # Load History
    import glob
    history_dir = os.path.join(get_user_dir(username), "history")
    if os.path.exists(history_dir):
        files = glob.glob(os.path.join(history_dir, "*.json"))
        files.sort(key=os.path.getmtime, reverse=True)
        for fpath in files:
            fname = os.path.basename(fpath)
            sid = fname.replace(".json", "")
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    title = meta.get("title", "Untitled Chat")
            except:
                title = "Corrupted"
            
            # Using columns for Chat Title and Delete Button
            col1, col2 = st.columns([4, 1])
            with col1:
                # Truncate title for button
                btn_title = title if len(title) < 20 else title[:17] + "..."
                if st.button(f"{btn_title}", key=f"open_{sid}", use_container_width=True, help=title):
                    msgs, _ = load_session(username, sid)
                    st.session_state.messages = msgs
                    st.session_state.session_id = sid
                    st.rerun()
            with col2:
                if st.button("Delete", key=f"del_{sid}"):
                    delete_session(username, sid)
                    if st.session_state.get('session_id') == sid:
                        st.session_state.messages = []
                        st.session_state.session_id = str(uuid.uuid4())
                    st.rerun()

# Determine active model (needed across tabs)
current_model = None
if config.get('model_id'):
    for m in allowed_models:
        if m['id'] == config['model_id']:
            current_model = m
            break
if not current_model and allowed_models:
    current_model = allowed_models[0]

# RAG knowledge base toggle (sidebar — visible in all tabs)
docs = database.get_documents()
indexed_docs = [d for d in docs if d['index_status'] == 'indexed']
if indexed_docs and current_model:
    with st.sidebar:
        use_rag = st.toggle("Use Knowledge Base", value=False, key="use_rag")
        if use_rag:
            doc_names = {d['id']: d['name'] for d in indexed_docs}
            st.selectbox(
                "Document", list(doc_names.keys()),
                format_func=lambda i: doc_names[i], key="rag_doc"
            )

# Tabs
tab_chat, tab_practice, tab_notebook = st.tabs(["Chat", "Practice", "Notebook"])

with tab_chat:
    # Chat UI
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "image_path" in msg:
                img_path = get_image_path(username, msg["image_path"])
                if os.path.exists(img_path):
                    st.image(img_path, width=300)

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
            # Inject RAG context if enabled
            rag_inject = ""
            if indexed_docs and current_model and st.session_state.get("rag_doc"):
                sel_doc = next((d for d in indexed_docs if d['id'] == st.session_state["rag_doc"]), None)
                if sel_doc and sel_doc.get('index_path'):
                    rag_inject = rag_utils.retrieve_context(sel_doc['index_path'], user_input)

            # Build message list
            chat_messages = [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages
            ]
            # Prepend RAG as a system context block if available
            if rag_inject:
                chat_messages[-1]["content"] = (
                    f"[Relevant document context:]\n{rag_inject}\n\n"
                    f"[Student question:] {user_input}"
                )
            response_text = call_model_api(current_model, chat_messages)
        else:
            response_text = "[No model assigned. Ask your teacher to grant model access.]"

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

with tab_practice:
    st.header("Practice Questions")

    # Section 1: Teacher-assigned questions
    assigned_qs = database.get_questions_for_student(user['id'])
    if assigned_qs:
        st.subheader("Assigned by Teacher")
        for q in assigned_qs:
            with st.expander(f"[{q['question_type']}] {q.get('doc_name','')}"):
                st.markdown(q['question'])
        st.markdown("---")

    # Section 2: Generate from notebook
    st.subheader("Generate from My Notebook")
    st.write("Select notebook entries to generate targeted practice questions.")

    notebook = load_notebook(username)
    if not notebook:
        st.info("Your notebook is empty. Add entries from Chat first.")
    else:
        notebook.sort(key=lambda x: x['timestamp'], reverse=True)
        options = {e['id']: f"{e['title']} ({e['timestamp'][:10]})" for e in notebook}
        selected_ids = st.multiselect(
            "Select entries:", list(options.keys()),
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
                selected_entries = [n for n in notebook if n['id'] in selected_ids]
                context_text = ""
                for entry in selected_entries:
                    context_text += (
                        f"\n---\nTopic: {entry['title']}\n"
                        f"Key Point: {entry.get('summary','')}\n"
                        f"Original Q: {entry['question']}\n"
                    )
                type_str = ", ".join(q_types)
                prompt = (
                    f"Based on these student notebook entries, generate 3 practice questions "
                    f"for EACH of these types: {type_str}.\n"
                    f"Format: number each question, label the type, and include the answer.\n"
                    f"For Multiple Choice: provide 4 options (A-D) and mark the correct answer.\n"
                    f"For Fill-in-the-blank: use ___ and provide the answer.\n"
                    f"For True/False: state the verdict clearly.\n\n"
                    f"Notebook entries:\n{context_text}"
                )
                with st.spinner("Generating..."):
                    questions = call_model_api_single(current_model, prompt)
                st.markdown(questions)

with tab_notebook:
    st.header("Your Notebook")

    notebook = load_notebook(username)
    if not notebook:
        st.info("No entries yet.")
    else:
        notebook.sort(key=lambda x: x['timestamp'], reverse=True)
        for entry in notebook:
            with st.expander(f"{entry['title']} - {entry['timestamp'][:16]}"):
                new_title = st.text_input("Title", value=entry['title'], key=f"title_{entry['id']}")
                if new_title != entry['title']:
                    update_notebook_entry_title(username, entry['id'], new_title)
                    st.rerun()

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Original Question**")
                    st.info(entry['question'])
                with col2:
                    st.markdown("**Original Answer**")
                    st.info(entry['answer'])

                if entry.get('summary'):
                    st.markdown("**Key Learning / Summary**")
                    st.warning(entry['summary'])

                if st.button("Delete Entry", key=f"del_note_{entry['id']}"):
                    delete_notebook_entry(username, entry['id'])
                    st.rerun()

    if st.button("Refresh Notebook"):
        st.rerun()
