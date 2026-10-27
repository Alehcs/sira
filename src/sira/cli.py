import argparse
import json
from pathlib import Path

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


def snapshot(args) -> None:
    from .snapshot import build

    m = build(args.out, workers=args.workers, rubin=not args.no_rubin, log=lambda s: print(s, flush=True))
    print(json.dumps({k: m[k] for k in ("counts", "splits", "valset")}, indent=2))
    print(f"failures: {len(m['failures'])}")


def check_reader(args) -> None:
    from .reader import check

    extra = {"reasoning_effort": args.effort} if args.effort else {}
    result = check(args.root, args.protocol, args.cases, args.model, few_shot=not args.zero_shot,
                   workers=args.workers, **extra)
    name = "-".join([args.model, args.protocol, args.cases] + ([args.effort] if args.effort else [])
                    + (["zero"] if args.zero_shot else []))
    out = Path("var") / f"reader-{name}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
    if result["errors"]:
        raise SystemExit(f"incomplete run: {result['errors']} reads failed, see {out}")


def probe(args) -> None:
    from . import catalogs
    from .fetch import client
    from .probe import run

    with client(verify=False) as bts_client:  # BTS serves a self-signed certificate
        bts_rows = catalogs.bts(bts_client)
    with client() as c:
        result = run(bts_rows, catalogs.microlensing(c), args.model)
    out = Path("var") / f"probe-{args.model}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(prog="sira")
    sub = parser.add_subparsers(required=True)
    sub.add_parser("costs", help="show spend against caps").set_defaults(run=costs)
    sub.add_parser("smoke", help="one tiny call per model").set_defaults(run=smoke)
    snap = sub.add_parser("snapshot", help="download the local data snapshot")
    snap.add_argument("--out", default="data/snapshot")
    snap.add_argument("--workers", type=int, default=8)
    snap.add_argument("--no-rubin", action="store_true")
    snap.set_defaults(run=snapshot)
    reader = sub.add_parser("check-reader", help="score the image reader on the real/bogus valset")
    reader.add_argument("--model", choices=["spark-open", "spark"], default="spark-open")
    reader.add_argument("--protocol", choices=["v1", "v1-symmetric", "v1-matched", "v2"], default="v2")
    reader.add_argument("--cases", choices=["dev", "valset", "holdout"], default="dev")
    reader.add_argument("--effort", help="reasoning effort, overrides the model default")
    reader.add_argument("--zero-shot", action="store_true")
    reader.add_argument("--root", default="data/snapshot")
    reader.add_argument("--workers", type=int, default=8)
    reader.set_defaults(run=check_reader)
    memory = sub.add_parser("probe", help="measure what a model remembers about known transients")
    memory.add_argument("--model", choices=["spark", "wonder"], default="spark")
    memory.set_defaults(run=probe)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
