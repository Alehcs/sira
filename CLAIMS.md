# Claims

Every public sentence about SIRA (video, write-up, site, posts) must have a row here, with the number behind it and where anyone can check it. A sentence without a row is not said.

The test-split numbers come from the evaluation pre-registered in [`evidence/plan.json`](evidence/plan.json), timestamped by FreeTSA on 2026-11-01 at 11:58 UTC (`evidence/plan.json.tsr`, plus an OpenTimestamps proof) before any test object was replayed. `make reproduce` recomputes all of them from the files in `evidence/` and the public ledger, with no API keys and no paid calls.

## Unlocked

| Sentence | Number | Check |
|---|---|---|
| On objects it had never seen, SIRA forecast better than Muse alone. | +0.98 nats per measurement (95% interval 0.41 to 1.64), ahead on 26 of 37 objects; run a +1.16, run b +0.81, both above zero | `evidence/results.json` → `test.primary.b2`, `test.by_run` |
| On objects it had never seen, SIRA forecast better than its own physics alone. | +0.30 nats per measurement (0.12 to 0.52), ahead on 21 of 37 | `test.primary.b1` |
| SIRA's edge comes from pooling physics with Muse's own forecast. | Taking Muse's forecast out costs 0.28 nats (0.16 to 0.45); the team's reweighting adds 0.005 (−0.015 to 0.006), nothing measurable | `test.ablations` |
| SIRA's 90% intervals hold the truth about 90% of the time. | 94.8% on 1,064 test measurements (a little wide); Muse alone 86.5%, physics alone 90.2% | `test.forecasters` |
| From an SN Ia light curve alone, SIRA puts its host galaxy at the right distance to within about 6%. | Median redshift error 5.6% on 18 well-measured test SN Ia; 12.3% on all 29. Other types treated as Ia come out 65% too far | `physics.distance`, figure `distance` |
| Asked "lens or supernova?", SIRA was right every time it decided, and said "I don't know" otherwise. | 26 of 26 decisive verdicts right, 7 of 33 abstained (21%), judged on the part of each light curve it never saw | `physics.verdicts`, figure `verdicts` |
| When the sky surprised SIRA, Muse Wonder proposed the invisible lens, and unseen data confirmed it. | The physics was surprised on 6 of 54 test lensing events; Le Verrier's proposal won its sealed test (Neptune, e ≥ 20) on 4, abstained on 1, lost on 1. No SN Ia (0 of 29) set it off, so no false discovery | `leverrier`, figure `team_size` |
| One Le Verrier found as much as five, at a fifth of the cost. | 4 discoveries with 1, 3 or 5 proposals per surprise; US$0.43 against US$2.11 | `leverrier.sizes` |
| An investigation costs about 16 US cents in Muse calls. | US$0.159 per investigated transient, 42 live investigations over 4 nights | `live.cost`, figure `live` |
| Every bet is sealed before the sky answers, and anyone can check it. | Hash chain, FreeTSA RFC 3161 receipts and OpenTimestamps proofs on the `ledger` branch | `uv run sira verify --ledger ledger` |

## Measured, not a selling point

| Finding | Number | Check |
|---|---|---|
| On SN Ia, physics alone is as good as SIRA. | SIRA − physics −0.06, ahead on 2 of 11 Ia | `test.by_class.ia` |
| Review by Muse Wonder at max effort did not change the forecasts' quality. | −0.005 nats on 106 reviewed measurements (−0.035 to 0.153), US$3.45 on the test set | `test.team.director` |
| The instrument and memory skeptics never changed a test bet. | 0 bets dropped, 0 objects flagged as remembered; US$0.013 extra per bet | `test.team.skeptics` |
| The lookouts' vote of three rarely changes the call. | Changed 1 of 17 voted decisions, US$0.34 extra | `live.lookouts` |
| Three of the 40 pre-registered test objects got no bet. | Their only checkpoint had 4 detections and the physics needs 5 | `test.failed` |
| The test evaluation cost US$45 in Muse calls. | Two runs of 40 objects, 350 bets | `test.cost_usd` |

## Not unlocked yet

| Sentence | Waits for |
|---|---|
| SIRA's live record: X of Y questions right. | Answered questions at the freeze head, the nightly of 2026-11-03 (pre-registered). None answered at head 689 |
| Calibration night by night (F2). | At least 30 answered live questions |
| Anything about SIRA beating human players. | Answered Beat SIRA rounds |

## Never say

- That SIRA discovered new physics. Le Verrier rediscovered known lensing events on archival data it was not told about.
- That the agent team makes the forecasts better. The ablations say the pooled Muse forecast does; the team asks the questions, explains and proposes.
- 5.6% without "12.3% on all 29".
