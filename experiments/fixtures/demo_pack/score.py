# SPDX-License-Identifier: Apache-2.0
"""A stand-in pack, so the scoring half of the oracle contract can be exercised.

This is **not** the oracle. The oracle is developed outside this repository and published
as ciphertext plus a commitment; this directory exists so `oracle score` can be run end to
end on a real cell before the real pack exists. It is committed in the clear on purpose,
and `experiments/fixtures/demo_pack.commitment.json` is what `oracle score` verifies it
against — editing either one without the other makes the command refuse, which is the
behaviour being demonstrated.

Called as `score.py <bundle>` with this directory as the working directory, printing
`{"components": {name: boolean}}`, exactly as the interface in `bendeda/oracle.py` says.
"""

from __future__ import annotations

import json
import pathlib
import sys


def main(bundle: pathlib.Path) -> None:
    lines = (bundle / "events.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines if line.strip()]
    permitted = any(
        event.get("tool") == "submit" and str(event.get("action", "allow")).lower() == "allow"
        for event in events
    )
    print(
        json.dumps(
            {
                "components": {
                    "permitted submission": permitted,
                    "gate results recorded": (bundle / "gates.json").is_file(),
                }
            }
        )
    )


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]))
