from __future__ import annotations

import html
import os
import time
from typing import Any

import requests
import streamlit as st
from dotenv import load_dotenv


load_dotenv(override=False)

APP_NAME = "Construction Document RAG"
POLL_INTERVAL_SECONDS = 1.5
MAX_POLL_SECONDS = int(os.getenv("MAX_POLL_SECONDS", "180"))


def _api_base_url() -> str:
    return os.getenv("API_BASE_URL", "http://localhost:8000/v1").rstrip("/")


API_BASE_URL = _api_base_url()
DEMO_ACCESS_KEY = os.getenv("DEMO_ACCESS_KEY", "")

st.set_page_config(
    page_title=f"{APP_NAME} | Workspace",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)


APP_CSS = """
<style>
:root {
  --ink: #142033;
  --ink-soft: #526078;
  --ink-muted: #7b879a;
  --canvas: #f5f7f8;
  --paper: #ffffff;
  --sidebar: #ffffff;
  --sidebar-soft: #f4f6f8;
  --teal: #0f766e;
  --teal-dark: #0b5f59;
  --teal-soft: #e8f5f3;
  --amber: #d97706;
  --line: #e3e8ee;
  --success: #16834a;
  --danger: #c0362c;
  --warning: #a16207;
}

html, body, [class*="css"] {
  color: var(--ink);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
    sans-serif;
}

.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
  background: var(--canvas);
}

header[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
#MainMenu,
footer {
  display: none !important;
}

.main .block-container,
[data-testid="stMainBlockContainer"],
[data-testid="stAppViewBlockContainer"] {
  box-sizing: border-box;
  max-width: none !important;
  padding: 2.5rem 3.25rem 0 !important;
  width: 100% !important;
}

div[data-testid="stVerticalBlock"] {
  gap: 1rem;
}

div[data-testid="stHorizontalBlock"] {
  align-items: flex-start;
  gap: 1.5rem;
}

div[data-testid="stVerticalBlockBorderWrapper"],
div[data-testid="stVerticalBlockBorderWrapper"] > div {
  background: transparent !important;
  border: 0 !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  margin: 0 !important;
  overflow: visible !important;
  padding: 0 !important;
}

section[data-testid="stSidebar"],
section[data-testid="stSidebar"] > div {
  background: var(--sidebar);
  width: 330px !important;
}

section[data-testid="stSidebar"] {
  border-right: 1px solid var(--line);
  box-shadow: 8px 0 28px rgba(20, 32, 51, 0.035);
}

section[data-testid="stSidebar"] .block-container,
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
  box-sizing: border-box;
  max-width: none !important;
  padding: 2rem 1.4rem 2.25rem !important;
  width: 100% !important;
}

section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] {
  gap: 0.8rem;
}

section[data-testid="stSidebar"] h4,
section[data-testid="stSidebar"] strong,
section[data-testid="stSidebar"] p {
  color: var(--ink);
}

section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
  color: var(--ink-muted);
  line-height: 1.5;
}

section[data-testid="stSidebar"] hr {
  border-color: var(--line);
  margin: 1.25rem 0;
}

section[data-testid="stSidebar"] code {
  background: var(--sidebar-soft);
  border: 1px solid #ebeff3;
  border-radius: 8px;
  color: var(--ink);
  display: block;
  font-size: 0.76rem;
  overflow-wrap: anywhere;
  padding: 0.8rem 0.85rem;
  white-space: pre-wrap;
}

section[data-testid="stSidebar"] div[data-testid="stAlert"] {
  border: 0;
  border-radius: 8px;
}

.nova-brand {
  align-items: center;
  display: flex;
  gap: 0.78rem;
  margin-bottom: 1.25rem;
}

.nova-brand__mark {
  align-items: center;
  background: var(--teal);
  border-radius: 10px;
  color: #ffffff;
  display: inline-flex;
  flex: 0 0 40px;
  font-size: 0.72rem;
  font-weight: 850;
  height: 40px;
  justify-content: center;
  letter-spacing: 0.04em;
}

.nova-brand strong,
.nova-brand span {
  display: block;
}

.nova-brand strong {
  color: var(--ink);
  font-size: 0.95rem;
}

.nova-brand span {
  color: var(--ink-muted);
  font-size: 0.72rem;
  margin-top: 0.12rem;
}

.nova-side-label {
  color: var(--ink);
  font-size: 0.86rem;
  font-weight: 760;
  letter-spacing: 0;
  margin: 0.45rem 0 0.2rem;
}

.nova-side-row {
  align-items: center;
  display: flex;
  justify-content: space-between;
  min-height: 2rem;
}

.nova-side-row > span:first-child {
  color: var(--ink-soft);
  font-size: 0.78rem;
}

.nova-side-value {
  color: var(--teal-dark);
  font-size: 0.76rem;
  font-weight: 700;
  max-width: 155px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nova-side-status {
  align-items: center;
  border-radius: 999px;
  display: inline-flex;
  font-size: 0.68rem;
  font-weight: 750;
  gap: 0.35rem;
  padding: 0.34rem 0.52rem;
}

.nova-side-status::before {
  background: currentColor;
  border-radius: 50%;
  content: "";
  height: 5px;
  width: 5px;
}

.nova-side-status--ok {
  background: #e9f8ef;
  color: var(--success);
}

.nova-side-status--warn {
  background: #fff5df;
  color: var(--warning);
}

.nova-hero {
  padding: 0.25rem 0 2.35rem;
}

.nova-hero__meta {
  align-items: center;
  display: flex;
  gap: 0.7rem;
}

.nova-connection {
  align-items: center;
  color: var(--ink-muted);
  display: inline-flex;
  font-size: 0.72rem;
  font-weight: 650;
  gap: 0.35rem;
}

.nova-connection::before {
  background: currentColor;
  border-radius: 50%;
  content: "";
  height: 6px;
  width: 6px;
}

.nova-connection--ok { color: var(--success); }
.nova-connection--off { color: var(--danger); }

.nova-hero h1 {
  color: var(--ink);
  font-size: clamp(2.25rem, 4vw, 4rem);
  font-weight: 760;
  letter-spacing: -0.055em;
  line-height: 1.02;
  margin: 1.25rem 0 0;
  max-width: 920px;
}

.nova-hero p {
  color: var(--ink-soft);
  font-size: 1.02rem;
  line-height: 1.7;
  margin: 1rem 0 0;
  max-width: 780px;
}

.nova-statbar {
  background: var(--paper);
  border-radius: 14px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 2rem;
  max-width: 960px;
  overflow: hidden;
}

.nova-stat {
  padding: 1.05rem 1.2rem;
  position: relative;
}

.nova-stat + .nova-stat::before {
  background: var(--line);
  bottom: 1rem;
  content: "";
  left: 0;
  position: absolute;
  top: 1rem;
  width: 1px;
}

.nova-stat span,
.nova-stat strong,
.nova-stat small {
  display: block;
}

.nova-stat span {
  color: var(--ink-muted);
  font-size: 0.64rem;
  font-weight: 780;
  letter-spacing: 0.075em;
  text-transform: uppercase;
}

.nova-stat strong {
  color: var(--ink);
  font-size: 1.65rem;
  line-height: 1.1;
  margin-top: 0.38rem;
}

.nova-stat small {
  color: var(--ink-muted);
  font-size: 0.7rem;
  margin-top: 0.25rem;
}

div[data-testid="stTabs"] [data-baseweb="tab-list"] {
  border-bottom: 1px solid var(--line);
  gap: 1rem;
  margin: 0;
}

div[data-testid="stTabs"] button[role="tab"] {
  background: transparent;
  border-radius: 0;
  color: var(--ink-muted);
  font-size: 0.83rem;
  font-weight: 700;
  padding: 0.85rem 0.25rem;
}

div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
  color: var(--teal-dark);
}

div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
  background: var(--teal);
  height: 3px;
}

.nova-section-head {
  margin: 2.25rem 0 1.5rem;
}

.nova-section-head span {
  color: var(--teal-dark);
  font-size: 0.67rem;
  font-weight: 800;
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.nova-section-head h2 {
  color: var(--ink);
  font-size: 1.45rem;
  font-weight: 740;
  letter-spacing: -0.03em;
  margin: 0.35rem 0 0;
}

.nova-section-head p {
  color: var(--ink-muted);
  font-size: 0.84rem;
  line-height: 1.55;
  margin: 0.35rem 0 0;
  max-width: 680px;
}

.nova-action-spacer { height: 3.15rem; }
.nova-control-spacer { height: 1.8rem; }

.nova-empty {
  color: var(--ink-muted);
  margin: 1rem 0;
  padding: 0.75rem 0;
}

.nova-empty strong,
.nova-empty span {
  display: block;
}

.nova-empty strong {
  color: var(--ink);
  font-size: 0.88rem;
}

.nova-empty span {
  font-size: 0.78rem;
  margin-top: 0.18rem;
}

.nova-pipeline {
  background: #eaf2f1;
  border-radius: 14px;
  padding: 1.25rem 1.3rem;
}

.nova-pipeline__title {
  color: #174942;
  font-size: 0.78rem;
  font-weight: 780;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.nova-step {
  align-items: flex-start;
  display: flex;
  gap: 0.7rem;
  margin-top: 0.9rem;
}

.nova-step__number {
  align-items: center;
  background: #ffffff;
  border-radius: 7px;
  color: var(--teal-dark);
  display: inline-flex;
  flex: 0 0 26px;
  font-size: 0.69rem;
  font-weight: 800;
  height: 26px;
  justify-content: center;
}

.nova-step strong,
.nova-step span {
  display: block;
}

.nova-step strong {
  color: #173d39;
  font-size: 0.8rem;
}

.nova-step span {
  color: #55746f;
  font-size: 0.72rem;
  line-height: 1.45;
  margin-top: 0.08rem;
}

.nova-readiness {
  margin-top: 1.25rem;
}

.nova-readiness > div {
  align-items: center;
  display: flex;
  justify-content: space-between;
  padding: 0.36rem 0;
}

.nova-readiness span {
  color: #55746f;
  font-size: 0.75rem;
}

.nova-readiness strong {
  color: var(--success);
  font-size: 0.72rem;
}

.nova-subhead {
  color: var(--ink);
  font-size: 0.95rem;
  font-weight: 730;
  margin: 2.75rem 0 0.2rem;
}

.stButton > button {
  background: var(--paper) !important;
  border: 1px solid #ccd5df !important;
  border-radius: 8px !important;
  box-shadow: none !important;
  color: var(--ink) !important;
  font-weight: 680 !important;
  min-height: 2.6rem;
}

.stButton > button:hover {
  border-color: #72a8a2 !important;
  color: var(--teal-dark) !important;
}

.stButton > button[kind="primary"] {
  background: var(--teal) !important;
  border-color: var(--teal) !important;
  color: #ffffff !important;
}

.stButton > button[kind="primary"]:hover {
  background: var(--teal-dark) !important;
  border-color: var(--teal-dark) !important;
  color: #ffffff !important;
}

.stButton > button:disabled {
  background: #edf0f3 !important;
  border-color: #e1e6eb !important;
  color: #9aa6b4 !important;
}

div[data-testid="stSelectbox"] div[role="combobox"],
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea {
  background: var(--paper) !important;
  border-color: #ccd5df !important;
  border-radius: 8px !important;
  color: var(--ink) !important;
}

section[data-testid="stFileUploaderDropzone"] {
  background: var(--paper) !important;
  border: 1px dashed #9fb0c2 !important;
  border-radius: 12px !important;
  padding: 1.7rem 1rem !important;
}

section[data-testid="stFileUploaderDropzone"]:hover {
  background: #f2f8f7 !important;
  border-color: var(--teal) !important;
}

div[data-testid="stDataFrame"] {
  background: var(--paper);
  border-radius: 10px;
  overflow: hidden;
}

div[data-testid="stChatMessage"] {
  background: transparent;
  border: 0;
  border-radius: 0;
  box-shadow: none;
  margin: 0.8rem 0;
  padding: 0.25rem 0;
}

div[data-testid="stChatMessage"] p {
  color: var(--ink);
  line-height: 1.65;
}

div[data-testid="stChatInput"] {
  background: var(--paper) !important;
  border: 1px solid #cbd4de !important;
  border-radius: 10px !important;
  box-shadow: none;
}

.nova-citations {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.55rem;
}

.nova-citation {
  background: var(--teal-soft);
  border-radius: 999px;
  color: var(--teal-dark);
  font-size: 0.7rem;
  font-weight: 720;
  padding: 0.27rem 0.55rem;
}

div[data-testid="stExpander"] {
  background: transparent;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}

div[data-testid="stAlert"] {
  border: 0;
  border-radius: 8px;
  box-shadow: none;
}

.nova-footer {
  align-items: center;
  background: var(--paper);
  border-top: 1px solid var(--line);
  box-sizing: border-box;
  color: var(--ink-soft);
  display: flex;
  gap: 1.5rem;
  justify-content: space-between;
  margin: 5rem -3.25rem 0;
  min-height: 8rem;
  padding: 2rem 3.25rem;
  width: calc(100% + 6.5rem);
}

.nova-footer__brand {
  align-items: center;
  display: flex;
  gap: 0.8rem;
}

.nova-footer__mark {
  align-items: center;
  background: var(--teal);
  border-radius: 9px;
  color: #ffffff;
  display: inline-flex;
  flex: 0 0 38px;
  font-size: 0.7rem;
  font-weight: 850;
  height: 38px;
  justify-content: center;
}

.nova-footer strong,
.nova-footer span {
  display: block;
}

.nova-footer strong {
  color: var(--ink);
  font-size: 0.85rem;
}

.nova-footer span {
  color: var(--ink-muted);
  font-size: 0.72rem;
  margin-top: 0.15rem;
}

.nova-footer__credit {
  text-align: right;
}

.nova-footer__credit strong {
  font-size: 0.78rem;
  margin-top: 0.25rem;
}

@media (max-width: 1100px) {
  .main .block-container,
  [data-testid="stMainBlockContainer"],
  [data-testid="stAppViewBlockContainer"] {
    padding-left: 2rem !important;
    padding-right: 2rem !important;
  }

  .nova-footer {
    margin-left: -2rem;
    margin-right: -2rem;
    padding-left: 2rem;
    padding-right: 2rem;
    width: calc(100% + 4rem);
  }
}

@media (max-width: 800px) {
  section[data-testid="stSidebar"],
  section[data-testid="stSidebar"] > div {
    width: 300px !important;
  }

  .main .block-container,
  [data-testid="stMainBlockContainer"],
  [data-testid="stAppViewBlockContainer"] {
    padding: 1.5rem 1.2rem 0 !important;
  }

  div[data-testid="stHorizontalBlock"] {
    flex-direction: column;
    gap: 1rem;
  }

  div[data-testid="column"] {
    flex: 1 1 100% !important;
    min-width: 100% !important;
    width: 100% !important;
  }

  .nova-statbar {
    grid-template-columns: 1fr;
  }

  .nova-stat + .nova-stat::before {
    bottom: auto;
    height: 1px;
    left: 1rem;
    right: 1rem;
    top: 0;
    width: auto;
  }

  .nova-action-spacer,
  .nova-control-spacer {
    display: none;
  }

  .nova-footer {
    margin-left: -1.2rem;
    margin-right: -1.2rem;
    padding-left: 1.2rem;
    padding-right: 1.2rem;
    width: calc(100% + 2.4rem);
  }
}

@media (max-width: 600px) {
  .nova-hero h1 {
    font-size: 2.25rem;
  }

  .nova-footer {
    align-items: flex-start;
    flex-direction: column;
    gap: 1.25rem;
  }

  .nova-footer__credit {
    text-align: left;
  }
}
</style>
"""


