"""Clause-level polarity (mentions.py) and the datagen grader built on it: table-driven adversarial cases."""
import json
import threading

import pytest

from sahayak.datagen.grader import grade, script_ok
from sahayak.datagen.profiles import generate
from sahayak.mentions import claimed_available, mentioned

# (id, answer, scheme, claimed_available?)
CASES = [
    ("not_eligible_en", "You are not eligible for PMSBY.", "pmsbY".lower(), False),
    ("cannot_but_can_neg", "You cannot get PMJJBY, but you can get Sukanya and PMUY.", "pmjjby", False),
    ("cannot_but_can_pos1", "You cannot get PMJJBY, but you can get Sukanya and PMUY.", "ssy", True),
    ("cannot_but_can_pos2", "You cannot get PMJJBY, but you can get Sukanya and PMUY.", "pmuy", True),
    ("do_not_qualify", "You do not qualify for IGNOAPS. You are ineligible for PMSBY.", "ignoaps", False),
    ("ineligible", "You do not qualify for IGNOAPS. You are ineligible for PMSBY.", "pmsby", False),
    ("neg_header_list_1", "Not available for you:\n- APY\n- PMSBY", "apy", False),
    ("neg_header_list_2", "Not available for you:\n- APY\n- PMSBY", "pmsby", False),
    ("pos_header_list", "You can get:\n- APY\n- PMSBY", "apy", True),
    ("two_sections_neg", "Not eligible:\n- APY\n\nEligible:\n- PMSBY", "apy", False),
    ("two_sections_pos", "Not eligible:\n- APY\n\nEligible:\n- PMSBY", "pmsby", True),
    ("md_header_neg", "### Not eligible\n- PMUY", "pmuy", False),
    ("bold_header_pos", "**You can get**\n- PMSBY", "pmsby", True),
    ("comma_list_pos", "You can get IGNOAPS, PMSBY and APY.", "apy", True),
    ("semicolon_mixed_pos", "You can get IGNOAPS; you cannot get APY.", "ignoaps", True),
    ("semicolon_mixed_neg", "You can get IGNOAPS; you cannot get APY.", "apy", False),
    ("qualify_for", "You qualify for PMSBY and PMJJBY.", "pmjjby", True),
    ("imperative_offer", "Open a Sukanya Samriddhi account at the post office.", "ssy", True),
    ("plain_description_not_a_claim", "APY is a pension scheme for unorganised workers.", "apy", False),
    ("documents_line", "Documents needed for PMSBY: Aadhaar, bank account.", "pmsby", False),
    ("not_available", "Sorry, PMUY is not available for you.", "pmuy", False),
    ("arent_eligible", "Unfortunately you aren't eligible for IGNWPS.", "ignwps", False),
    ("conditional_en", "If you have a BPL card, you can get PMUY.", "pmuy", False),
    ("hedge_redirect", "You don't qualify for the 70+ card, but you may still be covered by regular PM-JAY. "
                       "Please check on the Ayushman app.", "pmjay_senior", False),
    ("bare_hedge_is_a_claim", "You may be eligible for PMSBY.", "pmsby", True),
    # Hindi
    ("hi_pos", "आप IGNOAPS के लिए पात्र हैं।", "ignoaps", True),
    ("hi_neg", "आप PMSBY के लिए पात्र नहीं हैं।", "pmsby", False),
    ("hi_ahi_neg", "आप PMSBY के लिए अपात्र हैं।", "pmsby", False),
    ("hi_contrast_pos", "आप IGNOAPS के लिए पात्र हैं लेकिन PMSBY के लिए नहीं।", "ignoaps", True),
    ("hi_contrast_neg", "आप IGNOAPS के लिए पात्र हैं लेकिन PMSBY के लिए नहीं।", "pmsby", False),
    ("hi_nahi_milegi", "IGNWPS पेंशन आपको नहीं मिलेगी।", "ignwps", False),
    ("hi_conditional", "अगर आपके पास बीपीएल कार्ड है तो आप IGNOAPS ले सकते हैं।", "ignoaps", False),
    ("hi_mil_sakti", "आपको उज्ज्वला योजना (PMUY) मिल सकती है।", "pmuy", True),
    # Hinglish
    ("hl_contrast_neg", "Aap PMJJBY ke liye eligible nahi hain, lekin Sukanya ke liye eligible hain.", "pmjjby", False),
    ("hl_contrast_pos", "Aap PMJJBY ke liye eligible nahi hain, lekin Sukanya ke liye eligible hain.", "ssy", True),
    ("hl_mil_sakta", "Aapko PM-KISAN mil sakta hai.", "pm_kisan", True),
    ("hl_apply_pos", "Aap PMSBY ke liye apply kar sakte hain.", "pmsby", True),
    ("hl_apply_neg", "Aap APY ke liye apply nahi kar sakte.", "apy", False),
    # Tamil
    ("ta_neg", "நீங்கள் PMSBY திட்டத்திற்கு தகுதி இல்லை.", "pmsby", False),
    ("ta_pos", "உங்களுக்கு PMSBY கிடைக்கும்.", "pmsby", True),
    ("ta_contrast_neg", "PMUY கிடைக்காது, ஆனால் Sukanya கிடைக்கும்.", "pmuy", False),
    ("ta_contrast_pos", "PMUY கிடைக்காது, ஆனால் Sukanya கிடைக்கும்.", "ssy", True),
]


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_polarity_table(case):
    _, answer, scheme, expected = case
    assert mentioned(answer, scheme)
    assert claimed_available(answer, scheme) is expected


