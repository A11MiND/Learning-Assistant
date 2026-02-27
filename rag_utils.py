"""
rag_utils.py — Page-based document indexing and retrieval.

Inspired by PageIndex (vectorless RAG):
  - Documents are indexed page by page, storing text and a short LLM-generated summary.
  - Retrieval ranks pages by keyword overlap against the user query, then prepends the
    top-N pages as context to the LLM prompt.
  - No vector database or local embedding model required.
"""

import os
import json
import re
import math
from datetime import datetime

DOCS_DIR = os.path.join("data", "system", "docs")


def _ensure_docs_dir():
    os.makedirs(DOCS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_pages_from_pdf(file_path):
    """Return list of {page_num, text} dicts (1-indexed)."""
    try:
        import pypdf
        reader = pypdf.PdfReader(file_path)
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            pages.append({"page_num": i + 1, "text": text.strip()})
        return pages
    except Exception as e:
        return [{"page_num": 1, "text": f"[PDF extraction error: {e}]"}]


def extract_pages_from_docx(file_path):
    """Return list of {page_num, text} dicts — DOCX has no real page breaks,
    so we chunk by paragraph groups of ~500 words."""
    try:
        from docx import Document
        doc = Document(file_path)
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        chunk_size = 40  # paragraphs per "page"
        pages = []
        for i in range(0, len(paragraphs), chunk_size):
            chunk = "\n".join(paragraphs[i:i + chunk_size])
            pages.append({"page_num": i // chunk_size + 1, "text": chunk})
        return pages if pages else [{"page_num": 1, "text": "[Empty document]"}]
    except Exception as e:
        return [{"page_num": 1, "text": f"[DOCX extraction error: {e}]"}]


def extract_pages_from_image(file_path):
    """For images, return a single page with a placeholder (requires vision LLM)."""
    return [{"page_num": 1, "text": "[Image file — use vision model to describe]",
              "is_image": True, "file_path": file_path}]


def extract_pages(file_path, file_type):
    """Dispatch extraction based on file type."""
    ft = file_type.lower()
    if ft == "pdf":
        return extract_pages_from_pdf(file_path)
    elif ft in ("docx", "doc"):
        return extract_pages_from_docx(file_path)
    elif ft in ("txt", "text"):
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            # chunk by 2000 chars
            chunks = [text[i:i + 2000] for i in range(0, len(text), 2000)]
            return [{"page_num": i + 1, "text": c} for i, c in enumerate(chunks)]
        except Exception as e:
            return [{"page_num": 1, "text": f"[Read error: {e}]"}]
    else:
        return extract_pages_from_image(file_path)


# ---------------------------------------------------------------------------
# Index building
# ---------------------------------------------------------------------------

def _tokenize(text):
    return re.findall(r"[a-z\u4e00-\u9fff0-9]+", text.lower())


def _tf_idf_score(query_tokens, page_tokens, idf):
    score = 0.0
    page_len = len(page_tokens) or 1
    tf_map = {}
    for tok in page_tokens:
        tf_map[tok] = tf_map.get(tok, 0) + 1
    for qt in query_tokens:
        tf = tf_map.get(qt, 0) / page_len
        score += tf * idf.get(qt, 1.0)
    return score


def build_page_index(file_path, file_type, model=None):
    """
    Build a page index from a document.

    Returns a dict:
    {
        "file_path": ...,
        "file_type": ...,
        "created_at": ...,
        "pages": [{"page_num": 1, "text": "...", "summary": "...", "tokens": [...]}]
    }

    If model is provided (dict with OpenAI-compatible fields), an LLM summary is
    generated for each page.  Otherwise, only the first 300 chars are stored.
    """
    pages = extract_pages(file_path, file_type)
    indexed_pages = []
    for p in pages:
        tokens = _tokenize(p["text"])
        summary = p["text"][:300].replace("\n", " ") + ("..." if len(p["text"]) > 300 else "")
        if model and p.get("text") and not p.get("is_image"):
            try:
                summary = _llm_summarize_page(model, p["text"])
            except Exception:
                pass
        indexed_pages.append({
            "page_num": p["page_num"],
            "text": p["text"],
            "summary": summary,
            "tokens": tokens,
            "is_image": p.get("is_image", False),
        })

    # Compute IDF over all pages
    doc_freq = {}
    for p in indexed_pages:
        for tok in set(p["tokens"]):
            doc_freq[tok] = doc_freq.get(tok, 0) + 1
    n = len(indexed_pages) or 1
    idf = {tok: math.log(n / df + 1) for tok, df in doc_freq.items()}

    return {
        "file_path": file_path,
        "file_type": file_type,
        "created_at": datetime.now().isoformat(),
        "page_count": len(indexed_pages),
        "idf": idf,
        "pages": indexed_pages,
    }


def _llm_summarize_page(model, text):
    """Call the teacher-configured model to summarize a page."""
    from openai import OpenAI
    client = OpenAI(
        api_key=model.get("api_key") or "not-required",
        base_url=model["api_url"]
    )
    resp = client.chat.completions.create(
        model=model.get("model_name") or "gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Summarize the following page content in 1-2 sentences for use as a search index. Be concise."},
            {"role": "user", "content": text[:3000]}
        ],
        max_tokens=150,
        timeout=30,
    )
    return resp.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Index persistence
# ---------------------------------------------------------------------------

def save_index(doc_id, index):
    """Save index JSON next to the document. Returns the path."""
    _ensure_docs_dir()
    path = os.path.join(DOCS_DIR, f"index_{doc_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    return path


def load_index(index_path):
    """Load a previously saved index JSON."""
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def retrieve_context(index_or_path, query, top_n=4, max_chars_per_page=1500):
    """
    Given a page index (dict or path to JSON) and a query string, return a
    formatted string of the most relevant pages to inject as RAG context.
    """
    if isinstance(index_or_path, str):
        index = load_index(index_or_path)
    else:
        index = index_or_path

    if not index or not index.get("pages"):
        return ""

    query_tokens = _tokenize(query)
    idf = index.get("idf", {})

    scored = []
    for p in index["pages"]:
        tokens = p.get("tokens") or _tokenize(p.get("text", ""))
        score = _tf_idf_score(query_tokens, tokens, idf)
        scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_pages = [p for _, p in scored[:top_n] if _ > 0]

    if not top_pages:
        top_pages = [p for _, p in scored[:2]]

    chunks = []
    for p in sorted(top_pages, key=lambda x: x["page_num"]):
        text = p.get("text", "")[:max_chars_per_page]
        chunks.append(f"[Page {p['page_num']}]\n{text}")

    return "\n\n---\n\n".join(chunks)
