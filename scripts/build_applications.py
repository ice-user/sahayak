"""Build data/documents.json and data/applications.json ("how to apply + be careful" records).

  python scripts/build_applications.py faq [--delay 2]   # render myscheme pages with FAQ answers expanded
                                                         #   -> data/sources/myscheme/faq/<slug>.txt (throttled)
  python scripts/build_applications.py docs              # write data/documents.json
  python scripts/build_applications.py build [--env-file ..\\source-trail\\backend\\.env] [--only ID ...]

Documents are mapped to canonical ids by alias in code; the LLM (research.llm.LLM, NVIDIA) only maps leftover
lines and extracts steps / watch-outs / FAQ / enrolment points / grievance. Every item must carry a quote that
research.application_check finds verbatim in the scheme's official page; failures are dropped and logged.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SNAPS = ROOT / "data" / "sources" / "myscheme"
FAQ_DIR = SNAPS / "faq"
DOCS_PATH = ROOT / "data" / "documents.json"
APPS_PATH = ROOT / "data" / "applications.json"
SCHEMES_PATH = ROOT / "data" / "schemes.json"

# scheme id -> myscheme slug (None: no myscheme page; the scheme's own source_url is used)
SLUGS = {"ignoaps": "nsap-ignoaps", "ignwps": "ignwps", "apy": "apy", "pmjjby": "pmjjby", "pmsby": "pmsby",
         "pmjay_senior": None, "pm_kisan": "pm-kisan", "pmuy": "pmuy", "ssy": None, "pmmvy": "pmmvy"}

# Official locator / portal pages that are only used if an HTTP GET returns 200 during the build.
LOCATORS = {"csc": "https://findmycsc.nic.in/"}
KNOWN_PORTALS = {"pmuy": "https://www.pmuy.gov.in/", "pmmvy": "https://pmmvy.wcd.gov.in/"}


# One plain sentence per (scheme, route mode). research.application_check accepts a summary only when it is a step's own
# action or its key nouns occur in the route's quotes; otherwise the route falls back to its first step.
ROUTE_SUMMARIES = {
    ("ignoaps", "online"): "Apply on the UMANG app or website with your mobile number and OTP",
    ("ignwps", "online"): "Apply on the UMANG app or website with your mobile number and OTP",
    ("pmuy", "online"): "Apply on the official website: choose your oil company and distributor",
    ("pmuy", "offline"): "Visit the gas agency with your reference number",
    ("apy", "online"): "Open an APY account online through net banking or the e-APY portal",
    ("apy", "offline"): "Visit your bank or post office to open an APY account",
    ("pm_kisan", "offline"): "Visit a CSC where the VLE fills in your registration",
    ("pmmvy", "online"): "Apply on the official website after a citizen login with your mobile number",
    ("pmjjby", "offline"): "Fill the consent form and submit it at your bank or post office",
    ("pmsby", "offline"): "Visit your bank branch and submit the PMSBY form",
    ("ssy", "offline"): "Open the account with the girl's birth certificate and a minimum deposit",
}


def finalize(sid: str, rec: dict) -> dict:
    """Code-only enrichment of a raw record: alternatives_group on documents, routes derived from the steps."""
    from research.application import assign_alternatives, derive_routes
    rec = dict(rec)
    rec["documents"] = assign_alternatives(rec.get("documents") or [])
    routes = derive_routes(rec.get("steps") or [], rec.get("portal_url"), rec.get("office"))
    for r in routes:
        r["summary"] = ROUTE_SUMMARIES.get((sid, r["mode"]), r["summary"])
    rec["routes"] = routes
    return rec


def _n(en, hi, ta, hing, aliases, how=None):
    return {"name": {"en": en, "hi": hi, "ta": ta, "hinglish": hing}, "aliases": aliases, "how_to_get": how}


_AGE_HOW = {"text": ("If you have no birth or school certificate, your ration card or voter ID (EPIC) can be used; "
                     "if you have none of these, a Medical Officer of any government hospital can issue an age "
                     "certificate."),
            "source_url": "https://www.myscheme.gov.in/schemes/ignwps"}

DOCUMENTS = {
    "aadhaar": _n("Aadhaar card", "आधार कार्ड", "ஆதார் அட்டை", "Aadhaar card",
                  ["aadhaar", "aadhar", "adhaar", "aadhaar card", "aadhar card", "aadhaar number", "aadhar number"]),
    "ration_card": _n("Ration card", "राशन कार्ड", "குடும்ப அட்டை", "Ration card",
                      ["ration card", "ration-card"]),
    "bpl_card": _n("BPL card", "बीपीएल कार्ड", "வறுமைக்கோட்டுக்கு கீழ் அட்டை", "BPL card",
                   ["bpl card", "bpl certificate", "below poverty line card"]),
    "income_certificate": _n("Income certificate", "आय प्रमाण पत्र", "வருமானச் சான்றிதழ்", "Income certificate",
                             ["income certificate", "income proof", "income declaration"]),
    "caste_certificate": _n("Caste certificate", "जाति प्रमाण पत्र", "சாதிச் சான்றிதழ்", "Caste certificate",
                            ["caste certificate", "sc/st certificate", "community certificate"]),
    "domicile_certificate": _n("Domicile certificate", "निवास प्रमाण पत्र", "இருப்பிடச் சான்றிதழ்",
                               "Domicile / niwas praman patra", ["domicile certificate", "domicile", "residence certificate"]),
    "residence_proof": _n("Proof of address", "पते का प्रमाण", "முகவரிச் சான்று", "Address proof",
                          ["proof of address", "address proof", "residential proof", "proof of residence",
                           "residence proof"]),
    "bank_passbook": _n("Bank passbook / account details", "बैंक पासबुक / खाता विवरण", "வங்கி கணக்குப் புத்தகம் / விவரங்கள்",
                        "Bank passbook / account details",
                        ["bank passbook", "passbook", "bank account number", "bank details", "bank account details",
                         "bank account", "ifsc"]),
    "savings_account": _n("Savings bank account", "बचत बैंक खाता", "சேமிப்புக் கணக்கு", "Savings bank account",
                          ["savings bank account", "savings account", "post office savings account"]),
    "passport_photo": _n("Passport-size photograph", "पासपोर्ट साइज़ फोटो", "பாஸ்போர்ட் அளவு புகைப்படம்",
                         "Passport size photo", ["passport size photograph", "passport size photo",
                                                 "passport-size photograph", "photograph", "photo"]),
    "photo_id": _n("Photo ID", "फोटो पहचान पत्र", "புகைப்பட அடையாள அட்டை", "Photo ID",
                   ["valid photo id", "photo id", "photo identity"]),
    "voter_id": _n("Voter ID (EPIC)", "मतदाता पहचान पत्र", "வாக்காளர் அடையாள அட்டை", "Voter ID card",
                   ["voter card", "voter id", "epic", "election card"]),
    "electricity_bill": _n("Electricity bill", "बिजली का बिल", "மின்சாரக் கட்டண ரசீது", "Bijli bill",
                           ["electricity bill"]),
    "age_proof": _n("Age proof", "आयु प्रमाण", "வயதுச் சான்று", "Age proof / umar ka praman",
                    ["age proof", "age certificate", "proof of age", "proof of date of birth", "date of birth"],
                    _AGE_HOW),
    "birth_certificate": _n("Birth certificate", "जन्म प्रमाण पत्र", "பிறப்புச் சான்றிதழ்", "Birth certificate",
                            ["birth certificate", "child birth certificate"]),
    "school_certificate": _n("School certificate", "स्कूल प्रमाण पत्र", "பள்ளிச் சான்றிதழ்", "School certificate",
                             ["school certificate", "school leaving certificate"]),
    "disability_certificate": _n("Disability certificate", "दिव्यांगता प्रमाण पत्र", "மாற்றுத்திறனாளி சான்றிதழ்",
                                 "Disability certificate", ["disability certificate", "disability card", "udid"]),
    "land_records": _n("Land records", "भूमि अभिलेख", "நில ஆவணங்கள்", "Zameen ke kagaz",
                       ["landholding paper", "landholding papers", "land holding papers", "land records",
                        "land record", "land ownership", "khatauni", "khasra"]),
    "mobile_number": _n("Mobile number", "मोबाइल नंबर", "கைபேசி எண்", "Mobile number",
                        ["mobile number", "mobile no"]),
    "death_certificate_of_spouse": _n("Husband's death certificate", "पति का मृत्यु प्रमाण पत्र",
                                      "கணவரின் இறப்புச் சான்றிதழ்", "Pati ka death certificate",
                                      ["death certificate of husband", "death certificate", "husband's death certificate"]),
    "pregnancy_registration": _n("Mother and Child Protection (MCP) card / pregnancy registration",
                                 "मातृ एवं शिशु सुरक्षा (MCP) कार्ड", "தாய்-சேய் பாதுகாப்பு (MCP) அட்டை",
                                 "MCP card / pregnancy registration", ["mcp card", "mcp/rchi card", "rchi card",
                                                                       "mother child protection card"]),
    "anc_record": _n("Antenatal check-up (ANC) record", "प्रसव पूर्व जाँच (ANC) रिकॉर्ड", "கர்ப்பகால பரிசோதனை பதிவு",
                     "ANC check-up record", ["anc date", "anc record", "lmp date", "last menstrual period"]),
    "immunization_record": _n("Child immunisation record", "बच्चे का टीकाकरण रिकॉर्ड", "குழந்தை தடுப்பூசி பதிவு",
                              "Bachche ka tikakaran record", ["child immunization", "immunization details",
                                                              "immunisation"]),
    "mgnrega_job_card": _n("MGNREGA job card", "मनरेगा जॉब कार्ड", "மகாத்மா காந்தி தேசிய ஊரக வேலை உறுதி அட்டை",
                           "MGNREGA job card", ["mgnrega job card", "mgnrega", "nrega job card"]),
    "e_shram_card": _n("e-Shram card", "ई-श्रम कार्ड", "இ-ஷ்ரம் அட்டை", "e-Shram card", ["e-shram card", "e shram card"]),
    "kisan_samman_proof": _n("PM-KISAN beneficiary proof", "पीएम-किसान लाभार्थी प्रमाण", "பிஎம்-கிசான் பயனாளி சான்று",
                             "PM-KISAN beneficiary proof", ["kisan samman nidhi"]),
    "pmjay_card": _n("Ayushman Bharat (PM-JAY) card", "आयुष्मान भारत (PM-JAY) कार्ड", "ஆயுஷ்மான் பாரத் அட்டை",
                     "Ayushman Bharat card", ["pradhan mantri jan aarogya yojana", "pmjay", "ayushman bharat"]),
    "self_declaration": _n("Self-declaration", "स्व-घोषणा पत्र", "சுய உறுதிமொழி", "Self declaration",
                           ["self-declaration", "self declaration", "14-point declaration", "annexure i"]),
    "application_form": _n("Filled application form", "भरा हुआ आवेदन पत्र", "பூர்த்தி செய்த விண்ணப்பப் படிவம்",
                           "Bhara hua application form", ["application form", "consent-cum-declaration form",
                                                         "consent cum declaration form"]),
    "affidavit_no_other_pension": _n("Affidavit: no other pension or assistance", "हलफनामा: कोई अन्य पेंशन नहीं",
                                     "வேறு ஓய்வூதியம் பெறவில்லை என்ற பிரமாணப் பத்திரம்",
                                     "Affidavit - koi aur pension nahi", ["affidavit"]),
    "nominee_details": _n("Nominee details", "नामांकित व्यक्ति का विवरण", "நியமனதாரர் விவரங்கள்",
                          "Nominee ki details", ["nominee details", "nominee"]),
    "kyc_documents": _n("KYC documents", "केवाईसी दस्तावेज़", "கேஒய்சி ஆவணங்கள்", "KYC documents",
                        ["kyc details", "kyc documents", "kyc"]),
    "migrant_declaration": _n("Migrant self-declaration", "प्रवासी स्व-घोषणा", "புலம்பெயர்ந்தோர் சுய உறுதிமொழி",
                              "Migrant self declaration", ["migrant applicants", "migrant family"]),
}


def write_documents() -> dict:
    DOCS_PATH.write_text(json.dumps(DOCUMENTS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {DOCS_PATH.relative_to(ROOT)} ({len(DOCUMENTS)} documents)")
    return DOCUMENTS


# ------------------------------------------------------------------ FAQ expansion (myscheme accordions)
def cmd_faq(a) -> None:
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, str(ROOT / "scripts"))
    import collect_myscheme as cm
    FAQ_DIR.mkdir(parents=True, exist_ok=True)
    th = cm.Throttle(a.delay)
    with sync_playwright() as p:
        b, pg = cm._browser(p)
        for sid, slug in SLUGS.items():
            if not slug:
                continue
            f = FAQ_DIR / f"{slug}.txt"
            if f.exists() and not a.force:
                print("have", slug)
                continue
            url = f"{cm.BASE}/schemes/{slug}"
            th.wait()
            try:
                pg.goto(url, wait_until="networkidle", timeout=60000)
                pg.wait_for_selector("text=Eligibility", timeout=20000)
                text = cm.snapshot_text(pg)
                tabs = pg.locator("div.cursor-pointer:has(> div > p.font-bold)")
                for i in range(tabs.count()):
                    th.delay, old = 0.4, th.delay
                    th.wait()
                    th.delay = old
                    try:
                        q = tabs.nth(i).locator("p.font-bold").first.inner_text().strip()
                        tabs.nth(i).click(timeout=3000)
                        pg.wait_for_timeout(500)
                        item = tabs.nth(i).locator("xpath=ancestor::div[contains(@class,'py-4')][1]")
                        block = re.sub(r"[ 	 ﻿]+", " ", item.inner_text()).strip()
                        if block.startswith(q) and block != q:
                            text = text.replace(q, block, 1)
                    except Exception:  # noqa: BLE001
                        pass
            except Exception as e:  # noqa: BLE001
                print("FAIL", slug, type(e).__name__)
                continue
            f.write_text(f"Source URL: {url}\n\n{text}\n", encoding="utf-8")
            print("saved", slug, f.stat().st_size)
        b.close()


# ------------------------------------------------------------------ build
def load_env_key(env_file: Path) -> None:
    """Put NVIDIA_API_KEY from a .env into the environment without printing it."""
    for ln in env_file.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(?:export\s+)?NVIDIA_API_KEY\s*=\s*(.*)$", ln)
        if m:
            os.environ["NVIDIA_API_KEY"] = m.group(1).strip().strip("'\"")
            return
    sys.exit("NVIDIA_API_KEY not found in env file")


def live_status(url: str) -> bool:
    """HTTP 200 on GET (certificate errors tolerated: this only proves the page is up)."""
    import httpx
    for verify in (True, False):
        try:
            r = httpx.get(url, headers={"User-Agent": "SahayakResearchBot/0.1"}, follow_redirects=True,
                          timeout=20, verify=verify)
            return r.status_code == 200
        except Exception:  # noqa: BLE001
            continue
    return False


def load_source(sid: str, schemes: dict) -> tuple[str, str, str]:
    """(source_text, source_url, note). myscheme snapshot (FAQ-expanded if present) else the scheme's own URL."""
    slug = SLUGS[sid]
    if slug:
        for p in (FAQ_DIR / f"{slug}.txt", SNAPS / f"{slug}.txt"):
            if p.exists():
                text = p.read_text(encoding="utf-8")
                return text, f"https://www.myscheme.gov.in/schemes/{slug}", f"myscheme:{p.parent.name}/{p.name}"
    from research.fetch import fetch_url
    url = schemes[sid]["source_url"]
    try:
        return fetch_url(url).text, url, "source_url (no myscheme page)"
    except Exception as e:  # noqa: BLE001
        return "", url, f"unavailable: {str(e)[:60]}"


