# Claims

Every public sentence about SIRA (video, write-up, site, posts) must have a row here, with the number behind it and where anyone can check it. A sentence without a row is not said.

The test-split numbers come from the evaluation pre-registered in [`evidence/plan.json`](evidence/plan.json), timestamped by FreeTSA on 2026-11-01 at 11:58 UTC (`evidence/plan.json.tsr`, plus an OpenTimestamps proof) before any test object was replayed. `make reproduce` recomputes all of them from the files in `evidence/` and the public ledger, with no API keys and no paid calls.

## Unlocked

| Sentence | Number | Check |
|---|---|---|
| On objects it had never seen, SIRA forecast better than Muse alone. | +0.98 nats per measurement (95% interval 0.41 to 1.64), about 2.7 times the probability on what the sky did (e^0.98, a geometric mean); ahead on 26 of 37 objects; run a +1.16, run b +0.81, both above zero | `evidence/results.json` → `test.primary.b2`, `test.by_run` |
| On objects it had never seen, SIRA forecast better than its own physics alone. | +0.30 nats per measurement (0.12 to 0.52), about 1.35 times the probability on what the sky did; ahead on 21 of 37 | `test.primary.b1` |
| SIRA's edge comes from pooling physics with Muse's own forecast. | Taking Muse's forecast out costs 0.28 nats (0.16 to 0.45); the team's reweighting adds 0.005 (−0.015 to 0.006), nothing measurable | `test.ablations` |
| SIRA's 90% intervals hold the truth about 90% of the time. | 94.8% on 1,064 test measurements (a little wide); Muse alone 86.5%, physics alone 90.2% | `test.forecasters` |
| From a well-measured SN Ia light curve alone, SIRA's physics code puts its host galaxy at the right distance to within about 6%. | Median redshift error 5.6% on 18 well-measured test SN Ia; 12.3% on all 29, above the 10% its acceptance test asks of all fits. Other types treated as Ia come out 65% too far. Physics code, no Muse call | `physics.distance`, figure `distance` |
| Asked "lens or supernova?", SIRA's physics code was right every time it decided, and said "I don't know" otherwise. | 26 of 26 decisive verdicts right, 7 of 33 abstained (21%), judged on the part of each light curve it never saw. Physics code, no Muse call | `physics.verdicts`, figure `verdicts` |
| When the sky surprised SIRA, Muse Wonder proposed an invisible lens, and it forecast the data it had not seen far better than the old hypotheses. | The physics was surprised on 6 of 54 test lensing events; Le Verrier's proposal won its sealed test (Neptune, e ≥ 20) on 4, abstained on 1, lost on 1. The lens is one of the 7 pieces Wonder builds models from; the lab's own hypotheses (Ia, II, Ibc, TDE) never include it. No SN Ia (0 of 29) surprised the physics | `leverrier`, figure `team_size` |
| One Le Verrier did as well as five, at a fifth of the cost. | 4 Neptune verdicts with 1, 3 or 5 proposals per surprise; US$0.43 against US$2.11 | `leverrier.sizes` |
| Muse Spark Open, the open-weights model, tells a real new source from a bad subtraction on about 91% of ZTF candidates it was never tuned on. | Balanced accuracy 0.913 (95% interval 0.869 to 0.956) and AUC 0.97 on 160 held-out candidates: 80 real (2024 supernovae of the Bright Transient Survey) and 80 bogus as labelled by ALeRCE's stamp classifier. Measured on Oct 27 against a 0.85 gate set before the run, not part of the timestamped plan. US$0.0097 a read | `reader.v2`, `evidence/reader/holdout-v2.json` |
| An investigation costs about 16 US cents in Muse calls. | US$0.159 per investigated transient, 42 live investigations over 4 nights | `live.cost`, figure `live` |
| Every bet is sealed before the sky answers, and anyone can check it. | Hash chain, FreeTSA RFC 3161 receipts and OpenTimestamps proofs on the `ledger` branch | `uv run sira verify --ledger ledger` |

## Measured, not a selling point

