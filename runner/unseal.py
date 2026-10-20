#!/usr/bin/env python3
"""Open a sealed batch: decrypt every transcript, check each one against the
SHA-256 in the batch manifest, and write it to batches/<id>/open/ as JSON plus
a readable Markdown copy. Needs the private seal key, so only the show can run
it. Anyone can then check the opened files (VERIFY.md).

  python3 runner/unseal.py b0007 --key /path/to/seal.key
"""
import argparse
import hashlib
import json
from pathlib import Path

import pyrage

REPO = Path(__file__).resolve().parent.parent
NAME = {"claude-fable-5-1": "Fable", "claude-opus-5-5": "Opus", "claude-sonnet-5-5": "Sonnet"}


def markdown(rec):
    names = {t["speaker"]: NAME.get(t["model"], t["model"]) for t in rec["turns"]}
    if len(set(names.values())) == 1:
        names = {k: f"{v} {'AB'[k]}" for k, v in names.items()}
    out = [f"# {rec['id']}: run {rec['run']} of {rec['of']} in batch {rec['batch']}", "",
           f"**Seed:** {rec['seed_text'] or '(none)'}", "",
           f"**Pair:** {rec['pair']} · **Format:** {rec['format']} · **Status:** {rec['status']} · "
           f"**Started:** {rec['started']} · **Finished:** {rec['finished']}", "",
           "The full instructions each model got are in the JSON file (`systems`). "
           "Replies are shown after the runner's light cleanup (markdown symbols and speaker labels removed); "
           "a reply's exact original is kept as `raw` whenever cleanup changed it.", "", "## Transcript", ""]
    for i, t in enumerate(rec["turns"]):
        cut = " *[cut off: the reply hit the length limit]*" if t.get("cut") else ""
        out.append(f"**[{i + 1}] {names[t['speaker']]}:** {t['text']}{cut}")
        out.append("")
    if rec.get("error"):
        out += [f"**Stopped early:** {rec['error']}", ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batch")
    ap.add_argument("--key", required=True)
    ap.add_argument("--repo", default=str(REPO))
    a = ap.parse_args()
    bdir = Path(a.repo) / "batches" / a.batch
    manifest = json.loads((bdir / "batch.json").read_text())
    ident = [l for l in Path(a.key).read_text().splitlines() if l.startswith("AGE-SECRET-KEY-")][0]
    ident = pyrage.x25519.Identity.from_str(ident)
    (bdir / "open").mkdir(exist_ok=True)
    for r in manifest["runs"]:
        raw = pyrage.decrypt((bdir / "sealed" / f"{r['file']}.age").read_bytes(), [ident])
        if hashlib.sha256(raw).hexdigest() != r["sha256"]:
            raise SystemExit(f"{r['file']}: does not match the manifest")
        (bdir / "open" / r["file"]).write_bytes(raw)
        (bdir / "open" / r["file"].replace(".json", ".md")).write_text(markdown(json.loads(raw)) + "\n")
    print(f"{a.batch}: opened {len(manifest['runs'])} transcripts, all match the manifest")


if __name__ == "__main__":
    main()
