import json
import re
from pathlib import Path

from .agents import _json
from .costs import price
from .llm import SPARK, usage_of

# the site's own words from site/src/words.js, so the agents' notes read like the rest of the page
HYP = {"ia": ("Type Ia supernova", "Supernova tipo Ia"), "ibc": ("Type Ibc supernova", "Supernova tipo Ibc"),
       "ii": ("Type II supernova", "Supernova tipo II"), "tde": ("Tidal disruption", "Disrupción por marea"),
       "null": ("None of the above", "Ninguna de las anteriores"), "adopted": ("Invisible lens", "Lente invisible")}
IPCC_ES = {"virtually certain": "virtualmente cierto", "very likely": "muy probable", "likely": "probable",
           "about as likely as not": "tan probable como improbable", "unlikely": "improbable",
           "very unlikely": "muy improbable", "exceptionally unlikely": "excepcionalmente improbable"}
TERMS = {"light curve": "curva de luz", "forecast": "pronóstico", "measurements": "mediciones", "artifact": "artefacto",
         "bet": "apuesta", "science": "ciencia", "reference": "referencia", "difference": "diferencia",
         "reader": "lector", "lookout": "vigía", "theorist": "teórico", "skeptic": "escéptico",
         "director": "director", "forecaster": "pronosticador"}
NAMES_ES = {
    "Unseen foreground microlens": "Microlente invisible en primer plano",
    "Galactic microlensing event": "Evento de microlente galáctica",
    "Drifting zeropoint subtraction bias": "Sesgo por deriva del punto cero",
    "Microlensed underlying supernova": "Supernova de fondo con microlente",
    "Galactic point-lens microlensing": "Microlente puntual galáctica",
    "Drifting template subtraction leakage": "Fuga por deriva de la plantilla",
    "Lens on red background giant": "Lente sobre una gigante roja de fondo",
    "Microlensed red giant": "Gigante roja con microlente",
    "Red template subtraction drift": "Deriva de la resta con plantilla roja",
    "Foreground microlens magnification": "Magnificación por microlente en primer plano",
    "Drifting calibration subtraction residual": "Residuo de calibración a la deriva",
}
GLOSSARY = dict(HYP.values()) | IPCC_ES | TERMS
KNOWN = GLOSSARY | NAMES_ES  # a note that is just one of these needs no model
TASK = ("You translate notes written by the AI astronomers of SIRA, a public astronomy lab, from English into plain "
        "Latin American Spanish for its website. Translate the meaning faithfully and add nothing. Keep every number "
        "exactly as written, decimal point included; keep band letters (g, r, i), units (mag, microjansky, uJy, K, d), "
        "symbols and fit parameters (x1, c, z, chi2, p_yes) and identifiers (object names such as ZTF19aavisrq, "
        "question ids such as q2) unchanged. Use these Spanish terms: "
        + "; ".join(f"{en} = {es}" for en, es in GLOSSARY.items())
        + ". Reply with JSON only: the same keys, each with its note in Spanish.")
NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _numbers(text: str) -> list[str]:
    return sorted(NUMBER.findall(text))


def translate(llm, texts: list[str]) -> tuple[dict[str, str], float]:
    # one call for the lot; a note whose numbers come back changed stays in English
    known = {t: KNOWN[t] for t in texts if t in KNOWN}
    todo = [t for t in dict.fromkeys(texts) if t and t.strip() and t not in known]
    if not todo:
        return known, 0.0
    notes = json.dumps({str(i): t for i, t in enumerate(todo, 1)}, ensure_ascii=False)
    r = llm.chat("meta", SPARK, [{"role": "system", "content": TASK}, {"role": "user", "content": notes}], "spanish",
                 response_format={"type": "json_object"}, reasoning_effort="minimal", timeout=60)
    usd, data = price("meta", SPARK, usage_of(r)), _json(r.choices[0].message.content)
    out = {t: data[str(i)].strip() for i, t in enumerate(todo, 1) if isinstance(data.get(str(i)), str)}
    return known | {t: es for t, es in out.items() if es and _numbers(es) == _numbers(t)}, usd


def logbook(llm, path: Path) -> float:
    # Le Verrier's names and ideas in Spanish beside the English, for the Bitácora
    path = Path(path)
    lanes = json.loads(path.read_text())
    ideas = [p for lane in lanes for chain in lane["chains"] for p in chain["proposals"]]
    es, usd = translate(llm, [p[k] for p in ideas for k in ("name", "idea")])
    for p in ideas:
        p.update({f"{k}_es": es[p[k]] for k in ("name", "idea") if p[k] in es})
    path.write_text(json.dumps(lanes, separators=(",", ":"), ensure_ascii=False))
    return usd