def test_table_has_enough_adversarial_cases():
    assert len(CASES) >= 20


# ---- grader
SCEN = generate(200, seed=7)


def _widow():
    return next(s for s in SCEN if s.persona == "elderly_widow" and s.profile["bpl"] and s.lang == "en")


def _turn(s, answer, args=None):
    args = {k: s.profile[k] for k in s.revealed} if args is None else args
    return {"revealed": set(s.revealed), "revealed_after": set(s.revealed), "answer": answer, "stopped": False,
            "tool_calls": [{"name": "check_eligibility", "arguments": json.dumps({"profile": args})}]}


def _names(s):
    from sahayak.models import Profile, load_schemes
    from sahayak.rules import check_all
    known = Profile(**{k: s.profile[k] for k in s.revealed})
    return [r.scheme_name for r in check_all(known, load_schemes()) if r.verdict == "eligible"]


def test_recall_needs_a_positive_claim():
    s = _widow()
    wrong = "You are not eligible for " + ", ".join(_names(s)) + "."
    g = grade(s, [_turn(s, wrong)])
    assert not g["checks"]["recall_ok"]


def test_false_claim_in_an_earlier_turn_is_caught():
    s = _widow()
    good = "You can get: " + "; ".join(_names(s)) + "."
    g = grade(s, [_turn(s, "You can get Atal Pension Yojana (APY)."), _turn(s, good)])
    assert not g["checks"]["no_false_claim"] and any("turn 1" in r for r in g["reasons"])


def test_one_negation_does_not_shield_other_schemes():
    s = _widow()
    good = "You can get: " + "; ".join(_names(s)) + "."
    bad = good + " You cannot get PMJJBY, but you can get Sukanya and PMUY."
    assert not grade(s, [_turn(s, bad)])["checks"]["no_false_claim"]


def test_correct_denials_are_not_rejected():
    s = _widow()
    good = "You can get: " + "; ".join(_names(s)) + "."
    answer = (good + "\nYou do not qualify for APY. You are ineligible for PMJJBY.\n"
              "Not available for you:\n- PMUY\n- Sukanya Samriddhi")
    g = grade(s, [_turn(s, answer)])
    assert g["checks"]["no_false_claim"], g["reasons"]


