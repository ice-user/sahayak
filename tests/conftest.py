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


import pytest as _pytest


@_pytest.fixture(autouse=True)
def _reset_stream_memory():
    """sahayak.llm remembers models that rejected streaming; isolate that between tests."""
    from sahayak import llm as _llm
    _llm._NO_STREAM_MODELS.clear()
    yield
    _llm._NO_STREAM_MODELS.clear()


def _symlinks_supported() -> bool:
    """Creating symlinks needs a privilege on Windows (Developer Mode or admin); Linux/macOS always can."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        try:
            (Path(d) / "link").symlink_to(Path(d))
            return True
        except (OSError, NotImplementedError):
            return False


requires_symlinks = _pytest.mark.skipif(
    not _symlinks_supported(), reason="cannot create symlinks here (Windows without Developer Mode/admin privilege)")
