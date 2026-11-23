# Sealed-oracle commit-reveal

Issue #13, Phase 0.10. Two commands replace the stubs:

```console
$ bendeda oracle seal <plaintext-dir> --recipient <age-key> --out oracle_sealed
$ bendeda oracle verify-commitment <plaintext-dir> --commitment oracle_sealed/commitment.json
```

`seal` builds a deterministic archive, hashes every component, folds the hashes
into one Merkle root and records it. `verify-commitment` recomputes both from a
plaintext directory and compares. The second command needs **no key and no
decryption**, because the commitment is built over the plaintext before
encryption — that is what makes it verifiable by a reader who was never given the
oracle.

## Determinism is the format

A `tar czf` embeds mtimes, owners and directory order, so the same files produce a
different archive on every machine. The archive here is written member by member,
sorted by path, with `mtime = 0`, `uid = gid = 0`, empty `uname`/`gname` and mode
`0644`. The test builds the same tree twice with different mtimes and different
write order and requires byte-identical archives and the same root.

Two details that were decided rather than inherited:

- **Odd Merkle levels are promoted, not duplicated.** Duplicating the last node
  (the Bitcoin convention) makes a list and the same list with its last item
  doubled share a root. Promotion cannot, and it is one sentence to explain.
- **Leaves are domain-separated.** A leaf is `sha256(0x00 || path || 0x00 ||
  digest)` and a node is `sha256(0x01 || left || right)`, so a leaf hash can
  never be read as a node hash.
- **The commitment names the components.** It publishes which files the oracle
  has and their hashes; it does not publish their contents. That is the intended
  disclosure — the contamination-controls page already says the commitment
  reveals the task list, not the checks.

## Evidence

```console
$ python -m unittest tests.test_oracle -v
test_two_builds_of_the_same_content_agree_byte_for_byte ... ok
test_the_archive_records_no_timestamp_or_owner ... ok
test_one_changed_byte_changes_the_root ... ok
test_an_unchanged_tree_has_no_differences ... ok
test_a_changed_file_is_named ... ok
test_an_added_and_a_missing_file_are_both_reported ... ok
test_a_dry_run_writes_nothing ... ok
test_no_recipient_refuses_rather_than_writing_plaintext ... ok
test_no_age_refuses ... ok
test_seal_writes_ciphertext_a_commitment_and_sums ... ok
test_verification_passes_and_fails_on_one_byte ... ok
test_the_cli_path_verifies_without_decrypting ... ok
test_a_missing_commitment_is_exit_three ... ok
test_the_repository_is_clean ... ok
test_a_canary_in_a_task_file_is_refused ... ok
test_a_canary_file_without_a_guid_is_refused ... ok
Ran 17 tests
OK
```

The one-byte tamper is not hypothetical: appending a single space to
`a.bend` produces

```text
oracle verify-commitment: 1 component(s) differ from the commitment
  a.bend: committed d690929663d5... but now 481e81c216fb...
  committed root 08da7bf30a014054cc461c35027d09232dfd0557f487bee1dd5fe936aa232966
  recomputed     f844a588eb1fd125e7f76bf4d0d350bd4ba63a2640e8ff4e1d80cb357009f418
```

and exit code 1. `--dry-run` prints the same root and writes nothing, which is
also a CI step.

## The canary

`oracle_sealed/canary.txt` mints a public GUID. Public is the point: it is a
marker that must never appear in an agent's context or a task file, so its
presence anywhere it does not belong is a finding. `tools/check_oracle_absence.py`
extracts it and refuses any file under `tasks/` that contains it. The same check
still refuses plaintext archives and non-ciphertext files under `oracle_sealed/`.

A local false positive was fixed at the cause while building this:
`.bend-cache/*.tar.gz` (the pinned Bend archives downloaded by
`tools/fetch_bend.py`) were reported as plaintext oracle archives on every
developer machine. They are build inputs, never repository artifacts, and a fresh
CI checkout never has them, so `.bend-cache` is now skipped. The check is about
what could be committed.

## Exit codes

| Code | `seal` | `verify-commitment` |
|---|---|---|
| 0 | archive sealed, commitment written (or dry run printed) | root matches every component |
| 1 | encryption ran and failed, or the dry run could not read the input | at least one component differs; roots printed |
| 3 | no recipient, no `age`, or unreadable input — nothing was sealed | no directory, no commitment, or an unreadable commitment |

Exit 3 for "cannot encrypt" is deliberate: writing a plaintext archive so the
command can exit 0 would defeat the guard that rejects it.

## Limits

- `age` is not installed in this development environment or in the harness image,
  so the encryption path is exercised with a fake `age` executable that prefixes
  its input. That tests the plumbing — argv, stdin, output file, cleanup on
  failure — but **not** `age` itself. The first real seal on a scoring host must
  be recorded with the `age` version in `THIRD_PARTY.md`.
- Decryption and scoring are Phase 2 (`oracle score` is still a stub that exits
  3). This phase proves the commitment, not the scoring.
- The commitment is not signed. It is published as a commit, and Phase 3's
  `prereg-v1` tag is what gives it a time; a signature is a Phase 3 decision.
- The archive is USTAR and rejects paths over 100 bytes. That is a deliberate
  refusal rather than a silent switch to PAX, which would embed timestamps.