| Finding | Number | Check |
|---|---|---|
| On SN Ia, physics alone is slightly better than SIRA. | SIRA − physics −0.06; SIRA ahead on 2 of 11 Ia | `test.by_class.ia` |
| Le Verrier also made a false discovery. | In both full test replays it proposed a lens for a superluminous supernova (ZTF25abiwxmw), and the lens won its sealed test (log10 e 3.27 and 2.63 on 10 measurements): the lab has no superluminous model, so the lens beat the ones it had. Its other Neptune verdicts there were 2 real lensing events | `test.team.verdicts`, `evidence/test/a/ZTF25abiwxmw/ledger.jsonl` |
| On all 29 test SN Ia, the distance misses the bar its acceptance test sets. | 12.3% median error against 10%; the plan reports both the 18 well-measured and all 29 | `physics.distance.passes` |
| The 50/50 pool was adopted after the first dev replay. | The plan says the pool was fixed before any dev result could tune it. Its share was never tuned, but pooling itself came 32 minutes after the first dev replay showed Muse alone beating the physics (commits a130172 and d25af11, Oct 27), days before any test object was replayed | `git log` |
| Review by Muse Wonder at max effort did not change the forecasts' quality. | −0.005 nats on 106 reviewed measurements (−0.035 to 0.153), US$3.45 on the test set | `test.team.director` |
| The instrument and memory skeptics never changed a test bet. | 0 bets dropped, 0 objects flagged as remembered; US$0.013 extra per bet | `test.team.skeptics` |
| The lookouts' vote of three rarely changes the call. | Changed 1 of 17 voted decisions, US$0.34 extra | `live.lookouts` |
| Three of the 40 pre-registered test objects got no bet. | Their only checkpoint had 4 detections and the physics needs 5 | `test.failed` |
| The test evaluation cost US$45 in Muse calls. | Two runs of 40 objects, 350 bets | `test.cost_usd` |
| The reader's second protocol is not significantly better than its first. | 0.913 against 0.875 on the same 160 candidates; 13 reads gained, 7 lost, McNemar p 0.26 | `reader.v2_vs_v1` |

## Measured after the plan

Computed from the same sealed test ledgers once the results were in, so not pre-registered. `make reproduce` recomputes them too.

| Finding | Number | Check |
|---|---|---|
| Muse's forecast, not averaging, carries SIRA's edge. | Pooling the same physics half and half with climatology instead of Muse's forecast loses 0.30 nats per measurement (0.11 to 0.54); Muse ahead on 28 of 37 objects. Alone, Muse scores about the same as climatology (−5.07 against −5.12) | `test.posthoc.muse_or_climatology_as_partner`, `test.forecasters` |
| On the test replays' yes/no questions, SIRA was right about 3 times in 4, and Muse alone about as often. | 223 answered questions on 33 objects: SIRA 75.8% right (Brier 0.159), Muse alone 77.1% (0.166), physics alone 67.7% (0.220), climatology 59.2% (0.243); always answering the base rate scores 0.246 | `test.posthoc.questions` |

## Not unlocked yet

| Sentence | Waits for |
|---|---|
| SIRA's live record: X of Y questions right. | Answered questions at the freeze head, the nightly of 2026-11-03 (pre-registered). None answered up to seq 689. ZTF has sent no data since Oct 29, 13:18 UTC; questions whose window falls in the gap are void by the sealed rule, reported and not counted |
| Calibration night by night (F2). | At least 30 answered live questions |
| Anything about SIRA beating human players. | Answered Beat SIRA rounds |

## Never say

- That SIRA discovered new physics. Le Verrier rediscovered known lensing events on archival data it was not told about.
- That the agent team makes the forecasts better. The ablations say the pooled Muse forecast does; the team asks the questions, explains and proposes.
- 5.6% without "12.3% on all 29".
- That Wonder came up with the lens from nothing. A lens is one of the 7 pieces it builds from.
- That Le Verrier never made a false discovery, or that a Neptune verdict confirms a model. It means the model forecast unseen data far better than the old hypotheses.
