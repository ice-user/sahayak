"""Deterministic application planner: schemes + profile -> one actionable plan. No LLM involved.

Using it as a chat-agent tool (not wired yet):

    from sahayak.planner import build_plan
    build_plan(scheme_ids: list[str], profile: dict | Profile | None = None, lang: str = "en") -> dict

    returns {
      "lang": str,
      "checklist": [{"doc","name","needed_for":[scheme_id],"mandatory":bool,"how_to_get":None|{"text","source_url"},"have":None}
                    | {"doc_group","label","options":[<doc entries>],"needed_for","mandatory"}],  # "any one of" groups
      "steps": [{"scheme_id","scheme_name","scheme_ids","scheme_names","n","action","where","mode","source_url",
                 "source_urls","group_kind":"prepare"|"online"|"offline","group"}],  # near-identical steps merged
      "schemes": [{"scheme_id","scheme_name","source_url","source_official":bool,"recommended_mode",
                   "routes":[{"mode":"online"|"offline","summary","where","recommended":bool,"steps":[...]}]}],
      "watch_outs": [{"scheme_id","scheme_name","scheme_ids","scheme_names","kind","text","quote","personal":True|False|None,
                      "source_url"}],  # near-identical watch-outs (same kind, text ratio >= 0.9) merged
      "where_to_go": [{"scheme_id","scheme_name","enrol_points":[{"type","name","locator_url","quote"}],"grievance":None|{...},
                       "helpline","portal_url","office"}],
      "enrol_groups": [{"type","scheme_ids":[..],"points":[{"name","locator_url","scheme_ids"}]}],  # one trip per type
      "summary": {"schemes","documents","mandatory_documents","steps","online_steps","offline_steps","trips",
                  "offices":[str],"portals":[str],"watch_outs","personal_watch_outs",
                  "missing_application_data":[scheme_id],"unknown_schemes":[scheme_id],"data_available":bool},
      "sources": [url]}

    Tool schema: {"scheme_ids": [str], "lang": "en|hi|ta|hinglish"}; pass the session profile yourself.
    personal: True = applies to this user (listed first), False = does not, None = unknown or general (never hidden).
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any

from .models import DATA_PATH, Profile, load_schemes
from .rules import FAIL, PASS, eval_condition

DATA_DIR = Path(DATA_PATH).parent
APPLICATIONS_PATH = DATA_DIR / "applications.json"
DOCUMENTS_PATH = DATA_DIR / "documents.json"
LANGS = ("en", "hi", "ta", "hinglish")

_cache: dict[Path, tuple[float, dict]] = {}


def _load(path: Path) -> dict:
    """Read a JSON object file, cached by mtime. Missing or unreadable file -> {}."""
    path = Path(path)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    hit = _cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        data = {}
    _cache[path] = (mtime, data)
    return data


def load_applications() -> dict:
    return _load(APPLICATIONS_PATH)


def load_documents() -> dict:
    return _load(DOCUMENTS_PATH)


def get_application(scheme_id: str) -> dict | None:
    rec = load_applications().get(scheme_id)
    return rec if isinstance(rec, dict) else None


def _profile_data(profile: Any) -> dict:
    if profile is None:
        return {}
    data = profile.model_dump() if isinstance(profile, Profile) else dict(profile)
    if data.get("children") is not None:
        data["children"] = [c if isinstance(c, dict) else c.model_dump() for c in data["children"]]
    return data


def _personal(applies_if: Any, data: dict) -> bool | None:
    """True: applies to this user. False: does not. None: unknown (or no condition)."""
    if not isinstance(applies_if, dict):
        return None
    try:
        status, _ = eval_condition(data, applies_if)
    except (KeyError, TypeError, ValueError):
        return None
    return True if status == PASS else False if status == FAIL else None


def _doc_name(doc_id: str, entry: dict | None, as_written: str, lang: str) -> str:
    names = (entry or {}).get("name") or {}
    if isinstance(names, dict):
        for key in (lang, "en"):
            if names.get(key):
                return names[key]
    return as_written or doc_id


def _is_online(mode: Any) -> bool:
    return "online" in str(mode or "").lower()


def _grouped(items: list[tuple[str, dict]]) -> list[dict]:
    """Group by key (groups in order of first appearance), keeping (scheme, n) order inside a group."""
    groups: dict[str, list[dict]] = {}
    for key, step in items:
        groups.setdefault(key, []).append(step)
    return [{**s, "group": k} for k, steps in groups.items() for s in steps]


_PREPARE = re.compile(r"^\W*(keep|have|get|arrange|collect|gather|prepare|make sure)\b.*\b(documents?|papers?|copies|certificates|ready)\b",
                      re.I)
SIMILAR = 0.85


def _is_prepare(action: Any) -> bool:
    return bool(_PREPARE.search(str(action or "")))


def _norm(text: Any) -> str:
    return " ".join(re.findall(r"\w+", str(text or "").lower()))


def _similar(a: str, b: str) -> bool:
    if a == b:
        return True
    ta, tb = " ".join(sorted(set(a.split()))), " ".join(sorted(set(b.split())))
    ratio = max(difflib.SequenceMatcher(None, ta, tb).ratio(), difflib.SequenceMatcher(None, a, b).ratio())
    return ratio >= SIMILAR


def _merge(items: list[tuple[str, dict]], by_where: bool) -> list[tuple[str, dict]]:
    """Collapse near-identical steps (same where/mode unless `by_where` is False) across schemes into one."""
    out: list[tuple[str, dict, str, str]] = []
    for key, step in items:
        action, where, mode = _norm(step["action"]), _norm(step["where"]), _norm(step["mode"])
        hit = None
        for o in out:
            if (not by_where or (o[2] == where and o[3] == mode)) and _similar(o[4], action):
                hit = o
                break
        if hit is None:
            first = {**step, "scheme_ids": [step["scheme_id"]], "scheme_names": [step["scheme_name"]],
                     "source_urls": [step["source_url"]] if step["source_url"] else []}
            out.append((key, first, where, mode, action))
            continue
        m = hit[1]
        if step["scheme_id"] not in m["scheme_ids"]:
            m["scheme_ids"].append(step["scheme_id"])
            m["scheme_names"].append(step["scheme_name"])
        if step["source_url"] and step["source_url"] not in m["source_urls"]:
            m["source_urls"].append(step["source_url"])
    return [(k, s) for k, s, *_ in out]


def _unique_offices(offline: list[tuple[str, dict]]) -> list[str]:
    seen: dict[str, str] = {}
    for k, _ in offline:
        seen.setdefault(_norm(k), k)  # case/space-insensitive, first spelling kept
    return list(seen.values())


OFFICIAL_SUFFIXES = (".gov.in", ".nic.in", ".gov")
LOW_DIGITAL_AGE = 60
_FLAG_WORDS = ("homeless", "vulnerable", "elderly_alone", "no_phone", "no_mobile", "no_smartphone")


def is_official(url: Any) -> bool:
    m = re.match(r"^(?:https?://)?([^/:?#]+)", str(url or "").strip().lower())
    host = m.group(1).rstrip(".") if m else ""
    return any(host.endswith(x) or host == x.lstrip(".") for x in OFFICIAL_SUFFIXES)


def prefers_offline(data: dict) -> bool:
    """True when the profile suggests limited digital access: age >= 60, vulnerable/homeless flags, or no mobile number."""
    age = data.get("age")
    if isinstance(age, (int, float)) and not isinstance(age, bool) and age >= LOW_DIGITAL_AGE:
        return True
    for key in ("homeless", "vulnerable", "vulnerable_flag", "limited_digital_access"):
        if data.get(key) is True:
            return True
    flags = data.get("vulnerability_flags") or data.get("flags") or data.get("vulnerability")
    if isinstance(flags, (list, tuple, set)) and any(str(f).lower() in _FLAG_WORDS for f in flags):
        return True
    return data.get("has_mobile") is False or data.get("mobile_number") is False or data.get("has_mobile_number") is False


_SUPPORT = re.compile(r"^\W*(?:(?:check|track|view|know)\b.*\bstatus\b|download\b.*\b(?:form|application)\b)", re.I)


def _is_support(action: Any) -> bool:
    """Steps that are not a way of applying on their own: get ready, download the form, check the status later."""
    return _is_prepare(action) or bool(_SUPPORT.search(str(action or "")))


def derive_routes(steps: list[dict], portal_url: str | None = None, office: str | None = None) -> list[dict]:
    """Split a record's steps into alternative routes, one per mode (online first).

    Support steps (get documents ready, download the form, check status) join the route of the nearest real step
    before or after them, so "download the form" followed by "submit at the bank" is one offline route and a later
    "check status" never makes an online route by itself. The summary is the first real step's action unless a
    verified paraphrase is stored on the record; `where` is the portal (online) or the office."""
    ordered = [dict(s) for s in sorted(steps, key=lambda s: (s.get("n") is None, s.get("n") or 0))]
    real = [i for i, s in enumerate(ordered) if not _is_support(s.get("action"))]
    if not real:
        real = list(range(len(ordered)))
    route_of: dict[int, str] = {}
    for i, s in enumerate(ordered):
        if i in real:
            route_of[i] = "online" if s.get("mode") == "online" else "offline"
            continue
        nxt = next((j for j in real if j > i), None)
        prev = next((j for j in reversed(real) if j < i), None)
        j = nxt if nxt is not None else prev
        route_of[i] = "online" if ordered[j].get("mode") == "online" else "offline"
    routes = []
    for mode in ("online", "offline"):
        group = [s for i, s in enumerate(ordered) if route_of[i] == mode]
        first = next((s for i, s in enumerate(ordered) if route_of[i] == mode and i in real), None)
        if not group or first is None:
            continue
        where = portal_url if mode == "online" else next((s["where"] for s in group if s.get("where")), None) or office
        routes.append({"mode": mode, "summary": first.get("action") or "", "where": where or None, "steps": group})
    return routes


def _route_list(rec: dict) -> list[dict]:
    routes = [r for r in (rec.get("routes") or []) if isinstance(r, dict) and r.get("steps")]
    return routes or derive_routes([s for s in rec.get("steps") or [] if isinstance(s, dict)],
                                   rec.get("portal_url"), rec.get("office"))


def recommended_mode(routes: list[dict], data: dict) -> str | None:
    modes = [r.get("mode") for r in routes]
    if not modes:
        return None
    if prefers_offline(data) and "offline" in modes:
        return "offline"
    return "online" if "online" in modes else modes[0]


WATCH_SIMILAR = 0.9


def _dedupe_watch(items: list[dict]) -> list[dict]:
    """Merge watch-outs with the same kind and near-identical text (within and across schemes)."""
    out: list[tuple[str, dict]] = []
    for w in items:
        text = _norm(w["text"])
        hit = next((o for t, o in out if o["kind"] == w["kind"]
                    and difflib.SequenceMatcher(None, t, text).ratio() >= WATCH_SIMILAR), None)
        if hit is None:
            out.append((text, {**w, "scheme_ids": [w["scheme_id"]], "scheme_names": [w["scheme_name"]]}))
            continue
        if w["scheme_id"] not in hit["scheme_ids"]:
            hit["scheme_ids"].append(w["scheme_id"])
            hit["scheme_names"].append(w["scheme_name"])
        if hit["personal"] is not True and (w["personal"] is True or hit["personal"] is False):
            hit["personal"] = w["personal"]  # the more specific verdict wins: applies > unknown > does not apply
    return [o for _, o in out]


GROUP_LABELS = {
    "id_proof": {"en": "Any one ID proof", "hi": "कोई एक पहचान प्रमाण", "ta": "ஏதேனும் ஒரு அடையாளச் சான்று",
                 "hinglish": "Koi ek ID proof"},
    "address_proof": {"en": "Any one address proof", "hi": "कोई एक पते का प्रमाण", "ta": "ஏதேனும் ஒரு முகவரிச் சான்று",
                      "hinglish": "Koi ek address proof"},
    "age_proof": {"en": "Any one age proof", "hi": "कोई एक आयु प्रमाण", "ta": "ஏதேனும் ஒரு வயதுச் சான்று",
                  "hinglish": "Koi ek age proof"},
    "family_proof": {"en": "Any one family proof", "hi": "कोई एक पारिवारिक प्रमाण", "ta": "ஏதேனும் ஒரு குடும்பச் சான்று",
                     "hinglish": "Koi ek family proof"},
}
_ANY_OF = {"en": "Any one of", "hi": "इनमें से कोई एक", "ta": "இவற்றில் ஏதேனும் ஒன்று", "hinglish": "Inme se koi ek"}
GROUP_HEADS = {"address_proof": "residence_proof", "age_proof": "age_proof", "id_proof": "photo_id"}  # generic names for the group


def build_plan(scheme_ids: list[str], profile: Any = None, lang: str = "en", schemes: dict | None = None) -> dict:
    lang = lang if lang in LANGS else "en"
    apps, docs = load_applications(), load_documents()
    schemes = schemes if schemes is not None else load_schemes()
    data = _profile_data(profile)

    ids = list(dict.fromkeys(i for i in scheme_ids if isinstance(i, str)))
    unknown, missing, used = [], [], []
    for sid in ids:
        if sid not in schemes and sid not in apps:
            unknown.append(sid)
        elif not isinstance(apps.get(sid), dict):
            missing.append(sid)
        else:
            used.append(sid)

    def name_of(sid: str) -> str:
        return getattr(schemes.get(sid), "name", None) or sid

    checklist: dict[str, dict] = {}
    groups: dict[str, dict] = {}
    prepare: list[tuple[str, dict]] = []
    online: list[tuple[str, dict]] = []
    offline: list[tuple[str, dict]] = []
    watch: list[dict] = []
    sources: list[str] = []
    where_to_go: list[dict] = []
    enrol: dict[str, dict] = {}
    scheme_cards: list[dict] = []
    unofficial: list[str] = []

    def doc_entry(doc_id: str, d: dict) -> dict:
        entry = docs.get(doc_id) if isinstance(docs.get(doc_id), dict) else None
        return {"doc": doc_id, "name": _doc_name(doc_id, entry, d.get("as_written", ""), lang), "needed_for": [],
                "mandatory": False, "how_to_get": (entry or {}).get("how_to_get"), "have": None}

    for sid in used:
        rec = apps[sid]
        sname = name_of(sid)
        points = [p for p in (rec.get("enrol_points") or []) if isinstance(p, dict)]
        grievance = rec.get("grievance") if isinstance(rec.get("grievance"), dict) else None
        where_to_go.append({"scheme_id": sid, "scheme_name": sname, "enrol_points": points, "grievance": grievance,
                            "helpline": rec.get("helpline"), "portal_url": rec.get("portal_url"),
                            "office": rec.get("office")})
        for p in points:
            g = enrol.setdefault(str(p.get("type") or "other"), {"scheme_ids": [], "points": {}})
            if sid not in g["scheme_ids"]:
                g["scheme_ids"].append(sid)
            pt = g["points"].setdefault(p.get("name") or "", {"name": p.get("name"), "locator_url": p.get("locator_url"),
                                                            "scheme_ids": []})
            pt["locator_url"] = pt["locator_url"] or p.get("locator_url")
            if sid not in pt["scheme_ids"]:
                pt["scheme_ids"].append(sid)
        for d in rec.get("documents") or []:
            doc_id = d.get("doc")
            if not doc_id:
                continue
            gid = d.get("alternatives_group")
            if isinstance(gid, str) and gid:
                grp = groups.setdefault(gid, {"options": {}, "needed_for": [], "mandatory": False})
                opt = grp["options"].setdefault(doc_id, doc_entry(doc_id, d))
                for target in (opt, grp):
                    if sid not in target["needed_for"]:
                        target["needed_for"].append(sid)
                    target["mandatory"] = target["mandatory"] or bool(d.get("mandatory"))
                continue
            item = checklist.setdefault(doc_id, doc_entry(doc_id, d))
            if sid not in item["needed_for"]:
                item["needed_for"].append(sid)
            item["mandatory"] = item["mandatory"] or bool(d.get("mandatory"))

        routes = _route_list(rec)
        rec_mode = recommended_mode(routes, data)
        official = rec.get("source_official") if isinstance(rec.get("source_official"), bool) else is_official(rec.get("source_url"))
        if not official:
            unofficial.append(sid)
        out_routes = []
        for r in routes:
            is_rec = r.get("mode") == rec_mode
            steps_out = []
            for st in sorted(r.get("steps") or [], key=lambda x: (x.get("n") is None, x.get("n") or 0)):
                mode = r.get("mode") or st.get("mode") or rec.get("mode")  # support steps follow their route
                step = {"scheme_id": sid, "scheme_name": sname, "n": st.get("n"), "action": st.get("action"),
                        "where": st.get("where"), "mode": mode, "source_url": rec.get("source_url")}
                if _is_prepare(st.get("action")):
                    step["group_kind"] = "prepare"
                    prepare.append(("prepare", step))
                    continue  # shown once in the prepare group, not inside a route
                steps_out.append({k: v for k, v in step.items() if k not in ("scheme_id", "scheme_name")})
                if not is_rec:
                    continue
                if _is_online(mode):
                    step["group_kind"] = "online"
                    online.append((rec.get("portal_url") or st.get("where") or "portal", step))
                else:
                    step["group_kind"] = "offline"
                    offline.append((r.get("where") or rec.get("office") or st.get("where") or "office", step))
            if steps_out:
                out_routes.append({"mode": r.get("mode"), "summary": r.get("summary") or steps_out[0]["action"],
                                   "where": r.get("where"), "recommended": is_rec, "steps": steps_out})
        scheme_cards.append({"scheme_id": sid, "scheme_name": sname, "source_url": rec.get("source_url"),
                             "source_official": official, "recommended_mode": rec_mode, "routes": out_routes})
        for w in rec.get("watch_outs") or []:
            watch.append({"scheme_id": sid, "scheme_name": sname, "kind": w.get("kind"), "text": w.get("text"),
                          "quote": w.get("quote"), "personal": _personal(w.get("applies_if"), data),
                          "source_url": rec.get("source_url")})
        if rec.get("source_url") and rec["source_url"] not in sources:
            sources.append(rec["source_url"])

    rank = {True: 0, None: 1, False: 2}
    watch = _dedupe_watch(watch)
    watch.sort(key=lambda w: rank[w["personal"]])  # stable: scheme order kept within a verdict
    entries_by_doc = dict(checklist)
    group_entries: list[dict] = []
    for gid, grp in groups.items():
        opts = list(grp["options"].values())
        head = GROUP_HEADS.get(gid)
        if head and len(opts) > 1:
            opts = [o for o in opts if o["doc"] != head] or opts  # the generic name is the label, not an option
            plain = entries_by_doc.pop(head, None)  # "proof of address" asked on its own is this same group
            if plain:
                grp["mandatory"] = grp["mandatory"] or plain["mandatory"]
                grp["needed_for"] += [x for x in plain["needed_for"] if x not in grp["needed_for"]]
        label = GROUP_LABELS.get(gid, {}).get(lang) or f"{_ANY_OF[lang]}: " + " / ".join(o["name"] for o in opts)
        group_entries.append({"doc_group": gid, "label": label, "options": opts, "needed_for": grp["needed_for"],
                              "mandatory": grp["mandatory"]})
    items = sorted([*entries_by_doc.values(), *group_entries], key=lambda c: (not c["mandatory"], -len(c["needed_for"])))
    steps = (_grouped(_merge(prepare, False)) + _grouped(_merge(online, True)) + _grouped(_merge(offline, True)))
    offices = _unique_offices(offline)
    portals = list(dict.fromkeys(k for k, _ in online))
    all_steps = sum(len(r["steps"]) for c in scheme_cards for r in c["routes"])

    return {
        "lang": lang,
        "checklist": items,
        "schemes": scheme_cards,
        "steps": steps,
        "watch_outs": watch,
        "where_to_go": where_to_go,
        "enrol_groups": sorted(
            ({"type": t, "scheme_ids": g["scheme_ids"], "points": list(g["points"].values())} for t, g in enrol.items()),
            key=lambda g: -len(g["scheme_ids"])),
        "summary": {
            "schemes": len(used), "documents": len(items),
            "mandatory_documents": sum(1 for c in items if c["mandatory"]),
            "steps": len(steps), "prepare_steps": sum(1 for x in steps if x["group_kind"] == "prepare"),
            "online_steps": sum(1 for x in steps if x["group_kind"] == "online"),
            "offline_steps": sum(1 for x in steps if x["group_kind"] == "offline"),
            "all_route_steps": all_steps,
            "trips": len(offices), "offices": offices, "portals": portals,
            "watch_outs": len(watch), "personal_watch_outs": sum(1 for w in watch if w["personal"] is True),
            "unofficial_sources": unofficial,
            "missing_application_data": missing, "unknown_schemes": unknown,
            "data_available": bool(apps),
        },
        "sources": sources,
    }
