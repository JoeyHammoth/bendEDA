# The self-hosted tools runner (issue #12)

The `bend-and-eda` job runs the gates that need Bend and the OSS CAD Suite in the
same place: law lint, model mutation, the canary suite and translation fidelity.
It is skipped until a runner exists, and the skip is deliberate — a gate that
cannot run must not report a pass.

## What is in the repository already

- `.github/workflows/ci.yml` job `bend-and-eda`, `runs-on: [self-hosted, linux, bendeda-tools]`.
- `if: vars.BENDEDA_TOOLS_RUNNER == 'true'` — the job stays skipped, never green,
  until the variable is set.
- The job body: `bendeda canary --image pinned`, `bendeda law lint tasks --recursive`,
  `bendeda tf run --all`.

## What needs a host

Registration cannot be done from this repository; it needs a machine the owner
controls and a registration token.

1. On the host, install Docker, Python 3.12+, and the pinned images
   (`bendeda/bend:2.0.40`, `bendeda/oss-cad:2026-11-20`), or let the job build
   them once and cache them.
2. Register the runner with the labels the job asks for:

   ```bash
   # token from Settings -> Actions -> Runners -> New self-hosted runner
   ./config.sh --url https://github.com/JoeyHammoth/bendEDA \
     --token <REGISTRATION_TOKEN> \
     --labels self-hosted,linux,bendeda-tools \
     --unattended --replace
   sudo ./svc.sh install && sudo ./svc.sh start
   ```

3. Set the repository variable, which is what un-skips the job:

   ```bash
   gh variable set BENDEDA_TOOLS_RUNNER --body true
   ```

4. Run the job once by hand (`gh workflow run ci.yml`) and check that it *fails*
   when a gate is broken. A first run that passes proves the wiring, not the gate.

## Required checks and branch protection

The checks required on `main` (set on 2026-11-25):

| Check | Why |
|---|---|
| `tests (py3.12)`, `tests (py3.13)` | the package and the fixtures |
| `repository hygiene` | secrets, licence headers, whitespace, oracle absence, DCO |
| `locked-file guard` | a locked artifact cannot change without an amendment |
| `docs site` | the site's links and assets |
| `harness image (pinned Dockerfile)` | the sandbox image builds offline, and the `run` → `oracle score` → `score` chain runs on it |
| `oss-cad suite image (pinned)` | the simulator and prover image builds, and the trace gate judges real RTL in it |
| `bend and EDA gates` | the reason the runner exists — **not** required yet; see below |

Protection settings:

- no direct pushes to `main`;
- one owner review, and two reviews for `tasks/`, `prereg/` and `amendments/`
  (enforced by `CODEOWNERS`);
- dismiss stale approvals on push;
- require the checks above, and require branches to be up to date before merge.

The image jobs were left out of the original five, and that had a cost: PR #49 merged
with a red `harness image (pinned Dockerfile)` because the job was not required, and its
defect — the proxy could not write the events directory — was only found afterwards.
Both image jobs are required now, so that cannot repeat.

`bend and EDA gates` stays unrequired until the tools runner exists (#12): the job is
skipped while `BENDEDA_TOOLS_RUNNER` is unset, and a required check that reports
`skipped` on every pull request would be a check that says nothing.

Setting the list needs an admin token; a token with only `repo` and `project` scopes
cannot do it. The endpoint replaces the whole list, so the existing five have to be
repeated:

```bash
gh api -X PATCH repos/OWNER/REPO/branches/main/protection/required_status_checks \
  -f strict=true \
  -f 'contexts[]=tests (py3.12)' -f 'contexts[]=tests (py3.13)' \
  -f 'contexts[]=repository hygiene' -f 'contexts[]=docs site' \
  -f 'contexts[]=locked-file guard' \
  -f 'contexts[]=harness image (pinned Dockerfile)' \
  -f 'contexts[]=oss-cad suite image (pinned)'
```

`CODEOWNERS` still cannot enforce the owner review or the two-review rule for
`tasks/`, `prereg/` and `amendments/`, because branch protection reports
`reviews: null` until the repository is on a paid plan or made public. That limit is
written here rather than assumed.

## The failure this avoids

If the runner is absent and the job is allowed to run, GitHub queues it forever
or fails the pull request for the wrong reason. If the job is deleted, the gates
disappear silently. The skip-with-reason is the third option: the run shows
`skipped`, the reason is in the workflow file, and no document claims the gates
passed.
