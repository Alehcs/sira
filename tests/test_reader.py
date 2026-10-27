import io
import json
from types import SimpleNamespace

import numpy as np
import pytest
from astropy.io import fits

from sira import reader
from sira.stamps import to_png


def fits_bytes(data):
    buf = io.BytesIO()
    fits.PrimaryHDU(data).writeto(buf)
    return buf.getvalue()


def fake_response(text):
    usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20, prompt_tokens_details=None,
                            completion_tokens_details=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))], usage=usage)


class FakeLLM:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def chat(self, provider, model, messages, tag="", **kwargs):
        self.calls.append((provider, model, messages, kwargs))
        return fake_response(self.answer(messages))


def test_parse_handles_fences_and_missing_label():
    assert reader.parse('```json\n{"label": "real", "p_real": 0.8, "why": "psf"}\n```')["label"] == "real"
    assert reader.parse('{"p_real": 0.2}')["label"] == "bogus"
    assert reader.parse('{"label": "real", "p_real": 7}')["p_real"] == 1.0
    assert reader.parse("no idea")["label"] is None


def test_metrics_count_unanswered_as_mistakes():
    rows = [{"truth": "real", "label": "real", "p_real": 0.9}, {"truth": "real", "label": None, "p_real": None},
            {"truth": "bogus", "label": "bogus", "p_real": 0.1}, {"truth": "bogus", "label": None, "p_real": None}]
    m = reader.metrics(rows)
    assert m["balanced_accuracy"] == 0.5
    assert m["unanswered"] == 2
    assert m["auc"] == 1.0
    assert not m["passes_gate"]


@pytest.fixture
def snapshot_dir(tmp_path, monkeypatch):
    png = to_png(fits_bytes(np.zeros((63, 63))))
    entries = {"valset": [("real", "ZTFval0001"), ("bogus", "ZTFval0002")], "examples": [("real", "ZTFex00001")]}
    for name, items in entries.items():
        rows = []
        for label, oid in items:
            files = [f"{name}/{oid}_{k}.png" for k in ("science", "template", "difference")]
            for f in files:
                (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
                (tmp_path / f).write_bytes(png)
            rows.append({"label": label, "oid": oid, "files": files})
        (tmp_path / f"{name}.json").write_text(json.dumps(rows))
    monkeypatch.setattr(reader, "EXAMPLES", {"ZTFex00001": (0.9, "clean point source")})
    return tmp_path


def test_check_scores_every_case_and_shows_examples(snapshot_dir):
    llm = FakeLLM(lambda msgs: '{"label": "real", "p_real": 0.7, "why": "x"}')
    result = reader.check(snapshot_dir, "spark-open", workers=2, llm=llm)
    assert result["n"] == 2 and result["shots"] == 1
    assert result["real_recall"] == 1.0 and result["bogus_recall"] == 0.0
    _, _, msgs, _ = llm.calls[0]
    assert msgs[0]["role"] == "system" and msgs[2]["role"] == "assistant" and msgs[-1]["role"] == "user"
    assert "ZTF" not in json.dumps([m for m in msgs if m["role"] == "user"])


def test_examples_must_stay_out_of_the_valset(snapshot_dir, monkeypatch):
    monkeypatch.setattr(reader, "EXAMPLES", {"ZTFval0001": (0.9, "leak")})
    with pytest.raises(ValueError):
        reader.check(snapshot_dir, "spark-open", llm=FakeLLM(lambda m: "{}"))


def test_unsure_answers_get_two_more_opinions():
    answers = iter(['{"label": "real", "p_real": 0.6}', '{"p_real": 0.2}', '{"p_real": 0.1}'])
    llm = FakeLLM(lambda msgs: next(answers))
    r = reader.read(llm, "spark-open", b"png", [])
    assert len(llm.calls) == 3 and r["votes"] == 3
    assert r["p_real"] == 0.3 and r["label"] == "bogus" and r["p_first"] == 0.6


def test_confident_answer_is_read_once():
    llm = FakeLLM(lambda msgs: '{"label": "bogus", "p_real": 0.05}')
    r = reader.read(llm, "spark-open", b"png", [])
    assert len(llm.calls) == 1 and r["label"] == "bogus" and r["usd"] > 0