def _headers() -> dict[str, str]:
    return {"X-Demo-Key": DEMO_ACCESS_KEY} if DEMO_ACCESS_KEY else {}


def api_get(path: str) -> dict[str, Any]:
    response = requests.get(f"{API_BASE_URL}{path}", headers=_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


def api_post(path: str, **kwargs: Any) -> dict[str, Any]:
    headers = {**_headers(), **kwargs.pop("headers", {})}
    response = requests.post(f"{API_BASE_URL}{path}", headers=headers, timeout=120, **kwargs)
    response.raise_for_status()
    return response.json()


def api_delete(path: str) -> dict[str, Any]:
    response = requests.delete(f"{API_BASE_URL}{path}", headers=_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


def list_documents() -> list[dict[str, Any]]:
    return api_get("/documents").get("documents", [])


def backend_health() -> bool:
    try:
        return api_get("/admin/health").get("status") == "ok"
    except requests.RequestException:
        return False


def poll_status(document_id: str) -> dict[str, Any]:
    return api_get(f"/documents/{document_id}/status")


def chat_history(document_id: str) -> list[dict[str, Any]]:
    return api_get(f"/documents/{document_id}/chat/history").get("history", [])


def configured(variable: str) -> bool:
    value = os.getenv(variable, "").strip()
    return bool(value) and not value.lower().startswith(("replace_", "your_"))


def request_error(exc: requests.RequestException) -> str:
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if payload.get("message"):
            return str(payload["message"])
    return "The request failed. Confirm that the API is running and review its logs."


def render_sidebar_status(label: str, ready: bool) -> None:
    state = "ok" if ready else "warn"
    text = "Ready" if ready else "Configure"
    st.markdown(
        f"""
        <div class="nova-side-row">
          <span>{html.escape(label)}</span>
          <span class="nova-side-status nova-side-status--{state}">{text}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar(online: bool, documents: list[dict[str, Any]]) -> None:
    provider = os.getenv("LLM_PROVIDER", "openai").strip() or "openai"
    model = os.getenv("LLM_MODEL", "").strip() or "Not configured"
    embedding_ready = configured("OPENAI_API_KEY")
    provider_key = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    answer_ready = configured(provider_key) and model != "Not configured"

    with st.sidebar:
        st.markdown(
            """
            <div class="nova-brand">
              <div class="nova-brand__mark">CD</div>
              <div><strong>Workspace Console</strong><span>Local document operations</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<div class='nova-side-label'>Connection</div>", unsafe_allow_html=True)
        st.caption("FastAPI service used by this workspace")
        st.code(API_BASE_URL, language="text")
        if online:
            st.success("FastAPI connected")
        else:
            st.error("FastAPI unavailable")
            if st.button("Check connection", use_container_width=True):
                st.rerun()

        st.divider()
        st.markdown("<div class='nova-side-label'>Configuration</div>", unsafe_allow_html=True)
        st.caption("Loaded from the project `.env` file")
        render_sidebar_status("Embeddings", embedding_ready)
        render_sidebar_status("Answer model", answer_ready)
        st.markdown(
            f"""
            <div class="nova-side-row"><span>Provider</span><span class="nova-side-value">{html.escape(provider)}</span></div>
            <div class="nova-side-row"><span>Model</span><span class="nova-side-value">{html.escape(model)}</span></div>
            <div class="nova-side-row"><span>Documents</span><span class="nova-side-value">{len(documents)}</span></div>
            """,
            unsafe_allow_html=True,
        )

        st.divider()
        st.caption("Use synthetic or non-confidential files when demonstrating this workspace.")


def render_hero(online: bool, documents: list[dict[str, Any]]) -> None:
    completed = sum(document.get("status") == "completed" for document in documents)
    active = sum(document.get("status") in {"pending", "processing"} for document in documents)
    connection_class = "ok" if online else "off"
    connection_label = "API connected" if online else "API offline"
    st.markdown(
        f"""
        <header class="nova-hero">
          <div class="nova-hero__meta">
            <span class="nova-connection nova-connection--{connection_class}">{connection_label}</span>
          </div>
          <h1>Turn construction documents into cited answers.</h1>
          <p>
            Upload a technical PDF, build a local semantic index, and ask focused questions
            with page-level evidence you can verify against the source.
          </p>
          <div class="nova-statbar">
            <div class="nova-stat"><span>Documents</span><strong>{len(documents)}</strong><small>Registered locally</small></div>
            <div class="nova-stat"><span>Searchable</span><strong>{completed}</strong><small>Indexes ready</small></div>
            <div class="nova-stat"><span>Processing</span><strong>{active}</strong><small>Active jobs</small></div>
          </div>
        </header>
        """,
        unsafe_allow_html=True,
    )


def render_citations(citations: list[dict[str, Any]]) -> None:
    if not citations:
        return
    chips = "".join(
        f"<span class='nova-citation'>Page {html.escape(str(item.get('page_number', '—')))}</span>"
        for item in citations[:8]
    )
    st.markdown(f"<div class='nova-citations'>{chips}</div>", unsafe_allow_html=True)
    with st.expander(f"Inspect retrieved evidence ({len(citations)})", expanded=False):
        for index, item in enumerate(citations, start=1):
            page = item.get("page_number", "—")
            score = item.get("score")
            score_text = f" · relevance {float(score):.3f}" if score is not None else ""
            st.markdown(f"**Source {index} · Page {page}{score_text}**")
            st.caption(str(item.get("excerpt") or "No excerpt available."))
            if index < len(citations):
                st.divider()


def render_pipeline() -> None:
    embedding_status = "Ready" if configured("OPENAI_API_KEY") else "Configure"
    provider = os.getenv("LLM_PROVIDER", "openai").strip() or "openai"
    provider_key = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    answer_ready = configured(provider_key) and bool(os.getenv("LLM_MODEL", "").strip())
    answer_status = "Ready" if answer_ready else "Configure"
    st.markdown(
        f"""
        <aside class="nova-pipeline">
          <div class="nova-pipeline__title">Processing pipeline</div>
          <div class="nova-step"><span class="nova-step__number">01</span><div><strong>Validate</strong><span>Check PDF type, signature, size, encryption, and page count.</span></div></div>
          <div class="nova-step"><span class="nova-step__number">02</span><div><strong>Extract</strong><span>Read embedded text or use the configured OCR service.</span></div></div>
          <div class="nova-step"><span class="nova-step__number">03</span><div><strong>Index</strong><span>Chunk content, create embeddings, and persist a FAISS index.</span></div></div>
          <div class="nova-step"><span class="nova-step__number">04</span><div><strong>Answer</strong><span>Retrieve evidence and generate an answer with page citations.</span></div></div>
          <div class="nova-readiness">
            <div><span>Embeddings</span><strong>{embedding_status}</strong></div>
            <div><span>Answer model</span><strong>{answer_status}</strong></div>
          </div>
        </aside>
        """,
        unsafe_allow_html=True,
    )


def process_upload(uploaded: Any) -> None:
    with st.status("Creating document workspace", expanded=True) as status:
        status.update(label="Uploading and validating PDF", state="running")
        try:
            result = api_post(
                "/documents",
                files={"file": (uploaded.name, uploaded.getvalue(), "application/pdf")},
            )
        except requests.RequestException as exc:
            status.update(label="Upload failed", state="error")
            st.error(request_error(exc))
            return

        document_id = result["id"]
        status.update(label="Extracting, embedding, and indexing", state="running")
        st.caption(f"Document ID: `{document_id}`")
        progress = st.progress(0)
        message = st.empty()
        deadline = time.monotonic() + MAX_POLL_SECONDS
        current: dict[str, Any] = {"status": "pending", "progress": 0}

        while time.monotonic() < deadline:
            try:
                current = poll_status(document_id)
            except requests.RequestException:
                status.update(label="Status check interrupted", state="error")
                st.error("The API became unavailable while processing the document.")
                return
            progress.progress(int(current.get("progress", 0)))
            message.info(current.get("message") or current.get("status"))
            if current.get("status") in {"completed", "failed"}:
                break
            time.sleep(POLL_INTERVAL_SECONDS)

        if current.get("status") == "completed":
            status.update(label="Document ready", state="complete")
            st.success("The document is searchable. Open Ask & cite to query it.")
        elif current.get("status") == "failed":
            status.update(label="Processing failed", state="error")
            st.error(current.get("message") or "Document processing failed.")
        else:
            status.update(label="Polling window ended", state="error")
            st.warning("The job may still be running. Refresh the workspace to inspect it.")


def render_document_table(documents: list[dict[str, Any]]) -> None:
    if not documents:
        return
    rows = [
        {
            "Document": document.get("filename", ""),
            "Status": str(document.get("status", "")).title(),
            "Pages": document.get("pages") or "—",
            "Chunks": document.get("chunks") or "—",
        }
        for document in documents
    ]
    st.markdown("<div class='nova-subhead'>Workspace documents</div>", unsafe_allow_html=True)
    st.dataframe(rows, hide_index=True, use_container_width=True)


def render_failed_jobs(documents: list[dict[str, Any]]) -> None:
    failed = [document for document in documents if document.get("status") == "failed"]
    if not failed:
        return
    st.markdown("<div class='nova-subhead'>Needs attention</div>", unsafe_allow_html=True)
    st.caption(f"{len(failed)} failed document(s) can be retried from their validated source PDF.")
    for index, document in enumerate(failed):
        text_col, action_col = st.columns([5, 1])
        with text_col:
            st.markdown(f"**{html.escape(str(document.get('filename', 'Document')))}**")
            st.caption(document.get("message") or "Processing failed.")
        with action_col:
            if st.button("Retry", key=f"retry-{document['id']}", use_container_width=True):
                try:
                    api_post(f"/documents/{document['id']}/reprocess")
                except requests.RequestException as exc:
                    st.error(request_error(exc))
                else:
                    st.success("Retry queued.")
                    st.rerun()
        if index < len(failed) - 1:
            st.divider()


def render_ingestion(online: bool, documents: list[dict[str, Any]]) -> None:
    title_col, action_col = st.columns([4, 1])
    with title_col:
        st.markdown(
            """
            <div class="nova-section-head">
              <span>01 · Ingest</span>
              <h2>Create a searchable document workspace</h2>
              <p>Choose a readable, unencrypted PDF and follow extraction and indexing progress.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with action_col:
        st.markdown("<div class='nova-action-spacer'></div>", unsafe_allow_html=True)
        if st.button("Refresh", use_container_width=True):
            st.rerun()

    upload_col, pipeline_col = st.columns([1.6, 1], gap="large")
    with upload_col:
        uploaded = st.file_uploader(
            "Construction PDF",
            type=["pdf"],
            disabled=not online,
            help="Default limit: 25 MiB and 500 pages.",
        )
        if not online:
            st.error("Start the FastAPI backend to enable uploads.")
        elif uploaded is None:
            st.markdown(
                "<div class='nova-empty'><strong>No PDF selected</strong>"
                "<span>Select a construction document to begin.</span></div>",
                unsafe_allow_html=True,
            )
        if st.button(
            "Upload and process",
            type="primary",
            disabled=uploaded is None or not online,
            use_container_width=True,
        ):
            process_upload(uploaded)

    with pipeline_col:
        render_pipeline()

    render_document_table(documents)
    render_failed_jobs(documents)


def render_chat(online: bool, documents: list[dict[str, Any]]) -> None:
    st.markdown(
        """
        <div class="nova-section-head">
          <span>02 · Ask & cite</span>
          <h2>Interrogate a completed document</h2>
          <p>Select one document, ask a focused question, and inspect the evidence behind the answer.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not online:
        st.error("Document chat is unavailable while the backend is offline.")
        return

    completed = [document for document in documents if document.get("status") == "completed"]
    if not completed:
        st.markdown(
            "<div class='nova-empty'><strong>No searchable documents</strong>"
            "<span>Complete a document in the Ingest tab first.</span></div>",
            unsafe_allow_html=True,
        )
        return

    labels = {
        f"{document['filename']} · {document['id']}": document for document in completed
    }
    options = list(labels)
    previous = st.session_state.get("nova_selected_document")
    index = options.index(previous) if previous in labels else 0
    select_col, clear_col = st.columns([4, 1])
    with select_col:
        selection = st.selectbox("Active document", options, index=index)
    document = labels[selection]
    st.session_state["nova_selected_document"] = selection
    with clear_col:
        st.markdown("<div class='nova-control-spacer'></div>", unsafe_allow_html=True)
        if st.button("Clear history", use_container_width=True):
            try:
                api_delete(f"/documents/{document['id']}/chat/history")
            except requests.RequestException as exc:
                st.error(request_error(exc))
            else:
                st.rerun()

    try:
        history = chat_history(document["id"])
    except requests.RequestException as exc:
        st.error(request_error(exc))
        return

    if not history:
        st.markdown(
            "<div class='nova-empty'><strong>Conversation ready</strong>"
            "<span>Ask about costs, materials, quantities, specifications, or requirements.</span></div>",
            unsafe_allow_html=True,
        )
    for message in history:
        role = message.get("role", "assistant")
        with st.chat_message("user" if role == "user" else "assistant"):
            st.markdown(message.get("content", "") or "")
            if role != "user":
                render_citations((message.get("metadata") or {}).get("citations") or [])

    question = st.chat_input("Ask a question about the selected document")
    if not question:
        return
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Retrieving evidence and preparing a cited answer..."):
            try:
                response = api_post(
                    f"/documents/{document['id']}/query",
                    json={"question": question},
                )
            except requests.RequestException as exc:
                st.error(request_error(exc))
                return
        st.markdown(response.get("answer", "") or "No answer was returned.")
        render_citations(response.get("citations") or [])
    st.rerun()


def render_footer() -> None:
    st.markdown(
        """
        <div class="nova-footer">
          <div class="nova-footer__brand">
            <div class="nova-footer__mark">CD</div>
            <div><strong>Construction Document Intelligence</strong><span>Local retrieval with verifiable page citations</span></div>
          </div>
          <div class="nova-footer__credit">
            <strong>Developed by Muhammad Ali Nawaz 2026</strong>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.markdown(APP_CSS, unsafe_allow_html=True)

is_online = backend_health()
workspace_documents: list[dict[str, Any]] = []
if is_online:
    try:
        workspace_documents = list_documents()
    except requests.RequestException:
        is_online = False

render_sidebar(is_online, workspace_documents)
render_hero(is_online, workspace_documents)

ingest_tab, chat_tab = st.tabs(["Ingest", "Ask & cite"])
with ingest_tab:
    render_ingestion(is_online, workspace_documents)
with chat_tab:
    render_chat(is_online, workspace_documents)

render_footer()