# ---- language / script
@pytest.mark.parametrize("text, lang, ok", [
    ("आप पात्र हैं।", "hi", True),                                                   # short but valid Hindi
    ("आप IGNOAPS (Indira Gandhi National Old Age Pension) के लिए पात्र हैं।", "hi", True),
    ("You can get IGNOAPS and PMSBY from the bank. Documents: Aadhaar, passbook. आप पात्र हैं।", "hi", False),
    ("You can get IGNOAPS.", "hi", False),
    ("நீங்கள் தகுதி பெற்றவர்.", "ta", True),
    ("You are eligible. நீங்கள் தகுதி.", "ta", False),
    ("You can get IGNOAPS. Carry your Aadhaar.", "en", True),
    ("आप पात्र हैं और आधार कार्ड लेकर नजदीकी कार्यालय में जाइए।", "en", False),
    ("Aapko IGNOAPS mil sakta hai. Aadhaar card lekar office mein apply karein.", "hinglish", True),
    ("You can get IGNOAPS. Carry your Aadhaar card to the office and apply.", "hinglish", False),  # English for a Hinglish user
    ("आप पात्र हैं और आधार कार्ड लेकर जाइए।", "hinglish", False),
])
def test_script_ratio_checks(text, lang, ok):
    assert script_ok(text, lang) is ok


# ---- resumable, crash-safe output files
def test_resume_survives_truncated_last_line(tmp_path):
    from sahayak.datagen.run import load_scenarios, run, save_scenarios
    scen = tmp_path / "s.jsonl"
    save_scenarios(12, 1, scen)
    out = tmp_path / "out"
    run(scen, out, "oracle", workers=1, limit=5, paraphrase=False, model=None)
    train = out / "train.jsonl"
    data = train.read_bytes()
    train.write_bytes(data + b'{"id": "s0000')                       # crash mid-write
    run(scen, out, "oracle", workers=2, limit=None, paraphrase=False, model=None)
    lines = [ln for ln in train.read_text(encoding="utf-8").splitlines() if ln.strip()]
    ids = [json.loads(ln)["id"] for ln in lines]                     # every line parses
    assert len(ids) == len(set(ids)) == 12


def test_repair_handles_missing_newline_and_garbage_middle(tmp_path):
    from sahayak.datagen.run import read_jsonl, repair_jsonl
    p = tmp_path / "x.jsonl"
    p.write_bytes(b'{"id": 1}\nnot json\n{"id": 2}')
    repair_jsonl(p)
    assert p.read_bytes().endswith(b"\n")
    assert [r["id"] for r in read_jsonl(p)] == [1, 2]


def test_append_record_is_atomic_per_line_across_threads(tmp_path):
    from sahayak.datagen.run import append_record
    p = tmp_path / "o.jsonl"
    big = "x" * 20000

    def work(t):
        for i in range(25):
            append_record(p, {"id": f"{t}-{i}", "blob": big})

    threads = [threading.Thread(target=work, args=(t,)) for t in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 200 and all(json.loads(ln)["blob"] == big for ln in lines)


def test_hinglish_pa_sakte_and_laabh_count_as_offers():
    """Found live: 'free anaj pa sakte hain' slipped past the guard, so an unverified PM-GKAY claim reached a user."""
    from sahayak.mentions import offered_schemes
    assert offered_schemes("AAP ke paas AAY ration card hai, toh aap PM Garib Kalyan Anna Yojana (PMGKAY) ke tahat free anaj pa sakte hain.") == ["pm_gkay"]
    assert offered_schemes("Aap PMGKAY ka laabh le sakti hain.") == ["pm_gkay"]
    assert offered_schemes("Aap PMGKAY nahi pa sakte kyunki aapke paas ration card nahi hai.") == []
    assert offered_schemes("Agar aapke paas AAY card hai to aap PMGKAY pa sakte hain.") == []
