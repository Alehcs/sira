# SIRA

**An AI astronomer built to be proven wrong in public.**

SIRA investigates cosmic transients — supernovae, tidal disruption events, microlensing — using public alerts from real sky surveys (ZTF, via the ALeRCE broker). It proposes rival physical hypotheses, registers quantitative predictions *before* new observations arrive, and lets the data grade them. It decides when to wait, think harder, or ask for help, and it keeps a public, timestamped record of every bet.

Built for the Meta Global AI Developer Hackathon 2026 (Indie track, *Push the Frontier*), with Meta's Muse models.

> Status: betting live since October 27, 2026; still being built during the hackathon.

## Built during the hackathon

Everything in this repository was written during the hackathon, starting October 26, 2026. The commit history is the record of what was built and when.

## Check the bets yourself

Every evening a public GitHub Actions run scores SIRA's open bets against what the sky did, places new ones, and appends everything to `ledger.jsonl` on the `ledger` branch. Each entry carries the hash of the one before it, so changing any bet breaks every hash after it. The newest entry is then sealed with an RFC 3161 timestamp from FreeTSA and an OpenTimestamps proof that Bitcoin confirms within hours.

```bash
git clone https://github.com/Alehcs/sira && cd sira
git worktree add ledger origin/ledger
uv run sira verify --ledger ledger --online
```

`verify` checks every entry against the protocol below, rebuilds the hash chain, checks every receipt against the FreeTSA root shipped in this repository, checks that each bet was sealed within an hour of being made, recomputes every score and answer from the sealed forecast, opens SIRA's sealed Beat SIRA answers and rescores the players, and with `--online` checks every scored measurement against the ALeRCE archive. Pass a head you saw before (`--since SEQ:HASH`) to catch a rewritten history.

Without SIRA's code, for any sealed head `H`:

```bash
shasum -a 256 ledger/receipts/H.json        # prints H
openssl ts -verify -digest H -in ledger/receipts/H.tsr -CAfile src/sira/freetsa_ca.pem
ots verify ledger/receipts/H.json.ots       # needs a Bitcoin node
```

**What the receipts cannot prove.** They show that a bet existed at a given time, not that it was the only bet: someone running private copies could publish only the luckiest one. Here, every anchor names the commit and the Actions run that made it, and each run's log is public. Scores also depend on the photometry ALeRCE serves.

## The protocol

The ledger format is open, so any forecaster (a classifier, a broker, another AI scientist) can be graded the same way. Its schema is [`src/sira/ledger.schema.json`](src/sira/ledger.schema.json) (JSON Schema 2020-12).

- **Entries.** One JSON object per line of `ledger.jsonl`, with `seq`, `time`, `kind`, `payload`, `prev` and `hash`. `hash` is the SHA-256 of the entry without it, written as RFC 8785 JSON, and `prev` is the hash of the entry before.
- **Bets.** For each future time and band, the expected flux as a mixture of Gaussians (`[name, weight, mean, sd]`), plus an optional yes or no question with its probability. Rivals sealed beside it (`baselines`) are graded on the same data.
- **Anchors.** The head of the chain, stamped by FreeTSA (RFC 3161) and by OpenTimestamps. A bet counts from the first anchor that covers it.
- **Outcomes and answers.** Every measurement taken after the seal is scored for the bet and each rival (log score, PIT, CRPS), and each question is settled by the first measurement near its time.
- **Everything else.** `event` says who worked, with which model and at what cost; `surprise` and `verdict` come from Le Verrier; `round`, `reveal`, `crowd` and `crowd_answer` are Beat SIRA.

To hold your own forecaster to it, write its bets in this shape, anchor the head after each batch, append outcomes as the data arrive, and run `sira verify --ledger <dir>`.

## Repository layout

- `main` — the project: code, site, workflows and documentation.
- `ledger` — data only: SIRA's bets, timestamp receipts and resolutions, appended automatically every night. The code on `main` reads it; nobody needs to switch branches.

## Data and acknowledgments

SIRA uses only public data:

- Alerts, light curves and image stamps from the [Zwicky Transient Facility](https://www.ztf.caltech.edu) (ZTF), served by the [ALeRCE](https://alerce.science) broker.
- Classifications and redshifts from the [ZTF Bright Transient Survey](https://sites.astro.caltech.edu/ztf/bts/explorer.php).
- Rubin Observatory alerts through the [Fink](https://fink-broker.org) broker.
- Host galaxy images from the [DESI Legacy Imaging Surveys](https://www.legacysurvey.org/acknowledgment/).
- The ZTF DR17 microlensing catalog by R. Zhai ([doi:10.5281/zenodo.13829674](https://doi.org/10.5281/zenodo.13829674), [arXiv:2311.18627](https://arxiv.org/abs/2311.18627)).

## License

MIT — see [LICENSE](LICENSE).
