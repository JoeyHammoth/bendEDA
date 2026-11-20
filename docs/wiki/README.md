# Wiki source

The GitHub wiki is the project's living log: the phase plan, the decision history,
and the answers to objections we keep hearing. Its source lives here so that a
decision can be reviewed like code, and so a wiki outage does not lose the history.

**Read it rendered:** <https://github.com/JoeyHammoth/bendEDA/wiki>

## Files

| File | Page |
|---|---|
| `Home.md` | landing page |
| `Phase-0-Plan.md` | what has to be true before the first task is authored |
| `Decision-Log.md` | dated decisions, including reversals |
| `Agent-Roles.md` | who authors what when no human writes the laws |
| `Metrics-Cheat-Sheet.md` | endpoints, formulas, and the trap in each |
| `Running-the-CLI.md` | install, verify, exit codes |
| `Contamination-Controls.md` | sealed oracle and public-repository hygiene |
| `Repository-Map.md` | where a thing lives and why |
| `FAQ.md` | recurring objections, answered by the protocol |
| `_Sidebar.md`, `_Footer.md` | wiki chrome |

## Editing rules

1. **Write history, not the present.** Date claims and cite the commit or tag they
   were true at. "Currently" ages badly; "as of `abc1234`" does not.
2. **Do not duplicate the protocol.** Link to the design document. If a wiki page
   and the document disagree, the document wins and the page is a bug.
3. **Record reversals.** A decision that changed keeps its old entry with a
   superseded marker. A log that only shows the final answer is not a log.
4. **No oracle content, no credentials, no unreviewed result numbers.**

## Syncing to GitHub

```bash
git clone https://github.com/JoeyHammoth/bendEDA.wiki.git /tmp/bendeda-wiki
cp docs/wiki/*.md /tmp/bendeda-wiki/
cd /tmp/bendeda-wiki && git add -A && git commit -s -m "wiki: sync from docs/wiki" && git push
```

The first page must exist before the wiki repository can be cloned; if the clone
fails with "repository not found", create any page once in the GitHub UI and the
repository appears. Everything after that is a normal push.