def code_documents(sections: dict, docs: dict) -> tuple[list[dict], list[str]]:
    """(mapped documents, leftover lines). One entry per (line, doc id)."""
    from research.application import body_lines, line_is_mandatory, map_document_line
    out: list[dict] = []
    left: list[str] = []
    optional_from_here = False
    for ln in body_lines(sections.get("Documents Required", "")):
        low = ln.casefold()
        if low.startswith("indicative documents") or low.endswith("such as:-") or len(ln) < 4:
            continue
        if "any one of" in low:
            optional_from_here = True
        parts = [x.strip() for x in re.split(r"(?<=[.!?])\s+(?=[A-Z])", ln) if x.strip()] if len(ln) > 120 else [ln]
        for part in parts:
            ids = map_document_line(part, docs)
            if not ids:
                if len(parts) == 1 and not low.startswith("mentioned below") and not low.startswith("these"):
                    left.append(part)
                continue
            mand = line_is_mandatory(part) and not optional_from_here
            for i in ids:
                out.append({"doc": i, "as_written": part, "mandatory": mand, "quote": part})
    return out, left


def extract(llm, name: str, sections: dict, docs: dict, leftover: list[str]) -> dict | None:
    from research.application_prompt import build_messages
    from research.llm import LLMOutputError, parse_json_object
    for attempt in range(2):
        try:
            return parse_json_object(llm.complete(build_messages(name, sections, sorted(docs), leftover)))
        except (LLMOutputError, Exception) as e:  # noqa: BLE001
            print(f"   LLM attempt {attempt + 1} failed: {type(e).__name__}: {str(e)[:80]}")
            time.sleep(3)
    return None


