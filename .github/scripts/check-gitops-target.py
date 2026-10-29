"""
Fail if any Argo CD Application under gitops/apps/ that points at this
repository tracks anything other than `main`.

During development the apps can point at a feature branch so Argo CD syncs
work in progress; this check makes sure that setting can't be merged.

    python check-gitops-target.py [gitops/apps]
"""
import sys
from pathlib import Path

import yaml

REPO = "github.com/shayur-p60/django-task-manager"
REQUIRED = "main"


def sources(app):
    spec = app.get("spec", {})
    if "source" in spec:
        yield spec["source"]
    yield from spec.get("sources", [])


def main(root):
    problems, checked = [], 0
    files = sorted(Path(root).rglob("*.y*ml"))
    for path in files:
        for doc in yaml.safe_load_all(path.read_text()):
            if not doc or doc.get("kind") != "Application":
                continue
            name = doc.get("metadata", {}).get("name", "?")
            for src in sources(doc):
                url = src.get("repoURL", "").lower().removesuffix(".git").removesuffix("/")
                if not url.endswith(REPO):
                    continue
                checked += 1
                rev = src.get("targetRevision", "HEAD")
                if rev != REQUIRED:
                    problems.append(f"{path}: Application {name!r} tracks {rev!r}, must be {REQUIRED!r}")
    for p in problems:
        print(f"::error file={p.split(':')[0]}::{p}")
    print(f"Checked {checked} source(s) in {len(files)} file(s): {len(problems)} problem(s).")
    if checked == 0:
        print(f"::error::No Application sources for {REPO} found under {root}")
        return 1
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "gitops/apps"))
