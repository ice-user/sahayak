import os

# Unit tests never download models; hybrid search is tested with a stand-in embedder.
os.environ.setdefault("SAHAYAK_SEARCH", "bm25")
# Legacy tests script one reply per LLM call; streaming (and its non-streaming fallback) is tested explicitly
# with Agent(stream=True). Tests never inherit LLM_* settings from the developer's shell.
os.environ["LLM_STREAM"] = "0"
for _name in ("LLM_EXTRA_BODY", "LLM_SYSTEM_PREFIX"):
    os.environ.pop(_name, None)
# The topic guard (extra classifier call, canned greeting replies) is tested explicitly with Agent(topic_guard=...);
# legacy tests script exactly one reply per main-model call.
os.environ["TOPIC_GUARD"] = "off"
for _name in ("TOPIC_GUARD_MODEL", "TOPIC_GUARD_TIMEOUT_S"):
    os.environ.pop(_name, None)