def cmd_build(a) -> None:
    from research.application import split_sections
    from research.application_check import check_documents_file, check_record, tally
    from research.llm import LLM
    if a.env_file and Path(a.env_file).exists():
        load_env_key(Path(a.env_file))
    os.environ.setdefault("LLM_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b")
    docs = write_documents()
    problems = check_documents_file(docs)
    if problems:
        sys.exit("documents.json invalid: " + "; ".join(problems))
    schemes = {s["id"]: s for s in json.loads(SCHEMES_PATH.read_text("utf-8"))["schemes"]}
    llm = LLM(temperature=0.0, max_tokens=6000)
    existing = json.loads(APPS_PATH.read_text("utf-8")) if APPS_PATH.exists() else {}

    live: dict[str, bool] = {}
    for u in {**LOCATORS, **{f"portal:{k}": v for k, v in KNOWN_PORTALS.items()}}.values():
        live[u] = live_status(u)
    print("live checks:", {u: ok for u, ok in live.items()})
    live_urls = [u for u, ok in live.items() if ok]

    result, rows = dict(existing), []
    for sid in (a.only or list(SLUGS)):
        text, url, note = load_source(sid, schemes)
        today = date.today().isoformat()
        if not text.strip():
            rows.append((sid, note, "-", "-", "-", "-", "-", ["no source text; no record written"]))
            print(f"{sid}: {note}")
            continue
        sections = split_sections(text) or {"Page": text}
        mapped, left = code_documents(sections, docs)
        raw = extract(llm, schemes[sid]["name"], sections, docs, left)
        if raw is None:
            rows.append((sid, note, "-", "-", "-", "-", "-", ["LLM failed twice; no record written"]))
            continue
        # leftover document lines: the LLM only picks a canonical id (never invents one)
        for m in raw.get("doc_map") or []:
            if isinstance(m, dict) and m.get("line") in left and m.get("doc") in docs:
                mapped.append({"doc": m["doc"], "as_written": m["line"], "mandatory": bool(m.get("mandatory", True)),
                               "quote": m["line"]})
        enrol = []
        for e in raw.get("enrol_points") or []:
            if isinstance(e, dict):
                loc = LOCATORS.get(e.get("type"))
                enrol.append({"type": e.get("type"), "name": e.get("name"), "locator_url": loc if loc in live_urls else None,
                              "quote": e.get("quote")})
        rec = {"mode": raw.get("mode"), "portal_url": raw.get("portal_url"), "office": raw.get("office"),
               "helpline": re.sub(r"\s*[^\w\s,/+()\-.]+\s*", " - ", raw["helpline"]).strip()
               if isinstance(raw.get("helpline"), str) else None, "fees": raw.get("fees"),
               "steps": [{"n": s.get("n", i + 1), "action": s.get("action"), "where": s.get("where"),
                          "mode": s.get("mode"), "quote": s.get("quote")}
                         for i, s in enumerate(raw.get("steps") or []) if isinstance(s, dict)],
               "documents": mapped,
               "watch_outs": [{"kind": w.get("kind"), "text": w.get("text"), "quote": w.get("quote"),
                               "applies_if": w.get("applies_if")} for w in raw.get("watch_outs") or []
                              if isinstance(w, dict)],
               "faq": [{"q": f.get("q"), "a": f.get("a"), "quote": f.get("quote")} for f in raw.get("faq") or []
                       if isinstance(f, dict)],
               "enrol_points": enrol, "grievance": raw.get("grievance"),
               "source_url": url, "verified_at": today}
        rec = finalize(sid, rec)
        known = [u for k, u in KNOWN_PORTALS.items() if k == sid and live.get(u)]
        clean, log = check_record(rec, text, docs, live_urls=live_urls, known_portals=known)
        if clean is None:
            rows.append((sid, note, "-", "-", "-", "-", "-", log))
            continue
        result[sid] = clean
        t = tally(clean)
        rows.append((sid, note, t["steps"], t["documents"], t["watch_outs"], t["faq"], t["enrol_points"], log))
    APPS_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {APPS_PATH.relative_to(ROOT)}\n")
    print(f"{'scheme':14}{'steps':>6}{'docs':>6}{'watch':>6}{'faq':>5}{'enrol':>6}  grievance  source")
    for sid, note, st, dc, wo, fq, en, log in rows:
        g = "yes" if (result.get(sid) or {}).get("grievance") else "-"
        print(f"{sid:14}{st!s:>6}{dc!s:>6}{wo!s:>6}{fq!s:>5}{en!s:>6}  {g:9}  {note}")
    print("\ndropped items:")
    for sid, *_, log in rows:
        for ln in log:
            print(f"  {sid}: {ln}")


