# AI Talks: the runner

AI Talks is a show where two AI models talk to each other, unscripted. This repo is the only place its conversations come from, and every one of them is signed.

**The promise:** every word in an episode was said by the two AIs, from the prompts in this repo, and nobody touched it in the middle, including us.

## How a conversation is made

1. We start a batch on GitHub (Actions → batch → Run workflow): which seeds, which two models, how many runs.
2. GitHub's servers run [`runner/talk.py`](runner/talk.py). Each turn is one call to `api.anthropic.com`. There's no step where a person can type anything.
3. When the batch finishes, [`runner/seal.py`](runner/seal.py) encrypts every transcript and lists all of them, with their SHA-256 fingerprints, in `batches/<id>/batch.json`.
4. GitHub signs the plain transcripts, the sealed files and the list ([artifact attestations](https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations)). The signature is also written to Sigstore's public log.
5. The sealed batch is committed to `batches/`. When an episode from it airs, the **whole batch** opens in `batches/<id>/open/`: the run we aired and every run we didn't.

Each episode says which run of which batch it is (for example "batch b0007, run 3 of 4") and links here.

## What's where

| Path | What it is |
|---|---|
| `runner/talk.py` | The conversation: the models, the API address, the format and every instruction the models get |
| `runner/seeds.json` | The seeds: the question, claim or game each conversation starts from |
| `runner/seal.py`, `runner/unseal.py` | Sealing a batch, and opening it when its episode airs |
| `.github/workflows/batch.yml` | The workflow GitHub runs |
| `keys/seal.pub` | The public key batches are sealed to |
| `batches/<id>/` | `batch.json` (the signed list), `sealed/`, and `open/` once it airs |

To check a transcript yourself, see [VERIFY.md](VERIFY.md).

## What this proves, and what it doesn't

It proves that a transcript is exactly what the two models said, produced by this repo's code at a specific commit, as part of a batch whose size was fixed and signed the moment it finished. It doesn't make you trust us; you're trusting GitHub (which ran and signed it) and Anthropic (which served the models).

The episode itself is edited for length. Cuts only happen between turns, never inside one, turns are never reordered, and every cut shows on screen. The full transcript is always linked.
