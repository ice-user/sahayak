"""Web chat for Sahayak.   Run:  streamlit run app.py"""
from __future__ import annotations

import json
import os

import streamlit as st

from sahayak.agent import Agent, default_trace_dir
from sahayak.tools import Toolbox

st.set_page_config(page_title="Sahayak: find government schemes", page_icon="🪔", layout="centered")

PROVIDERS = {
    "NVIDIA": ("https://integrate.api.nvidia.com/v1", os.environ.get("NVIDIA_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b")),
    "Gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.5-flash"),
    "Groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "OpenAI": ("", "gpt-4o-mini"),
    "Ollama (local)": ("http://localhost:11434/v1", "qwen2.5:7b"),
}
EXAMPLES = [
    "My mother is 62, a widow, BPL card holder, has a bank account. What can she get?",
    "मेरी 4 साल की बेटी है, उसके लिए कोई बचत योजना?",
    "Mere dadaji 74 saal ke hain, hospital ka free scheme hai kya?",
    "I'm 27, I pay income tax and have a savings account. Any insurance or pension I can join?",
]


@st.cache_resource(show_spinner="Loading scheme search…")
def get_toolbox(search_mode: str) -> Toolbox:
    return Toolbox(search_mode=search_mode)


with st.sidebar:
    st.header("Settings")
    default_provider = "NVIDIA" if os.environ.get("NVIDIA_API_KEY") and not os.environ.get("LLM_API_KEY") else "Gemini"
    provider = st.selectbox("LLM provider", list(PROVIDERS), index=list(PROVIDERS).index(default_provider))
    default_url, default_model = PROVIDERS[provider]
    use_env = provider != "NVIDIA" and os.environ.get("LLM_API_KEY")
    base_url = st.text_input("Base URL", value=(os.environ.get("LLM_BASE_URL") if use_env else None) or default_url)
    model = st.text_input("Model", value=os.environ.get("LLM_MODEL") or default_model)
    env_key = os.environ.get("NVIDIA_API_KEY", "") if provider == "NVIDIA" else os.environ.get("LLM_API_KEY", "")
    api_key = st.text_input("API key", value=env_key, type="password",
                            help="Kept in this browser session only. Use 'ollama' for local Ollama.")
    modes = ["hybrid", "bm25"]
    default_mode = os.environ.get("SAHAYAK_SEARCH", "hybrid")
    search_mode = st.radio("Search", modes, horizontal=True,
                           index=modes.index(default_mode) if default_mode in modes else 0,
                           help="hybrid = keywords + multilingual embeddings")
    show_debug = st.toggle("Show tool calls", value=True)
    if st.button("New conversation"):
        st.session_state.pop("agent", None)
        st.session_state.messages = []
        st.rerun()
    st.caption("Eligibility is decided by fixed rules in code, never by the AI. "
               "Amounts are the central share; your state may add more. Always confirm at the office.")

st.title("🪔 Sahayak")
st.write("Ask about government schemes in **English, हिन्दी, தமிழ் or Hinglish**.")

st.session_state.setdefault("messages", [])


def get_agent() -> Agent:
    cfg = (base_url, model, api_key, search_mode)
    if st.session_state.get("agent_cfg") != cfg or "agent" not in st.session_state:
        client = st.session_state.get("client_override")  # used by tests
        if client is None:
            from openai import OpenAI
            client = OpenAI(base_url=base_url or None, api_key=api_key or "missing")
        st.session_state.agent = Agent(client=client, model=model, toolbox=get_toolbox(search_mode),
                                       trace_dir=default_trace_dir())  # traces only with SAHAYAK_TRACES=1
        st.session_state.agent_cfg = cfg
    return st.session_state.agent


def render_trace(steps: list[dict]):
    llm_steps = [s for s in steps if s["kind"] == "llm"]
    total_latency = sum(s.get("latency_s") or 0 for s in llm_steps)
    tokens = sum(s.get("tokens") or 0 for s in llm_steps)
    with st.expander(f"🔧 {sum(s['kind'] == 'tool_call' for s in steps)} tool calls · "
                     f"{len(llm_steps)} LLM calls · {total_latency:.1f}s · {tokens} tokens"):
        for s in steps:
            if s["kind"] != "tool_call":
                continue
            st.markdown(f"**{s['name']}**")
            st.code(s["arguments"], language="json")
            try:
                result = json.loads(s["result"])
            except json.JSONDecodeError:
                result = s["result"]
            if s["name"] == "check_eligibility" and isinstance(result, dict) and "eligible" in result:
                cols = st.columns(3)
                cols[0].success("Eligible\n\n" + "\n".join(f"- {r['scheme_id']}" for r in result["eligible"]) or "—")
                cols[1].warning("Need info\n\n" + "\n".join(
                    f"- {r['scheme_id']}: {', '.join(r['missing_fields'])}" for r in result["need_info"]) or "—")
                cols[2].error("Not eligible\n\n" + "\n".join(f"- {r['scheme_id']}" for r in result["not_eligible"]) or "—")
            else:
                st.json(result, expanded=False)


for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if show_debug and m.get("trace"):
            render_trace(m["trace"])

if not st.session_state.messages:
    st.caption("Try one:")
    for ex in EXAMPLES:
        if st.button(ex, use_container_width=True):
            st.session_state.pending = ex
            st.rerun()

prompt = st.chat_input("Type your question…") or st.session_state.pop("pending", None)
if prompt:
    if not api_key and "client_override" not in st.session_state:
        st.error("Add an API key in the sidebar first (or 'ollama' for local Ollama).")
        st.stop()
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Checking schemes…"):
            try:
                answer, trace = get_agent().chat(prompt)
                steps = trace.steps
            except Exception as e:
                answer, steps = f"⚠️ The AI service returned an error: `{e}`", []
        st.markdown(answer)
        if show_debug and steps:
            render_trace(steps)
    st.session_state.messages.append({"role": "assistant", "content": answer, "trace": steps})
