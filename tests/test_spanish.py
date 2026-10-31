import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sira import spanish
from sira.llm import SPARK

WORDS = Path(__file__).parents[1] / "site" / "src" / "words.js"


def model(answer=None, error=None):
    # a stand-in for Spark: answer maps the numbered notes it is sent to its reply
    calls = []

    def chat(provider, model, messages, tag="", **kwargs):
        calls.append({"provider": provider, "model": model, "messages": messages, "tag": tag} | kwargs)
        if error:
            raise error
        notes = json.loads(messages[-1]["content"])
        usage = SimpleNamespace(prompt_tokens=600, completion_tokens=300, prompt_tokens_details=None,
                                completion_tokens_details=None)
        reply = SimpleNamespace(message=SimpleNamespace(content=answer(notes)))
        return SimpleNamespace(choices=[reply], usage=usage)
    return SimpleNamespace(chat=chat, calls=calls)


def tag(notes):
    return json.dumps({k: f"[es] {v}" for k, v in notes.items()})


def test_one_minimal_spark_call_translates_every_note():
    llm = model(tag)
    texts = ["Smooth rise over 12 days.", "Fits a z=0.087 plateau.", "Smooth rise over 12 days.", ""]
    es, usd = spanish.translate(llm, texts)
    assert es == {"Smooth rise over 12 days.": "[es] Smooth rise over 12 days.",
                  "Fits a z=0.087 plateau.": "[es] Fits a z=0.087 plateau."}
    assert len(llm.calls) == 1 and len(json.loads(llm.calls[0]["messages"][-1]["content"])) == 2
    call = llm.calls[0]
    assert (call["provider"], call["model"], call["reasoning_effort"]) == ("meta", SPARK, "minimal")
    assert usd == pytest.approx((600 * 1.25 + 300 * 4.25) / 1e6)


def test_a_note_whose_numbers_change_stays_in_english():
    texts = {"Peak at -2.6 d, 0.9 mag redder.": "Pico en -2,6 d, 0,9 mag más rojo.",
             "Rises 3-4 times in 5 days.": "Sube varias veces en cinco días.",
             "Flat near 19 mag for 4 days.": "Plana cerca de 19 mag por 4 días.",
             "Brighter than 75 microjansky in r.": "Más brillante que 750 microjansky en r."}
    es, _ = spanish.translate(model(lambda notes: json.dumps({k: texts[v] for k, v in notes.items()})), list(texts))
    assert es == {"Flat near 19 mag for 4 days.": "Plana cerca de 19 mag por 4 días."}


def test_the_glossary_is_the_sites_own_words():
    js = WORDS.read_text().lower()
    assert all(en.lower() in js and es.lower() in js for en, es in spanish.GLOSSARY.items())
    assert "Type Ia supernova = Supernova tipo Ia" in spanish.TASK
    assert "about as likely as not = tan probable como improbable" in spanish.TASK


def test_a_note_that_is_a_known_name_needs_no_call():
    llm = model(tag)
    es, usd = spanish.translate(llm, ["Unseen foreground microlens", "likely"])
    assert es == {"Unseen foreground microlens": "Microlente invisible en primer plano", "likely": "probable"}
    assert llm.calls == [] and usd == 0


def test_a_bad_reply_translates_nothing_but_still_costs():
    es, usd = spanish.translate(model(lambda notes: "Lo siento, no puedo."), ["Smooth rise."])
    assert es == {} and usd > 0
    es, _ = spanish.translate(model(lambda notes: json.dumps({"1": ["Subida suave."], "2": " "})), ["Smooth rise.", "Flat."])
    assert es == {}


def lanes():
    return [{"object": "ZTF19aavisrq", "source": "team", "adopted": True, "chains": [{"proposals": [
        {"leap": "hidden", "name": "Unseen foreground microlens", "idea": "A lens magnifies it 3 times.", "chosen": True},
        {"leap": "new", "name": "Slow red flare", "idea": "A flare 2 mag redder.", "chosen": False}]}]},
        {"object": "ZTF25aatzejc", "source": "leverrier", "chains": []}]


def test_the_logbook_gets_spanish_beside_the_english(tmp_path):
    path = tmp_path / "logbook.json"
    path.write_text(json.dumps(lanes()))
    answers = {"Slow red flare": "Destello rojo lento", "A lens magnifies it 3 times.": "Una lente la hace 3 veces más brillante.",
               "A flare 2 mag redder.": "Un destello 3 mag más rojo."}
    usd = spanish.logbook(model(lambda notes: json.dumps({k: answers[v] for k, v in notes.items()})), path)
    hidden, new = json.loads(path.read_text())[0]["chains"][0]["proposals"]
    assert usd > 0 and "más brillante" in path.read_text()
    assert hidden == lanes()[0]["chains"][0]["proposals"][0] | {
        "name_es": "Microlente invisible en primer plano", "idea_es": "Una lente la hace 3 veces más brillante."}
    assert new == lanes()[0]["chains"][0]["proposals"][1] | {"name_es": "Destello rojo lento"}


def test_a_failed_call_leaves_the_logbook_in_english(tmp_path):
    path = tmp_path / "logbook.json"
    path.write_text(json.dumps(lanes()))
    with pytest.raises(RuntimeError):
        spanish.logbook(model(error=RuntimeError("down")), path)
    assert json.loads(path.read_text()) == lanes()
