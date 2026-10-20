# Checking a transcript

Every transcript in `batches/<id>/open/` was signed by GitHub when its batch finished. Here's how to check one.

## With the GitHub CLI (one command)

Install [`gh`](https://cli.github.com), sign in (`gh auth login`), download the transcript's `.json` file, then run:

```
gh attestation verify b0007-r03.json -R raulstern/ai-talks
```

It succeeds only if the file is byte-for-byte what this repo's workflow produced. Change one character and it fails. The output names the workflow and the commit it ran from, so you can read the exact code and prompts that made it.

## Without installing anything

1. Get the file's SHA-256: `shasum -a 256 b0007-r03.json` (Mac) or `sha256sum b0007-r03.json` (Linux), or any online SHA-256 tool.
2. Check it's listed in that batch's `batch.json`, next to its run number.
3. Open the batch's `ATTESTATION` link (or this repo's Actions → Attestations page): the signed subjects include that same fingerprint.

## What else to check

- **Nothing was dropped:** `batch.json` lists every run in the batch. Once a batch is open, every run listed is in `open/`, and each one verifies.
- **Nothing was injected:** the instructions each model got are in the transcript (`systems`) and in `runner/talk.py` at the signed commit. The seed comes from `runner/seeds.json` at that commit.
- **The right models:** the model names and `api.anthropic.com` are fixed in `runner/talk.py`. Each turn also records the model the API says served it (`served_by`) and Anthropic's message id.
