# mistakes.md

A running log of mistakes made while building/PR'ing templates for this repo —
schema errors, failed PRs, misread requirements, bad assumptions about an
upstream project, anything Kristian had to correct. Read this file in full
before starting new work. Add a new entry any time a PR fails, gets rejected,
or turns out to have been based on a misunderstanding.

## Entry format

```markdown
### YYYY-MM-DD — <slug or template name>

- **Trigger:** PR rejected / CI failed / merged-but-wrong / misunderstood request
- **What happened:** one or two sentences, factual, no editorializing
- **Root cause:** why it happened — bad assumption, missed doc, wrong field, etc.
- **Fix applied:** what was changed to correct it
- **Rule going forward:** one concrete, checkable rule to add to CLAUDE.md
  (or a pointer to the CLAUDE.md section it was added to)
```

Keep entries short and specific. The goal is a checklist that prevents repeat
mistakes, not a diary.

---

### Example (seed entry, not a real incident — delete once you have real ones)

### 2026-08-13 — repo audit

- **Trigger:** schema audit while setting up this workflow
- **What happened:** `docker/archivebox.json` has `"category": "Archiving"`
  (a bare string) instead of an array; `docker/timemachine.json` has
  `"category": null`. Both violate the documented schema.
- **Root cause:** no schema validation existed before templates were
  committed, so a malformed field went unnoticed.
- **Fix applied:** flagged in CLAUDE.md §2 as a known bad pattern, not to be
  copied. Not yet fixed upstream — candidate for a small cleanup PR.
- **Rule going forward:** validate `category` is always a non-empty array of
  strings before opening any PR that touches a `docker/*.json` file.

### 2026-08-13 — chore/claude-pr-badges

- **Trigger:** misunderstood request — pushed into a policy conflict mid-task
- **What happened:** built a GitHub Actions workflow
  (`.github/workflows/label-claude-prs.yml`) to auto-label Claude-authored
  PRs. The push was rejected: the repo's scoped PAT lacks the `workflow`
  scope needed to create/modify files under `.github/workflows/`, which is
  exactly what CLAUDE.md §6 says the token should never have ("no Actions").
  The task only landed because the token's scope was widened to push it.
- **Root cause:** didn't cross-check the task against §6's token-scope rule
  before starting; the conflict only surfaced at push time instead of being
  flagged up front.
- **Fix applied:** flagged the conflict to Kristian in the PR description
  instead of silently working around it; he chose to widen the token scope
  himself to unblock the push.
- **Rule going forward:** before starting any task that adds or edits a
  `.github/workflows/*` file, check the automation token's actual scope
  first and flag a §6 conflict *before* attempting the push, not after.
