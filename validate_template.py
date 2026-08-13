#!/usr/bin/env python3
"""
validate_template.py — schema + safety validator for kaywoz/mos-templates

Usage:
    python3 validate_template.py docker/newthing.json
    python3 validate_template.py compose/newthing/
    python3 validate_template.py docker/            # validate every file in a dir
    python3 validate_template.py --all              # validate whole repo (run from repo root)

Exit code 0 = no errors (warnings still possible, printed but non-fatal).
Exit code 1 = at least one error found in at least one file.

This is intentionally conservative: it flags things a human should look at
rather than trying to be a perfect linter. New categories, unusual fields,
and borderline "secret-looking" strings are WARNINGS, not errors — a human
makes the call. Only structural schema breaks and clearly-real-looking
credentials are ERRORS that should block a PR.
"""

import json
import re
import sys
from pathlib import Path

KNOWN_CATEGORIES = {
    "Utilities", "Security", "Network", "Media", "Monitoring",
    "Storage", "Backup", "Archiving", "Productivity", "Home Automation",
}

REQUIRED_DOCKER_KEYS = {
    "name", "repo", "network", "custom_ip", "default_shell", "privileged",
    "extra_parameters", "web_ui_url", "icon", "category", "project",
    "support", "description",
}

REQUIRED_COMPOSE_TEMPLATE_KEYS = {
    "name", "category", "description", "icon", "webui", "website",
}

ARRAY_OF_OBJECTS_FIELDS = ["paths", "ports", "variables", "devices", "labels", "command"]

PATH_ITEM_REQUIRED = {"name", "host", "container", "mode", "description", "required"}
PORT_ITEM_REQUIRED = {"name", "host", "container", "protocol", "description", "required", "mask"}
VAR_ITEM_REQUIRED = {"name", "key", "value", "description", "required", "mask"}

# Heuristics for things that look like real leaked credentials, vs. obvious
# placeholder text like SECRET_PASSWORD, CHANGE_ME, your-token-here, etc.
PLACEHOLDER_HINTS = re.compile(
    r"(changeme|change_me|your[-_]|example|placeholder|insecure|secret_password|"
    r"secret_token|username|password123|<.*>|\[.*\]|\{.*\})",
    re.IGNORECASE,
)
HIGH_ENTROPY_SECRET = re.compile(
    r"""
    (AKIA[0-9A-Z]{16})|                      # AWS access key
    (gh[pousr]_[A-Za-z0-9]{20,})|            # GitHub token
    (sk-[A-Za-z0-9]{20,})|                   # generic "sk-" style API key
    (xox[baprs]-[A-Za-z0-9-]{10,})|          # Slack token
    ([A-Za-z0-9+/]{32,}={0,2})               # long base64-ish blob
    """,
    re.VERBOSE,
)


class Result:
    def __init__(self, path):
        self.path = path
        self.errors = []
        self.warnings = []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    @property
    def ok(self):
        return not self.errors


