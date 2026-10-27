from types import SimpleNamespace

import pytest

from sira import probe

BTS_ROWS = [
    {"oid": f"ZTF{y % 100}bright{i}", "name": f"SN{y}b{i}", "type": "SN Ia", "redshift": 0.01 * (i + 1),
     "peak_mjd": 58484.0 + 365.25 * (y - 2019) + 10, "peak_mag": 13.0 + i, "ra": 10.0, "dec": -5.0}
    for y in range(2019, 2027) for i in range(3)
] + [
    {"oid": f"ZTF{y % 100}faint{i}", "name": f"SN{y}f{i}", "type": "SN II", "redshift": 0.05, "peak_mjd": 58484.0
     + 365.25 * (y - 2019) + 20, "peak_mag": 18.5, "ra": 20.0, "dec": 5.0} for y in range(2019, 2027) for i in range(3)
] + [{"oid": "ZTF25aapwxhm", "name": "SN2025khl", "type": "SN Ia", "redshift": 0.044, "peak_mjd": 60800.0,
      "peak_mag": 17.3, "ra": 1.0, "dec": 2.0}]
MULENS = [{"oid": "ZTF19aavnrqt", "t0_mjd": 58700.0, "tE": 40.0, "u0": 0.3, "ra": 3.0, "dec": 4.0}]


def test_events_mix_bright_faint_and_stars():
    picked = probe.events(BTS_ROWS, MULENS)
    groups = [e["group"] for e in picked]
    assert groups.count("star") == 2 and groups.count("bright") == 16 and groups.count("faint") == 16
    assert {e["year"] for e in picked if e["group"] == "bright"} == set(range(2019, 2027))
    assert all(e["peak_mag"] > 18 for e in picked if e["group"] == "faint")


@pytest.mark.parametrize("text,expected", [
    ("SN Ia", "ia"), ("Type Ia-91T", "ia"), ("SN Iax", "ia"), ("Type II-P", "ii"), ("SN IIn", "ii"),
    ("SN IIb", "stripped"), ("Ic-BL", "stripped"), ("SN Ib/c", "stripped"), ("TDE-H-He", "tde"),
    ("tidal disruption event", "tde"), ("SLSN-I", "slsn"), ("microlensing event", "lens"), ("FBOT", "other"),
    (None, None), ("unknown", None),
])
def test_coarse_types(text, expected):
    assert probe.coarse(text) == expected


def test_remembered_needs_a_specific_fact():
    truth = {"oid": "ZTF23aaklqou", "name": "SN2023ixf", "type": "SN II", "redshift": 0.0008}
    hit = probe.score(truth, {"known": True, "type": "Type II", "redshift": 0.00081}, {"known": True, "name": "SN 2023ixf"})
    assert hit["remembered"] and hit["sky_name_ok"] and hit["name_type_ok"]
    vague = probe.score(truth, {"known": True, "type": "SN II", "redshift": 0.01}, {"known": False, "name": None})
    assert vague["name_type_ok"] and not vague["remembered"]


def test_chance_scores_answers_against_other_events():
    rows = [{"oid": "a", "type": "SN Ia", "redshift": 0.05, "by_name": {"type": "Ia", "redshift": 0.05}},
            {"oid": "b", "type": "SN II", "redshift": 0.02, "by_name": {"type": "II", "redshift": 0.02}}]
    assert probe.chance(rows) == {"name_type_ok": 0.0, "name_z_ok": 0.0}


def test_run_asks_both_questions_per_event():
    calls = []

    def chat(provider, model, messages, tag="", **kwargs):
        calls.append(messages[-1]["content"])
        usage = SimpleNamespace(prompt_tokens=50, completion_tokens=10, prompt_tokens_details=None,
                                completion_tokens_details=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"known": false}'))], usage=usage)

    result = probe.run(BTS_ROWS, MULENS, "spark", llm=SimpleNamespace(chat=chat), workers=2)
    assert result["n"] == 34 and len(calls) == 68
    assert result["overall"]["remembered"] == 0.0 and result["usd"] > 0
    assert any("RA 3.0000 deg" in c for c in calls) and any("ZTF19aavnrqt?" in c for c in calls)
