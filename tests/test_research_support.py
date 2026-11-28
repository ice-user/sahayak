"""Shared helpers for the research-agent tests (no tests here): fixtures, fake LLM, PDF builder."""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from types import SimpleNamespace as NS

from research.graph import build_graph
from research.llm import LLM
from research.nodes import Deps
from sahayak.models import DATA_PATH

FIX = Path(__file__).parent / "fixtures" / "research"
SENIOR = FIX / "sample_senior_support.html"
YOUTH = FIX / "sample_youth_apprentice.html"
GIRL_TXT = FIX / "sample_girl_savings.txt"
SENIOR_URL = "https://example.org/fixtures/sample-senior-support"


class FakeClient:
    """OpenAI-compatible stand-in: returns scripted completions and records every request."""

    def __init__(self, script):
        self.script = list(script)
        self.sent: list[dict] = []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.sent.append({**kw, "messages": list(kw["messages"])})
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]  # last item repeats
        if isinstance(item, Exception):
            raise item
        text = item if isinstance(item, str) else json.dumps(item)
        return NS(choices=[NS(message=NS(content=text))], usage=NS(total_tokens=1))


def good_senior() -> dict:
    """A correct extraction of SENIOR (every quote is verbatim in the cleaned text)."""
    return {
        "id": "sample_senior_support",
        "name": "Sample Senior Citizen Support Scheme",
        "name_evidence": "Sample Senior Citizen Support Scheme (SSCSS)",
        "ministry": "Department of Example Social Welfare",
        "level": "central", "level_evidence": "Department of Example Social Welfare",
        "category": "pension",
        "summary": "Monthly pension for people aged 60 or above from BPL households.",
        "benefits": "A monthly pension of Rs 800 paid to the bank account.",
        "benefits_evidence": ["A monthly pension of Rs 800 is paid directly to the bank account of the beneficiary."],
        "rules": [
            {"field": "age", "op": "gte", "value": 60, "reason": "Applicant must be 60 or older",
             "evidence": "The applicant must be 60 years of age or above."},
            {"field": "bpl", "op": "eq", "value": True, "reason": "Household must be Below Poverty Line",
             "evidence": "household must be Below Poverty Line (BPL)"},
        ],
        "unmapped_criteria": [{"criterion": "Must have lived in the state for at least three years",
                               "evidence": "must have lived in the state for at least three years"}],
        "documents": [{"item": "Aadhaar card", "evidence": "Aadhaar card"},
                      {"item": "Age proof", "evidence": "Age proof"}, {"item": "BPL card", "evidence": "BPL card"}],
        "how_to_apply": "Submit the application form at the Gram Panchayat office.",
        "how_to_apply_evidence": ["Submit the application form at the Gram Panchayat office."],
        "tags": ["pension", "senior"], "aliases": [],
    }


def good_youth() -> dict:
    return {
        "id": "sample_youth_apprentice", "name": "Sample Youth Apprenticeship Allowance",
        "name_evidence": "Sample Youth Apprenticeship Allowance", "ministry": "Ministry of Example Skills",
        "level": "central", "level_evidence": "Ministry of Example Skills",
        "category": "skill", "summary": "Monthly stipend for apprentices aged 18-35 from low-income families.",
        "benefits": "Stipend of Rs 6,000 per month for 12 months.",
        "benefits_evidence": ["Stipend of Rs 6,000 per month for 12 months during apprenticeship"],
        "rules": [
            {"field": "age", "op": "gte", "value": 18, "reason": "Must be at least 18",
             "evidence": "between 18 and 35 years of age"},
            {"field": "age", "op": "lte", "value": 35, "reason": "Must be 35 or younger",
             "evidence": "between 18 and 35 years of age"},
            {"field": "annual_income", "op": "lte", "value": 300000,
             "reason": "Family income must be at most Rs 3,00,000 a year",
             "evidence": "annual family income is not more than Rs 3,00,000"}],
        "unmapped_criteria": [
            {"criterion": "Must have passed Class 12", "evidence": "must have passed Class 12"},
            {"criterion": "Must belong to a Scheduled Caste or Scheduled Tribe",
             "evidence": "must belong to a Scheduled Caste or Scheduled Tribe"}],
        "documents": [], "how_to_apply": "", "tags": [], "aliases": [],
    }


def good_girl() -> dict:
    return {
        "id": "sample_girl_savings", "name": "Sample Girl Child Savings Account Scheme",
        "name_evidence": "Sample Girl Child Savings Account Scheme", "ministry": "Department of Example Finance",
        "level": "central", "level_evidence": "Department of Example Finance",
        "category": "finance", "summary": "Savings account for girl children up to 10 years old.",
        "benefits": "Interest of 8 percent per year on deposits.",
        "benefits_evidence": ["Interest of 8 percent per year is paid on deposits"],
        "rules": [{"field": "children", "op": "any_child", "value": [
            {"field": "gender", "op": "eq", "value": "female"}, {"field": "age", "op": "lte", "value": 10}],
            "reason": "Needs a girl child aged 10 or younger",
            "evidence": "a girl child who is not older than 10 years"}],
        "documents": [{"item": "Birth certificate of the girl child",
                       "evidence": "Birth certificate of the girl child"}],
        "how_to_apply": "Visit any post office with the documents.",
        "how_to_apply_evidence": ["Visit any post office with the documents."],
    }


def variant(base: dict, **changes) -> dict:
    d = copy.deepcopy(base)
    d.update(changes)
    return d


NO_ISSUES = {"issues": [], "missing_criteria": []}


# fixed 10-scheme snapshot so merge/pipeline tests stay stable as the real database grows
SCHEMES_10 = Path(__file__).parent / "fixtures" / "research" / "schemes_10.json"


def make_deps(tmp_path: Path, script, *, model="fake-model", max_attempts=3, auditor=None,
              auditor_model="fake-auditor"):
    """Deps wired to a fake extractor LLM, a separate fake auditor LLM (default: finds nothing) and temp copies
    of the database; returns (deps, extractor_client). The auditor client is ``deps.verifier_llm.client``."""
    schemes = tmp_path / "schemes.json"
    shutil.copy(SCHEMES_10, schemes)
    client = FakeClient(script)
    aud = FakeClient([NO_ISSUES] if auditor is None else auditor)
    deps = Deps(llm=LLM(client=client, model=model), verifier_llm=LLM(client=aud, model=auditor_model),
                schemes_path=schemes, candidates_dir=tmp_path / "candidates", max_attempts=max_attempts,
                allowed_dirs=[tmp_path, FIX])
    return deps, client


def make_graph(tmp_path: Path, script, **kw):
    deps, client = make_deps(tmp_path, script, **kw)
    return build_graph(deps), deps, client


def start_file(graph, path, **kw):
    """runner.start for a local file (the explicit --file path)."""
    from research import runner
    return runner.start(graph, str(path), local_file=True, **kw)


def build_pdf(lines: list[str]) -> bytes:
    """Tiny valid single-page text PDF (Helvetica), enough for pypdf to extract text."""
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = "BT /F1 12 Tf 72 720 Td 16 TL\n" + "\n".join(f"({esc(ln)}) Tj T*" for ln in lines) + "\nET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
