# demo_pack

A stand-in for the sealed oracle pack, so `oracle score` can be exercised on a real run
bundle. It is **not** the oracle: the real pack is developed outside this repository and
published only as ciphertext plus a commitment.

```bash
bendeda run --matrix experiments/matrices/smoke.json --limit 1
bendeda oracle score --pack experiments/fixtures/demo_pack \
  --commitment experiments/fixtures/demo_pack.commitment.json \
  --bundle .bend-cache/runs/smoke/C0-toy_counter-s1 --host demo-pack
```

`score.py` reports two components from the bundle: whether the proxy permitted a
submission, and whether gate results were recorded. It reads nothing outside the bundle,
so it needs no key and no network.

`commitment.json` (one directory up) is the Merkle commitment `oracle score` verifies the
pack against. It is a hash, not a secret. `tests/test_oracle.py` fails if the pack and the
commitment drift apart, and changing the pack on purpose means regenerating it:

```bash
python -c "from pathlib import Path; from bendeda import oracle; \
Path('experiments/fixtures/demo_pack.commitment.json').write_text( \
oracle.build_commitment(Path('experiments/fixtures/demo_pack')).as_json(), encoding='utf-8')"
```
