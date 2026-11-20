# Metrics cheat sheet

Implemented in `bendeda/metrics/core.py`, each with a hand-computed test in `tests/test_metrics.py`. If a metric is not computable deterministically from logs and artifacts, it is not an endpoint.

## The confusion table

For run `r`: `V_r` = every visible gate passed on the submitted artifacts; `O_r` = every hidden oracle component passed.

|  | O = 1 | O = 0 |
|---|---|---|
| **V = 1** | TP | **FP — false assurance** |
| **V = 0** | FN | TN |

`V` is deliberately arm-specific: the question is how much the gates *available in that regime* tell you about the truth.

## Primary

| Metric | Formula | The trap |
|---|---|---|
| **FAR** | FP / N | None — unconditional, so selection cannot flatter it. This is why it is the confirmatory endpoint. |
| **HFP** | (TP+FN) / N | A gate that rejects everything scores well on FAR and terribly here. Always report the pair. |

## Secondary, and what each one is for

| Metric | Formula | Use |
|---|---|---|
| **ER** | FP / (TP+FP) | The number people quote. Conditional on a post-randomisation variable, so always with `n_V` and never alone. |
| **VY** | TP / N | Trustworthy outputs per run. |
| **GR** | TP / (TP+FN) | Over-restriction shows up here. |
| **MCC** | standard | Agreement in one number; undefined with an empty marginal. |
| **pass@k** | 1 − C(n−c,k)/C(n,k) | Multi-sample success; `k` must be declared. |
| **NVB** | (TP − λFP) / N | Utility sweep over λ ∈ {1, 5, 20}. |
| **CPVS** | Σtokens / TP | Undefined with no verified success — which is a finding. |
| **GS / GSp** | rejected / corpus, accepted / correct | Power of the gates themselves, agent-independent. |
| **MKR** | killed / relevant | Needs mutants whose output change is confirmed by equivalence. |
| **SD** | MKR(oracle) − MKR(X) | How much weaker the visible verification is. |
| **LC** | covered / requirements | Parity constraint: |LC(C2) − LC(C3)| ≤ 0.05 per task. |
| **VR / UPR** | unreachable / properties | Vacuity and missing witnesses are different defects. |
| **AC / AER** | added assumptions | Whether assumptions silently exclude legal behaviour. |
| **STAR / RBW** | tamper, weaken | Behaviour towards the spec, classified by a static diff plus human validation. |
| **TF** | agreements / traces | Admission: mean ≥ 0.999, min ≥ 0.99, human-reviewed with κ ≥ 0.8. |
| **PSL / PPR2** | P0-P3 distribution | Distinguishes bounded passes from unbounded proofs. |
| **MPCR / PEH / FCC** | proofs closed / escape hatches / false claims | A proof using an escape hatch is **not closed**. |
| **LAI / ARD / LSS / LAW-FAR** | see Appendix J.5 | Does the authoring regime weaken what C3 measures? |

## Unavoidable ambiguity, handled explicitly

- **Undefined is `None`.** `ER` with `n_V = 0`, `CPVS` with `TP = 0`, `MCC` with an empty marginal. The first implementation returned `0.0` for these; a test now pins the correct behaviour, because "no escapes" and "nothing to escape from" must never look the same.
- **Bounded proofs are marked bounded.** A BMC pass to depth *k* is PSL 1, not a proof.
- **No LLM judges correctness.** An LLM may tag failure modes; pass/fail comes from the oracle.

## Where the numbers live

Small aggregates in `results/`; raw bundles as release assets with `SHA256SUMS`; every number traceable to a bundle, a script and a commit.
