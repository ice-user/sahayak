from sahayak.agent import NVIDIA_BASE_URL, NVIDIA_DEFAULT_MODEL, clean_answer, resolve_config

KEYS = ["LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "NVIDIA_API_KEY", "NVIDIA_MODEL"]


def _clear(monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)


def test_nvidia_key_selects_nvidia(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setenv("NVIDIA_MODEL", "nvidia/some-model")
    assert resolve_config() == (NVIDIA_BASE_URL, "nvapi-test", "nvidia/some-model")


def test_nvidia_default_model(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    assert resolve_config()[2] == NVIDIA_DEFAULT_MODEL


def test_llm_override_beats_nvidia_model(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setenv("NVIDIA_MODEL", "nvidia/a")
    monkeypatch.setenv("LLM_MODEL", "meta/llama-3.3-70b-instruct")
    assert resolve_config()[2] == "meta/llama-3.3-70b-instruct"


def test_explicit_llm_provider_wins(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setenv("LLM_API_KEY", "groq-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    assert resolve_config()[:2] == ("https://api.groq.com/openai/v1", "groq-key")


def test_clean_answer_strips_reasoning():
    assert clean_answer("<think>step 1\nstep 2</think>\nYou can get PM-JAY.") == "You can get PM-JAY."
    assert clean_answer(None) == ""
