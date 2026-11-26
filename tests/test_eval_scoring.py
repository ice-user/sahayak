from evals.run_agent_evals import claimed_available, mentioned, score


def test_mention_detection_multilingual():
    assert mentioned("आप विधवा पेंशन (IGNWPS) के लिए पात्र हैं", "ignwps")
    assert mentioned("You can get Ayushman Bharat", "pmjay_senior")
    assert not mentioned("Nothing relevant here", "ssy")


def test_negated_mention_is_not_a_claim():
    ans = "You can join PMJJBY and PMSBY. You are not eligible for Atal Pension Yojana because you pay income tax."
    assert claimed_available(ans, "pmjjby")
    assert not claimed_available(ans, "apy")


def test_score_shape():
    case = {"expect_tool": "check_eligibility", "expect_eligible": ["ssy"], "expect_not_claimed": ["apy"]}
    s = score(case, "Open a Sukanya Samriddhi account.", ["check_eligibility"])
    assert s == {"used_tool": True, "recall": 1.0, "no_false_claim": True}
