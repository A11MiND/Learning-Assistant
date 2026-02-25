import streamlit as st
import sys
import os
import json
import requests
import uuid
import socket
from datetime import datetime
import database

# helper similar to main app

def call_model_api(model, user_input):
    prompt = user_input
    if model.get("system_prompt"):
        prompt = model["system_prompt"] + "\n\n" + user_input
    headers = {"Content-Type": "application/json"}
    if model.get("api_key"):
        headers["Authorization"] = f"Bearer {model['api_key']}"
    payload = {"prompt": prompt}
    try:
        resp = requests.post(model["api_url"], json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response") or data.get("output") or data.get("text") or str(data)
    except Exception as e:
        return f"[Model Error]: {e}"

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

def call_anythingllm_chat(base_url, api_key, slug, message, mode="chat"):
    url = f"{base_url}/workspace/{slug}/chat"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"message": message, "mode": mode}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data.get("textResponse", data.get("response", "No response text found."))
    except Exception as e:
        return f"[RAG Error]: {str(e)}"

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

# Tabs
tab_chat, tab_practice, tab_notebook = st.tabs(["Chat", "Practice", "Notebook"])

with tab_chat:
    # Chat Logic
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "image_path" in msg: # Load from persistent storage
                 img_path = get_image_path(username, msg["image_path"])
                 if os.path.exists(img_path):
                     st.image(img_path, width=300)
            elif "image" in msg: # Temporary session image (fallback)
                st.image(msg["image"], width=300)
            elif msg.get("has_image"): # Old fallback
                st.caption("[Image from history]")

    user_input = st.chat_input("Ask your AI Tutor...")

    if user_input:
        # User Message
        with st.chat_message("user"):
            st.markdown(user_input)
            if uploaded_file:
                st.image(uploaded_file, width=300)
        
        msg_data = {"role": "user", "content": user_input}
        if uploaded_file:
            # Save image to disk and add to message
            image_bytes = uploaded_file.getvalue()
            filename = save_image(username, image_bytes)
            msg_data["image_path"] = filename
            # We don't store "image" bytes in session state logic to avoid issues, we just reload path
            
        st.session_state.messages.append(msg_data)
        
        # AI Response
        response_text = ""
        # determine model from config
        model = None
        if config.get('model_id'):
            models = database.get_models()
            for m in models:
                if m['id'] == config['model_id']:
                    model = m
                    break
        if not model:
            # fallback first model
            ms = database.get_models()
            model = ms[0] if ms else None
        if uploaded_file:
            # legacy image support: prepend description
            image_bytes = uploaded_file.getvalue()
            desc_prompt = "Describe this image in detail."
            img_desc = call_model_api(model, desc_prompt) if model else ""
            rag_prompt = f"Image description: {img_desc}\nUser question: {user_input}"
            response_text = call_model_api(model, rag_prompt) if model else "[No model configured]"
        else:
            response_text = call_model_api(model, user_input) if model else "[No model configured]"
        
        with st.chat_message("assistant"):
            st.markdown(response_text)
        
        st.session_state.messages.append({"role": "assistant", "content": response_text})
        save_session(username, st.session_state.session_id, st.session_state.messages)
        
        # Store last Q&A for Notebook
        st.session_state.last_qa = (user_input, response_text)
        st.rerun()

    # Add to Notebook Button (outside the loop, checks state)
    if "last_qa" in st.session_state:
        q, a = st.session_state.last_qa
        if st.button("Add Last Q&A to Notebook"):
            with st.spinner("Analyzing mistake and summarizing..."):
                summary_prompt = f"Analyze this student's question and the answer. Summarize the key mistake the student might have made or the key concept they need to remember. Be concise.\n\nQuestion: {q}\nAnswer: {a}"
                summary = call_anythingllm_chat(
                    config.get("url", DEFAULT_ANY_LLM_URL),
                    config.get("api_key", ""),
                    config.get("slug", "default"),
                    summary_prompt
                )
                add_to_notebook(username, q, a, summary)
            st.success("Added to Notebook with AI Summary!")
            del st.session_state.last_qa # Clear after adding

with tab_practice:
    st.header("Generate Practice Questions")
    st.write("Select topics from your notebook to generate questions.")
    
    notebook = load_notebook(username)
    if not notebook:
        st.info("Your notebook is empty. Add some entries first!")
    else:
        # Sort by timestamp desc
        notebook.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Selection UI
        options = {entry['id']: f"{entry['title']} ({entry['timestamp'][:10]})" for entry in notebook}
        selected_ids = st.multiselect("Select Mistake Entries to Practice:", options.keys(), format_func=lambda x: options[x])
        
        if st.button("Generate Questions"):
            if not selected_ids:
                st.warning("Please select at least one topic.")
            else:
                selected_entries = [n for n in notebook if n['id'] in selected_ids]
                # Construct context
                context_text = ""
                for entry in selected_entries:
                    context_text += f"\n---\nTopic: {entry['title']}\nMistake/Key Point: {entry['summary']}\nOriginal Q: {entry['question']}\n"
                
                with st.spinner("Generating targeted practice questions..."):
                    prompt = f"Based on these specific mistake entries from a student's notebook, generate 3 practice questions to test their understanding and help them avoid similar mistakes:\n{context_text}"
                    questions = call_anythingllm_chat(
                        config.get("url", DEFAULT_ANY_LLM_URL),
                        config.get("api_key", ""),
                        config.get("slug", "default"),
                        prompt
                    )
                    st.markdown(questions)

with tab_notebook:
    st.header("Your Notebook")
    
    notebook = load_notebook(username)
    if not notebook:
        st.info("No entries yet.")
    else:
        notebook.sort(key=lambda x: x['timestamp'], reverse=True)
        for entry in notebook:
            with st.expander(f"📌 {entry['title']} - {entry['timestamp'][:16]}"):
                # Edit Title
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
                
                st.markdown("**💡 Key Learning / Summary**")
                st.warning(entry['summary'])
                
                if st.button("Delete Entry", key=f"del_note_{entry['id']}"):
                    delete_notebook_entry(username, entry['id'])
                    st.rerun()

    if st.button("Refresh Notebook"):
        st.rerun()
