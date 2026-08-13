# mos-templates — Claude working instructions

This file tells Claude (via Claude Code) how to build new MOS Hub templates for
this repo consistently, safely, and without repeating past mistakes.

**Before doing anything else in this repo, read `mistakes.md` in full.**
It contains lessons from past PRs/builds that failed or were misunderstood.
Do not repeat an entry from that log.

---

## 1. What you're building

Given a **GitHub repo URL** or a **Docker image reference**, produce a template
that matches the existing style in this repo exactly. There are two shapes:

- **Single container** → `docker/<slug>.json`
- **Multi-container stack** (needs a database, sidecar, etc.) → a new folder
  under `compose/<slug>/` containing `template.json`, `compose.yaml`, `.env`

Never guess which shape to use — inspect the upstream project's own
docker-compose/install docs. If it needs more than one container to run
correctly, it's a compose stack, not a single `docker/*.json`.

## 2. `docker/*.json` schema (single container)

Confirmed from existing files (`ntfy.json`, `filebrowser-quantum.json`, etc).
Field names are **snake_case**, not camelCase — this repo does not use
`camelCase` keys or `[[VARIABLE]]` placeholder syntax anywhere today. If that's
wanted going forward, that's a deliberate schema change to propose separately —
don't silently introduce it in one template.

```jsonc
{
  "name": "Human Readable Name",           // Title Case
  "repo": "namespace/image:tag",           // prefer a real pinned tag over :latest when upstream publishes one
  "network": "bridge",
  "custom_ip": null,
  "default_shell": "sh",                   // "sh" unless the image is known to need bash
  "privileged": false,                      // only true if upstream docs require it — flag this loudly if so
  "extra_parameters": "--restart=unless-stopped",
  "post_parameters": null,                  // args appended after the image, e.g. "serve"
  "web_ui_url": "http://[IP]:[PORT:80]",    // omit key entirely if the app has no web UI
  "icon": "https://...png",                 // prefer cdn.jsdelivr.net/gh/selfhst/icons or homarr-labs/dashboard-icons; fall back to the project's own repo asset
  "category": ["Utilities"],                // ALWAYS an array, even for one value. Reuse an existing category — see list below. Never invent a new one without asking.
  "project": "https://github.com/...",      // upstream source
  "support": "https://github.com/.../issues",
  "donate": null,
  "description": "1-2 plain sentences, no marketing fluff, no emoji.",
  "readme_url": "https://github.com/.../README.md",
  "paths": [
    {
      "name": "Config",
      "host": "/mnt/cache/appdata/<slug>",
      "container": "/config",
      "mode": "rw",
      "description": "Config directory",
      "required": true
    }
  ],
  "ports": [
    {
      "name": "WebUI Port",
      "host": "80",
      "container": "80",
      "protocol": "tcp",
      "description": "Web interface",
      "required": false,
      "mask": false
    }
  ],
  "variables": [
    {
      "name": "TZ",
      "key": "TZ",
      "value": "Etc/UTC",
      "description": "Timezone",
      "required": true,
      "mask": false
    }
  ],
  "devices": [],
  "labels": []
}
```

**Existing category vocabulary (reuse, don't fork new spellings):**
`Utilities`, `Security`, `Network`, `Media`, `Monitoring`, `Storage`,
`Backup`, `Archiving`, `Productivity`, `Home Automation`.

Two existing files in this repo violate the schema (`archivebox.json` has
`category` as a bare string, `timemachine.json` has `category: null`) —
**do not copy that pattern.** These are candidates for a cleanup PR, not
examples to follow.

## 3. `compose/<slug>/` schema (multi-container stack)

`template.json` here is deliberately lighter than the single-container schema:

```jsonc
{
  "name": "Human Readable Name",
  "category": ["Utilities"],
  "description": "1-2 plain sentences.",
  "icon": "https://...png",
  "webui": "http://{IP}:8888",     // note: {IP} here, not [IP] — this file uses a different placeholder style than docker/*.json. Match whichever folder you're in.
  "website": "https://upstream-project-site"
}
```

`compose.yaml` is a normal Compose file:
- Pin a real version tag in a comment where the exact latest tag can't be
  known ahead of time (see `atuin/compose.yaml`: `<LATEST TAGGED RELEASE>`),
  never leave a bare `:latest` with no note.
- Secrets/passwords go in `.env`, referenced as `${VAR_NAME}` — never
  hardcoded into `compose.yaml`.
- `.env` ships with **placeholder, non-functional example values** only
  (e.g. `really-insecure`), with a comment telling the user to change it.
  Never commit a real secret, even a throwaway one.

## 4. Build process for a new template

1. Fetch the upstream repo/image: README, `docker-compose.yml` if published,
   Docker Hub / GHCR tags page, exposed ports, declared volumes.
2. Verify the source is trustworthy before templating it (see §5).
3. Draft the JSON against the schema above.
4. Validate: valid JSON, `category` is an array using an existing value,
   no null where an array/string is expected, host paths follow the
   `/mnt/cache/appdata/<slug>` convention, no real secrets anywhere.
5. Diff against 2-3 similar existing templates for field-shape consistency
   before opening a PR.
6. If anything about the upstream project is ambiguous or you had to guess,
   say so in the PR description — don't silently guess and move on.

## 5. Security practices (non-negotiable)

- **Never embed a real credential, token, or password** in any template,
  `.env`, or compose file — placeholders only, clearly marked as such.
- **Check image provenance** before templating an unfamiliar image: is it an
  official image, a verified publisher, or a well-known maintainer (e.g.
  linuxserver.io, official project GHCR)? Note this in the PR description.
  Flag (don't silently accept) images from an unknown single-user namespace
  with no stars/activity.
- **Don't set `"privileged": true`** or add host device passthrough unless
  the upstream project's own docs explicitly require it — and call that out
  in the PR description so a human notices.
- **Never widen scope beyond the template files.** Don't touch CI config,
  `maintainer.json`, or unrelated templates in the same PR.
- **Never run arbitrary scripts pulled from the target repo.** Read its
  Dockerfile/compose/README as text to extract config; don't execute it.

## 6. Git / PR workflow

- Work on a new branch per template: `add/<slug>` or `fix/<slug>`.
- **Never push to `main` directly.** Always open a PR via `gh pr create`.
- **Never merge your own PR.** Merging is a human decision — this repo's
  automation stops at "PR opened," full stop.
- One template (or one clearly related fix) per PR.
- PR description must state: what the template is, source/image reference,
  category chosen, any assumptions made, and anything flagged under §5.
- Use a GitHub token scoped as narrowly as possible: fine-grained PAT,
  this repo only, `Contents: write` + `Pull requests: write`, no `Actions`,
  no org-wide access, no admin. Rotate/revoke it if it's ever pasted into a
  chat log instead of an env var.

## 7. When something goes wrong

If a PR is rejected, CI fails, a template turns out wrong after merge, or you
misunderstood something Kristian asked for — **log it in `mistakes.md`**
using the format defined at the top of that file, before doing anything else.
This is not optional cleanup, it's part of finishing the task.
