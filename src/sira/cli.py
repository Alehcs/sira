import argparse
import json
from pathlib import Path

from .costs import CostMeter
from .llm import LLM, SPARK, WONDER


def site(args) -> None:
    from .site import export, replays

    if args.replays:
        replays(Path("var"), Path(args.root), Path(args.out))
        print(f"replays written to {args.out}")
    else:
        print(json.dumps(export(Path(args.ledger), Path(args.out))["record"], indent=2))


def investigate(args) -> None:
    from .visits import run

    print(json.dumps(run(args.object, int(args.id) if args.id else None), indent=1))


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


def accept(args) -> None:
    from . import accept as checks

    if args.test == "at3":
        import pytest
        raise SystemExit(pytest.main(["-q", "tests/test_firewall.py", "tests/test_models.py"]))
    result = getattr(checks, args.test)(args.root)
    out = Path("var") / f"accept-{args.test}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))


def live(args) -> None:
    from .live import run

    print(json.dumps(run(Path(args.ledger), args.n, team=args.team, night_usd=args.night_usd), indent=2))


def challenge(args) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timezone

    from . import crowd
    from .fetch import client
    from .ledger import Ledger

    book, now, c = Ledger(Path(args.ledger)), datetime.now(timezone.utc), client()
    if args.publish:
        result = crowd.publish_round(book, c, now)
    else:
        with ThreadPoolExecutor(8) as pool:
            result = crowd.open_round(book, c, LLM(), now, pool, args.round_usd, dry=args.dry_run)
    print(json.dumps(result, indent=2))


def verify(args) -> None:
    from .fetch import client
    from .verify import verify as check

    result = check(Path(args.ledger), client(), online=args.online, known=tuple(args.since))
    print(json.dumps(result, indent=2))
    if not result["passes"]:
        raise SystemExit(1)


def climate(args) -> None:
    from .baselines import CLIMATE, climatology

    table = climatology(Path(args.root))
    CLIMATE.write_text(json.dumps(table, indent=1) + "\n")
    print(json.dumps(table, indent=2))


def leverrier(args) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from .leverrier import case
    from .llm import LLM

    with ThreadPoolExecutor(3) as pool:
        report = case(Path(args.root), args.oid, LLM(), args.gap, args.window, pool)
    out = Path("var") / f"leverrier-{args.oid}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({k: v for k, v in report.items() if k != "events"}, indent=2, default=str))


def moments(args) -> None:
    from .highlights import highlights

    for m in highlights(Path(args.ledger), args.top):
        print(f"[{m['kind']}] {m['time']} {m['object']}: {m['text']}")


def replay(args) -> None:
    from .llm import LLM
    from .replay import pick, report, run

    root, out = Path(args.root), Path(args.out)
    if not args.report_only:
        oids = args.oids or pick(root, args.split, args.per)
        print(json.dumps(run(root, oids, out, LLM(), args.workers), indent=1))
    result = report(root, out)
    (out / "report.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=2))


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
    check = sub.add_parser("accept", help="run an acceptance test from the roadmap")
    check.add_argument("test", choices=["at1", "at2", "at3"])
    check.add_argument("--root", default="data/snapshot")
    check.set_defaults(run=accept)
    night = sub.add_parser("live", help="score open bets, place new ones and anchor the ledger")
    night.add_argument("--ledger", default="ledger")
    night.add_argument("-n", type=int, default=15)
    night.add_argument("--team", action="store_true", help="let the Muse agent team triage, argue and choose bets")
    night.add_argument("--night-usd", type=float, default=4.0, help="stop investigating once the team spent this")
    night.set_defaults(run=live)
    game = sub.add_parser("challenge", help="seal SIRA's answers to today's Beat SIRA questions, or open them to players")
    game.add_argument("--ledger", default="ledger")
    game.add_argument("--publish", action="store_true", help="put today's sealed questions in Supabase for players")
    game.add_argument("--dry-run", action="store_true", help="pick and forecast only: no ledger, no Supabase")
    game.add_argument("--round-usd", type=float, default=2.0, help="stop forecasting once the round spent this")
    game.set_defaults(run=challenge)
    proof = sub.add_parser("verify", help="check the ledger chain, its receipts and that bets were sealed in time")
    proof.add_argument("--ledger", default="ledger")
    proof.add_argument("--online", action="store_true", help="also check every scored measurement against ALeRCE")
    proof.add_argument("--since", nargs="*", default=[], metavar="SEQ:HASH",
                       help="heads seen before, which must still be in the ledger")
    proof.set_defaults(run=verify)
    clim = sub.add_parser("climatology", help="rebuild the B0 table from the snapshot's dev half")
    clim.add_argument("--root", default="data/snapshot")
    clim.set_defaults(run=climate)
    leap = sub.add_parser("leverrier", help="replay a case: bet without the answer's hypothesis, call Le Verrier on surprise")
    leap.add_argument("oid")
    leap.add_argument("--root", default="data/snapshot")
    leap.add_argument("--gap", type=int, default=10)
    leap.add_argument("--window", type=int, default=40)
    leap.set_defaults(run=leverrier)
    best = sub.add_parser("highlights", help="list the ledger's best moments, for the video and posts")
    best.add_argument("--ledger", default="ledger")
    best.add_argument("--top", type=int, default=20)
    best.set_defaults(run=moments)
    rerun = sub.add_parser("replay", help="replay snapshot cases through the whole lab, with B0, B1 and B2 beside it")
    rerun.add_argument("oids", nargs="*")
    rerun.add_argument("--root", default="data/snapshot")
    rerun.add_argument("--split", default="dev", choices=["dev", "test"])
    rerun.add_argument("--per", type=int, default=2, help="cases per category when no ids are given")
    rerun.add_argument("--out", default="var/replay/dev")
    rerun.add_argument("--workers", type=int, default=4)
    rerun.add_argument("--report-only", action="store_true")
    rerun.set_defaults(run=replay)
    web = sub.add_parser("site", help="write the public site's data from the ledger, or from the saved replays")
    web.add_argument("--ledger", default="ledger")
    web.add_argument("--out", default="site/public/data")
    web.add_argument("--replays", action="store_true", help="write the replay files from var/ instead, locally")
    web.add_argument("--root", default="data/snapshot")
    web.set_defaults(run=site)
    visit = sub.add_parser("investigate", help="investigate one live object for a visitor of the site, outside the ledger")
    visit.add_argument("object")
    visit.add_argument("--id", help="the site's investigation to report to; without it the run only prints")
    visit.set_defaults(run=investigate)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
