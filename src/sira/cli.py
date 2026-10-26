import argparse
import json

from .costs import CostMeter
from .llm import LLM, SPARK, WONDER


def costs(_args) -> None:
    print(json.dumps(CostMeter().summary(), indent=2))


def smoke(_args) -> None:
    llm = LLM()
    ask = [{"role": "user", "content": "Reply with one word: ready"}]
    for name, call in [
        ("spark", lambda: llm.chat("meta", SPARK, ask, "smoke", reasoning_effort="minimal")),
        ("wonder", lambda: llm.chat("meta", WONDER, ask, "smoke", reasoning_effort="minimal")),
        ("spark-open", lambda: llm.fast(ask, "smoke")),
    ]:
        try:
            r = call()
            print(f"{name}: ok -> {r.choices[0].message.content!r}")
        except Exception as e:
            print(f"{name}: failed -> {e}")
    costs(None)


def main() -> None:
    parser = argparse.ArgumentParser(prog="sira")
    sub = parser.add_subparsers(required=True)
    sub.add_parser("costs", help="show spend against caps").set_defaults(run=costs)
    sub.add_parser("smoke", help="one tiny call per model").set_defaults(run=smoke)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
