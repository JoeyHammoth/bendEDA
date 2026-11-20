# Security policy

## What this project runs

BendEDA executes **model-generated code**: an agent writes SystemVerilog and Bend,
and the harness compiles and simulates it. The realistic security surface is
therefore not a web application but a sandbox:

| Surface | Risk | Control |
|---|---|---|
| Agent-generated RTL / testbenches | Simulator escape, resource exhaustion | No network, CPU/memory/time cgroups, disposable container per run |
| Model-generated shell or Python | Arbitrary code execution on the host | Tools only via MCP through the policy proxy; no direct shell |
| Protected specification files | Tampering to make a gate pass | Read-only mounts, hash manifests, proxy audit log |
| Sealed oracle | Leakage into the agent context or the public repo | Separate host, encrypted archive, commitment published before runs |
| Dependencies | Supply-chain compromise | Pinned versions and digests, Dependabot, CodeQL, no post-install scripts where avoidable |
| Credentials | Tokens in logs or containers | No credentials in containers by design; secret scanning in CI and pre-commit |

## Reporting a vulnerability

**Do not open a public issue for a security problem.**

- Use GitHub's private reporting: **Security → Report a vulnerability** on
  <https://github.com/JoeyHammoth/bendEDA>. This creates a private advisory
  visible only to maintainers.
- If you cannot use that flow, contact the maintainer listed in
  [GOVERNANCE.md](GOVERNANCE.md) and say only that you have a security report;
  do not include the details in a first message on a public channel.

Please include: affected component and version/commit, reproduction steps, the
impact you believe it has, and whether the issue is already public anywhere.

### What to expect

| Stage | Target |
|---|---|
| Acknowledgement | 3 working days |
| Initial assessment (severity, affected versions) | 10 working days |
| Fix or documented mitigation | 90 days for non-critical; faster for sandbox escapes |
| Public disclosure | Coordinated, after a fix or after 90 days, whichever comes first |

We will credit reporters in the advisory unless asked not to.

## In scope

- Sandbox escape from an agent run to the host or the scoring host.
- Reading the sealed oracle, or any path outside the run workspace.
- Writing to a protected path despite the policy proxy, or a proxy bypass.
- Hash-manifest collision or a lock that can be defeated without changing hashes.
- Credential or token leakage in logs, artifacts or the repository history.
- A dependency vulnerability reachable from harness code.

## Out of scope

- A model producing wrong, insecure or non-synthesizable RTL. That is the
  research subject, not a vulnerability — it is measured, not fixed.
- A proof accepted that you believe is false: report it as a **correctness**
  issue with `type: bug` and the counterexample. These are important and get
  priority, but they are part of the science.
- Denial of service against your own machine by running the full matrix.
- Findings that require an already-compromised host.

## Hardening notes for users

- Run the harness only inside the provided container definitions; do not point it
  at a machine holding credentials you care about.
- Treat every artifact produced by an agent run as untrusted input.
- The repository publishes no prebuilt images with vendor or GPL toolchains
  without their notices; build from `docker/` if you need a pinned environment.
