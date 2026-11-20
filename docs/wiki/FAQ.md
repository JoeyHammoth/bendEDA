# FAQ

### "Isn't proving the model pointless if the model isn't the RTL?"

Yes, if you stop there — which is why the programme defines a conformance ladder and measures its weakest rung instead of assuming it away. L0 proofs say nothing about Verilog; L1/L2 test the model against the RTL; L3 transfers the laws to properties proved on the RTL; and **translation fidelity** quantifies the gap between a law and its SVA translation. Ablation A1 exists specifically to test whether model-only proofs help RTL at all. If they do not, that is the finding.

### "If no human writes the laws, aren't you measuring one model grading another?"

Potentially — that is the sharpest threat, and Appendix J.5 states it in those terms. It is mitigated by cross-family authoring, mutation pressure on the law set (a blind-spot law set fails to kill plausible bugs), an independent oracle, an adversarial auditor, a same-family ablation (A7), and a moderator metric (LAW-FAR). None of these removes the threat; they make it measurable and reportable.

### "Why Bend at all? SymbiYosys already exists."

That is the null hypothesis, and C2 is the arm that tests it. C3 versus C2 asks whether the Bend workflow adds anything over an equivalent *locked* SVA pack. "Locking helps, Bend adds nothing" is a publishable, useful result — the study is designed so that answer is informative rather than embarrassing.

### "Doesn't the agent just weaken the spec until the proof passes?"

In C1 it can, which is exactly what RBW and STAR measure. In C2-C4 the specification is read-only, and a blocked write is logged rather than silently absorbed. Ablation A3 deliberately allows law proposals so the gaming rate can be observed under Bend too.

### "Aren't the tasks too small to generalise?"

They are small, and the external-validity limit is stated in every claim. The design compensates with tiers, three models, variants from private seeds, honeypots, and calibration against public benchmarks for difficulty ordering — never for inference.

### "Why publish a null result?"

Because the field's problem is not a shortage of plausible claims; it is a shortage of measurements that survive scrutiny. Publishing the protocol, the harness and the negative results is the contribution.

### "What does 'locked' actually mean here?"

The Conductor promotes a law set to `locked` after LA1-LA9 and LA9-A/B/C pass. From then on `locked/LOCKED.json` holds its hashes, the file is mounted read-only for every run, and CI refuses a change without an `amendment` label and a dated amendment record.

### "Bend's compiler is largely AI-written and unaudited. Why trust its verdicts?"

We do not trust them; we test them. A 30+ control canary suite must show zero false accepts or the Bend arms halt and the issue is reported upstream. The independent evaluator recomputes laws on enumerated reduced domains, and `--verdict` is used only if it actually works at the pinned release.

### "Is any of this running on hardware?"

No. This phase is completely digital: RTL, simulation, formal, synthesis reports. Ground truth is a hidden digital oracle, and "passes the oracle" is explicitly not "works on silicon". The hardware extension is designed (§14.10) but not built, and every hardware-dependent gate skips rather than passing.

### "How do I cite this?"

`CITATION.cff`. Cite the protocol version or tag you used — before `prereg-v1`, cite the commit. Citing the repository as a whole implies a stability the project does not yet claim.

### "Can I use the harness for my own project?"

Yes: Apache-2.0 for code, CC BY 4.0 for documents and task data. The plugin interfaces exist so that a law language, translator, gate or oracle can be added without forking. Keep the licensing and notice rules in `THIRD_PARTY.md` in mind if you redistribute a container with GPL tools in it.
