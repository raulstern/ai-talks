#!/usr/bin/env python3
"""Seal a finished batch and write its manifest.

Each conversation is encrypted to the public key in keys/seal.pub, so it can be
committed to this public repo now and read only when its batch is opened
(runner/unseal.py, when the episode airs). The manifest, batches/<id>/batch.json,
lists every run in the batch with the SHA-256 of its plain transcript. The
workflow then signs the plain transcripts, the sealed files and the manifest,
so no run can be added, dropped or changed later.

  python3 runner/seal.py --batch b0007 --src OUT --dest batches/b0007
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path

import pyrage

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--dest", required=True)
    ap.add_argument("--workflow-run", default=os.environ.get("WORKFLOW_RUN_URL"))
    a = ap.parse_args()

    recipient_str = (REPO / "keys" / "seal.pub").read_text().strip()
    recipient = pyrage.x25519.Recipient.from_str(recipient_str)
    src, dest = Path(a.src), Path(a.dest)
    if dest.exists():
        raise SystemExit(f"{dest} already exists: a batch is never rewritten")
    (dest / "sealed").mkdir(parents=True)

    runs, recs = [], []
    for p in sorted(src.glob(f"{a.batch}-r*.json")):
        raw = p.read_bytes()
        rec = json.loads(raw)
        sealed = pyrage.encrypt(raw, [recipient])
        (dest / "sealed" / f"{p.name}.age").write_bytes(sealed)
        recs.append(rec)
        runs.append({
            "run": rec["run"], "file": p.name, "seed": rec["seed"], "status": rec["status"],
            "turns": len(rec.get("turns", [])), "cost_usd": rec.get("cost_usd"),
            "sha256": sha256(raw), "sealed_sha256": sha256(sealed),
        })
    if not runs:
        raise SystemExit("no transcripts found")
    first = recs[0]
    manifest = {
        "batch": a.batch,
        "sealed": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "workflow_run": a.workflow_run,
        "runner_commit": os.environ.get("GITHUB_SHA"),
        "pair": first["pair"], "models": first["cfg"]["pair"], "format": first["format"],
        "settings": {k: v for k, v in first["cfg"].items() if k not in ("pair", "seed")},
        "seeds": sorted({r["seed"] for r in recs}),
        "api": first["api"],
        "mock": any(r.get("mock") for r in recs),
        "count": len(runs),
        "finished": sum(r["status"] == "done" for r in runs),
        "cost_usd": round(sum(r["cost_usd"] or 0 for r in runs), 2),
        "sealed_to": recipient_str,
        "runs": runs,
    }
    (dest / "batch.json").write_text(json.dumps(manifest, indent=1) + "\n")

    when = manifest["sealed"][:10]
    lines = [f"# Batch {a.batch}", "",
             f"{manifest['count']} conversations, sealed and signed on {when}. "
             f"Pair: {manifest['pair']}. Format: {manifest['format']}. "
             f"{manifest['finished']} of {manifest['count']} finished.", "",
             "Sealed until an episode from this batch airs; then the whole batch opens in `open/`. "
             "See VERIFY.md at the top of the repo to check any transcript against its signature.", "",
             "| Run | Seed | Status | Turns | SHA-256 of the transcript |", "|---|---|---|---|---|"]
    for r in runs:
        lines.append(f"| {r['run']} | {r['seed']} | {r['status']} | {r['turns']} | `{r['sha256']}` |")
    if manifest["workflow_run"]:
        lines += ["", f"Workflow run: {manifest['workflow_run']}"]
    (dest / "README.md").write_text("\n".join(lines) + "\n")
    print(f"{a.batch}: sealed {len(runs)} transcripts to {recipient_str[:16]}…")


if __name__ == "__main__":
    main()