def scan_for_secrets(obj, path_prefix, result):
    """Recursively scan string values for things that look like real secrets."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            scan_for_secrets(v, f"{path_prefix}.{k}", result)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            scan_for_secrets(v, f"{path_prefix}[{i}]", result)
    elif isinstance(obj, str):
        looks_like_url_or_path = obj.startswith(("http://", "https://", "/"))
        if (
            not looks_like_url_or_path
            and HIGH_ENTROPY_SECRET.search(obj)
            and not PLACEHOLDER_HINTS.search(obj)
        ):
            result.error(
                f"{path_prefix}: value looks like a real credential/token, not a "
                f"placeholder — remove it before opening a PR: {obj[:12]}..."
            )
        elif re.search(r"(password|token|secret|api[_-]?key)", k_or_empty(path_prefix), re.IGNORECASE):
            if not PLACEHOLDER_HINTS.search(obj) and len(obj) > 6:
                result.warn(
                    f"{path_prefix}: field name suggests a secret — double-check "
                    f"'{obj[:20]}' is actually just a placeholder."
                )


def k_or_empty(path_prefix):
    # last path segment, stripped of array indices, for keyword matching
    return re.sub(r"\[\d+\]", "", path_prefix.rsplit(".", 1)[-1])


def validate_array_of_objects(data, field, required_keys, result):
    if field not in data:
        return
    val = data[field]
    if not isinstance(val, list):
        result.error(f"'{field}' must be an array (got {type(val).__name__})")
        return
    for i, item in enumerate(val):
        if not isinstance(item, dict):
            result.error(f"'{field}[{i}]' must be an object")
            continue
        missing = required_keys - item.keys()
        if missing and required_keys:
            result.warn(f"'{field}[{i}]' missing expected keys: {sorted(missing)}")


def validate_docker_template(data, result):
    missing = REQUIRED_DOCKER_KEYS - data.keys()
    if missing:
        result.error(f"missing required top-level keys: {sorted(missing)}")

    cat = data.get("category")
    if cat is None:
        result.error("'category' is null — must be a non-empty array of strings")
    elif isinstance(cat, str):
        result.error(
            f"'category' is a bare string ({cat!r}) — must be an array, e.g. [{cat!r}]"
        )
    elif isinstance(cat, list):
        if not cat:
            result.error("'category' is an empty array — must contain at least one value")
        else:
            for c in cat:
                if not isinstance(c, str):
                    result.error(f"'category' contains a non-string value: {c!r}")
                elif c not in KNOWN_CATEGORIES:
                    result.warn(
                        f"'category' value {c!r} is not in the existing vocabulary "
                        f"({sorted(KNOWN_CATEGORIES)}) — confirm this is intentional, "
                        f"not a typo of an existing category."
                    )
    else:
        result.error(f"'category' must be an array, got {type(cat).__name__}")

    if not isinstance(data.get("name"), str) or not data.get("name", "").strip():
        result.error("'name' must be a non-empty string")

    repo = data.get("repo")
    if not isinstance(repo, str) or "/" not in repo:
        result.error("'repo' should look like 'namespace/image[:tag]' or a registry-qualified path")
    elif repo.endswith(":latest"):
        result.warn("'repo' is pinned to ':latest' — prefer a real version tag if upstream publishes one")

    if not isinstance(data.get("privileged"), bool):
        result.error("'privileged' must be a boolean")
    elif data["privileged"] is True:
        result.warn("'privileged' is true — confirm upstream docs actually require this and call it out in the PR")

    icon = data.get("icon")
    if isinstance(icon, str) and not icon.startswith("https://"):
        result.warn("'icon' is not an https:// URL")

    wu = data.get("web_ui_url")
    if wu is not None and not isinstance(wu, str):
        result.error("'web_ui_url' must be a string or null")

    for field, req_keys in [
        ("paths", PATH_ITEM_REQUIRED),
        ("ports", PORT_ITEM_REQUIRED),
        ("variables", VAR_ITEM_REQUIRED),
    ]:
        validate_array_of_objects(data, field, req_keys, result)

    for field in ["devices", "labels"]:
        if field in data and not isinstance(data[field], list):
            result.error(f"'{field}' must be an array")

    # host paths should follow the repo's own convention, soft check only
    for i, p in enumerate(data.get("paths", []) or []):
        host = p.get("host", "") if isinstance(p, dict) else ""
        if isinstance(host, str) and host and not host.startswith("/mnt/"):
            result.warn(f"paths[{i}].host {host!r} doesn't follow the '/mnt/...' convention used elsewhere")


def validate_compose_template_json(data, result):
    missing = REQUIRED_COMPOSE_TEMPLATE_KEYS - data.keys()
    if missing:
        result.error(f"missing required top-level keys: {sorted(missing)}")

    cat = data.get("category")
    if not isinstance(cat, list) or not cat:
        result.error("'category' must be a non-empty array of strings")
    else:
        for c in cat:
            if isinstance(c, str) and c not in KNOWN_CATEGORIES:
                result.warn(f"'category' value {c!r} is not in the existing vocabulary")


def validate_compose_yaml_text(text, result, env_keys):
    # crude but useful: flag hardcoded secrets not routed through ${VAR}
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_]+):\s*[\"']?(.+?)[\"']?\s*$", stripped)
        if m:
            key, val = m.group(1), m.group(2)
            if re.search(r"(PASSWORD|SECRET|TOKEN|API_KEY)$", key, re.IGNORECASE):
                if "${" not in val and not PLACEHOLDER_HINTS.search(val):
                    result.error(
                        f"compose.yaml:{lineno}: '{key}' looks hardcoded rather than "
                        f"pulled from .env via \\${{{key}}} — move it to .env"
                    )
        if HIGH_ENTROPY_SECRET.search(stripped) and not PLACEHOLDER_HINTS.search(stripped):
            result.error(f"compose.yaml:{lineno}: value looks like a real credential")

    if "<LATEST TAGGED RELEASE>" not in text and re.search(r"image:\s*\S+:latest", text):
        result.warn("compose.yaml pins ':latest' with no pinned-version note — see atuin/compose.yaml for the convention")


def validate_env_text(text, result):
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        if HIGH_ENTROPY_SECRET.search(val) and not PLACEHOLDER_HINTS.search(val):
            result.error(f".env:{lineno}: '{key}' value looks like a real, non-placeholder credential")


def validate_docker_json_file(path: Path):
    result = Result(path)
    try:
        text = path.read_text()
        data = json.loads(text)
    except json.JSONDecodeError as e:
        result.error(f"invalid JSON: {e}")
        return result
    validate_docker_template(data, result)
    scan_for_secrets(data, path.name, result)
    return result


def validate_compose_dir(path: Path):
    result = Result(path)
    tj = path / "template.json"
    cy = path / "compose.yaml"
    env = path / ".env"

    if not tj.exists():
        result.error("missing template.json")
    else:
        try:
            data = json.loads(tj.read_text())
            validate_compose_template_json(data, result)
            scan_for_secrets(data, "template.json", result)
        except json.JSONDecodeError as e:
            result.error(f"template.json: invalid JSON: {e}")

    if not cy.exists():
        result.error("missing compose.yaml")
    else:
        validate_compose_yaml_text(cy.read_text(), result, env_keys=None)

    if env.exists():
        validate_env_text(env.read_text(), result)
    else:
        result.warn("no .env file — fine if the stack truly needs no config, otherwise expected")

    return result


def collect_targets(args):
    targets = []
    if "--all" in args:
        root = Path(".")
        targets += sorted((root / "docker").glob("*.json"))
        if (root / "compose").exists():
            targets += sorted(p for p in (root / "compose").iterdir() if p.is_dir())
        return targets

    for a in args:
        p = Path(a)
        if p.is_dir():
            if (p / "template.json").exists() or p.name != "docker":
                # looks like a compose stack dir, or a plain dir of docker jsons
                if (p / "template.json").exists():
                    targets.append(p)
                else:
                    targets += sorted(p.glob("*.json"))
            else:
                targets += sorted(p.glob("*.json"))
        elif p.suffix == ".json":
            targets.append(p)
        else:
            print(f"Skipping unrecognized target: {p}", file=sys.stderr)
    return targets


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    targets = collect_targets(args)
    if not targets:
        print("No targets found to validate.")
        sys.exit(1)

    any_errors = False
    for t in targets:
        if t.is_dir():
            result = validate_compose_dir(t)
        elif t.name == "dillinger.json.bak" or t.suffix != ".json":
            continue
        else:
            result = validate_docker_json_file(t)

        status = "OK" if result.ok else "FAIL"
        print(f"\n[{status}] {t}")
        for e in result.errors:
            print(f"  ERROR:   {e}")
        for w in result.warnings:
            print(f"  WARNING: {w}")
        if not result.errors and not result.warnings:
            print("  (clean)")
        if not result.ok:
            any_errors = True

    print()
    sys.exit(1 if any_errors else 0)


if __name__ == "__main__":
    main()