def cmd_migrate(a) -> None:
    """Add routes, alternatives_group and source_official to the existing records without calling the LLM."""
    from research.application_check import check_documents_file, check_record
    docs = write_documents()
    problems = check_documents_file(docs)
    if problems:
        sys.exit("documents.json invalid: " + "; ".join(problems))
    schemes = {s["id"]: s for s in json.loads(SCHEMES_PATH.read_text("utf-8"))["schemes"]}
    existing = json.loads(APPS_PATH.read_text("utf-8"))
    live_urls = [u for u in LOCATORS.values() if live_status(u)] if a.live else None
    result = {}
    for sid, rec in existing.items():
        text, _url, note = load_source(sid, schemes)
        if not text.strip():  # source unreachable now: re-check against the record's own quotes (they were verified at build)
            text = chr(10).join(str(q) for q in _quotes(rec))
            note += " (quotes only)"
        known = [u for k, u in KNOWN_PORTALS.items() if k == sid]
        clean, log = check_record(finalize(sid, {k: v for k, v in rec.items() if k not in ("routes", "source_official")}),
                                  text, docs, live_urls=live_urls, known_portals=known + [rec.get("portal_url") or ""])
        if clean is None:
            print(f"{sid}: kept as is ({log})")
            result[sid] = rec
            continue
        # items the old build had already accepted must survive: never lose data in a code-only migration
        for key in ("steps", "documents", "watch_outs", "faq", "enrol_points"):
            if len(clean[key]) != len(rec.get(key) or []):
                print(f"{sid}: {key} {len(rec.get(key) or [])} -> {len(clean[key])}; kept the old list")
                clean[key] = rec.get(key) or []
        for k in ("portal_url", "office", "helpline", "fees", "grievance"):
            clean[k] = rec.get(k)
        result[sid] = clean
        print(f"{sid}: routes={[(r['mode'], len(r['steps'])) for r in clean['routes']]} official={clean['source_official']} "
              f"groups={sorted({d['alternatives_group'] for d in clean['documents'] if 'alternatives_group' in d})} [{note}]")
        for ln in log:
            print("   ", ln)
    APPS_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    print(f"wrote {APPS_PATH.relative_to(ROOT)}")


def _quotes(rec: dict):
    for key in ("steps", "documents", "watch_outs", "faq", "enrol_points"):
        for it in rec.get(key) or []:
            yield it.get("quote") or ""
            if key == "faq":
                yield it.get("a") or ""
    g = rec.get("grievance")
    if isinstance(g, dict):
        yield g.get("quote") or ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("faq")
    f.add_argument("--delay", type=float, default=2.0)
    f.add_argument("--force", action="store_true")
    sub.add_parser("docs")
    m = sub.add_parser("migrate")
    m.add_argument("--live", action="store_true", help="also HTTP-check locator urls")
    b = sub.add_parser("build")
    b.add_argument("--env-file", default=str(ROOT.parent / "source-trail" / "backend" / ".env"))
    b.add_argument("--only", nargs="*")
    a = ap.parse_args()
    {"faq": cmd_faq, "docs": lambda _: write_documents(), "build": cmd_build, "migrate": cmd_migrate}[a.cmd](a)


if __name__ == "__main__":
    main()
