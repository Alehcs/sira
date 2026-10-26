# SIRA

**An AI astronomer built to be proven wrong in public.**

SIRA investigates cosmic transients — supernovae, tidal disruption events, microlensing — using public alerts from real sky surveys (ZTF, via the ALeRCE broker). It proposes rival physical hypotheses, registers quantitative predictions *before* new observations arrive, and lets the data grade them. It decides when to wait, think harder, or ask for help, and it keeps a public, timestamped record of every bet.

Built for the Meta Global AI Developer Hackathon 2026 (Indie track, *Push the Frontier*), with Meta's Muse models.

> Status: under construction (hackathon started October 26, 2026).

## Built during the hackathon

Everything in this repository was written during the hackathon, starting October 26, 2026. The commit history is the record of what was built and when.

## Repository layout

- `main` — the project: code, site, workflows and documentation.
- `ledger` — data only: SIRA's bets, timestamp receipts and resolutions, appended automatically every night. The code on `main` reads it; nobody needs to switch branches.

## Data and acknowledgments

SIRA uses only public data. This project makes use of data from the Zwicky Transient Facility (ZTF), the ALeRCE broker, and the ZTF Bright Transient Survey. Full acknowledgments will be listed here as data sources are integrated.

## License

MIT — see [LICENSE](LICENSE).
