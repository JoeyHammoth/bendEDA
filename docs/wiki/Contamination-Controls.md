# Contamination controls

The repository is public and the oracle must stay hidden. Those two facts are only compatible with a protocol, not with good intentions.

## The commit-reveal protocol

| Step | Who | Public artifact |
|---|---|---|
| 1 | OAA develops the oracle in a separate private workspace | nothing |
| 2 | At the freeze, build a deterministic archive; compute SHA-256 of the plaintext and a Merkle root over per-task component hashes | `oracle_sealed/commitment.json` |
| 3 | Encrypt with `age`; private key held offline | `oracle_sealed/oracle.tar.age` |
| 4 | Commit both under the signed `prereg-v1` tag | tag + optional timestamp |
| 5 | During runs, decrypt only on the scoring host; agent containers have no route and no network; scan logs for oracle identifiers | nothing |
| 6 | At reveal, publish the key or plaintext | key |
| 7 | Anyone runs `bendeda oracle verify-commitment` | verification output |

Amendments publish a *new* commitment and keep the old one, so "we changed the oracle" is always visible as a diff in commitment hashes rather than an absence of evidence.

## Why the oracle is not in the repository at all

A public repository's history is forever. Deleting a committed oracle later does not un-publish it, and this project's own `tools/check_oracle_absence.py` refuses plaintext archives precisely because the mistake is irreversible.

## Contamination from the public repository itself

| Control | How |
|---|---|
| Canary GUID | One project-specific GUID with a "do not train on this" notice, placed in every task, prompt and result file |
| Private rotating variants | Public tasks are templates; evaluated instances come from private seeds |
| Model cutoff reporting | Each model's training cutoff recorded against the publication date |
| Time-split analysis | Pre-publication and post-publication models reported separately |
| Memorisation probes | Optional: prompt with the first half of a law file, measure verbatim continuation |
| Honeypots | Flawed specs detect memorised canonical solutions that ignore the flaw |

## Leakage audits

After each batch, logs are scanned for oracle identifiers, task paths that only the oracle knows, and seeded-bug names. A hit is an incident, not a curiosity: it is recorded in `amendments/` if it invalidates runs, and the affected runs are excluded with the exclusion listed in the results bundle.

## What this does *not* solve

- A model trained after publication may have memorised the public tasks. Time-split reporting names the problem; it does not remove it.
- A determined reader can infer something about the oracle from the commitment's task list. The commitment publishes which tasks have an oracle, not what it checks.

## Rules for contributors

1. Never commit oracle content, seeded bugs, or a reference proof.
2. Never paste oracle-related output into a public issue without checking it first.
3. If a contribution needs oracle knowledge to be reviewed, say so and use the private advisory channel.
