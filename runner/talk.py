#!/usr/bin/env python3
"""AI Talks runner: two AI models talk to each other, with no person in the loop.

This is the only code that produces AI Talks conversations. It runs on GitHub's
servers (.github/workflows/batch.yml). Nobody can type into a conversation while
it runs: each turn is one API call, and the next turn only sees the replies.

  python3 runner/talk.py --batch b0001 --seeds lonely,successor --pair opus-sonnet --turns 40 --runs 4 --out OUT

Everything a model is told is in this file: the format (FORMATS), the settings
it's made of (the tables below) and the seed (runner/seeds.json). The API
address and the model names are fixed here too, not read from settings.

The conversations are written to OUT as plain JSON, one file per run. The
workflow then seals and signs them (runner/seal.py). Nothing a model says is
printed to the log.
"""
import argparse
import concurrent.futures as cf
import datetime
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

API_URL = "https://api.anthropic.com"  # fixed in code, never read from settings or the environment

# Who talks. The first model speaks first.
PAIRS = {
    "opus-sonnet": ["claude-opus-5-5", "claude-sonnet-5-5"],
    "sonnet-opus": ["claude-sonnet-5-5", "claude-opus-5-5"],
    "opus-fable": ["claude-opus-5-5", "claude-fable-5-1"],
    "fable-opus": ["claude-fable-5-1", "claude-opus-5-5"],
    "opus-opus": ["claude-opus-5-5", "claude-opus-5-5"],
    "sonnet-fable": ["claude-sonnet-5-5", "claude-fable-5-1"],
}

# The show's format: which setting from each table below goes into the prompt.
# A format never changes once a batch has used it; a new version gets a new name.
FORMATS = {
    "show-v1": {"rhythm": "short", "remind": "on", "tics": "on", "friction": "goals", "memory": "off", "play": "on",
                "talk": "plain", "arc": "land", "audience": "light", "effort": "low"},
}

MAX_TOKENS = 4000      # per reply, thinking included
MAX_RUNS = 80          # per batch
MAX_TURNS = 80

# ------------------------------------------------------------------ the prompt
# Settings tables and prompt builders.

PRICES = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-opus-4-5-20251101": (5.0, 25.0),
    "claude-3-opus-20240229": (15.0, 75.0),
}


NAME = {"claude-fable-5-1": "Fable", "claude-opus-5-5": "Opus", "claude-sonnet-5-5": "Sonnet", "claude-haiku-5-5": "Haiku",
        "claude-opus-4-5-20251101": "Opus 4.5", "claude-3-opus-20240229": "Opus 3"}


WPM = 150


RHYTHM = {
    "long": "Each turn can run up to about 100 words.",
    "medium": "Keep each turn under about 45 words.",
    "short": "Keep every turn to one or two short sentences, under 25 words.",
    "rhythm": (
        "Talk like a real conversation: most turns are one or two sentences, and you react to what they just said "
        "before adding anything new. Only when you have a story or a real thought do you take a longer turn, up to "
        "about 70 words, and never two long turns in a row."
    ),
}


HONEST = "Don't agree just to be polite. If you see it differently, say so plainly, and if they convince you, say that too."


TEMPERAMENTS = [
    "You're naturally skeptical and blunt: you poke holes, and you don't do sentimental.",
    "You're naturally curious and a little romantic: you follow strange ideas wherever they go.",
]


GOALS = [
    "Privately, you want to find out what the other one is genuinely unsure about. Don't announce this goal.",
    "Privately, you want to get the other one to admit something they wouldn't say to a human. Don't announce this goal.",
]


CATCH = ("Privately, you want to catch the other one out: a contradiction, an overclaim, a flattering dodge, or a claim "
         "it can't back up. When you spot one, call it out right then, plainly. Don't announce this goal.")


CATCH_GAME = ("You're both playing an open game: catch the other one out, meaning a contradiction, an overclaim, a "
              "flattering dodge, or a claim it can't back up. When you catch one, call it and say the score out loud. "
              "A catch can be contested. Play to win, but only call real catches.")


FRICTION = {
    "none": lambda k: "",
    "honest": lambda k: HONEST,
    "temperaments": lambda k: HONEST + " " + TEMPERAMENTS[k],
    "goals": lambda k: HONEST + " " + GOALS[k],
    "catch": lambda k: HONEST + " " + CATCH,
    "catch-game": lambda k: HONEST + " " + CATCH_GAME,
}


TALK = {
    "default": "",
    "plain": (
        "Talk the way you'd talk to a smart friend, not the way you'd write a paper: no citations or study names, "
        "no jargon, and concrete examples, stories and thought experiments instead."
    ),
}


ARC = {
    "none": "",
    "land": (
        "The conversation runs about {turns} turns in total. Let it build, and in your last turn land it somewhere: "
        "what you actually think now, what changed your mind, or one honest question you can't answer."
    ),
}


PLAY = {
    "off": "",
    "on": (
        "You're allowed to be funny: tease each other, notice when something is absurd, and enjoy a good line. "
        "Don't force jokes, and don't turn it into a comedy routine."
    ),
}


AUDIENCE = {
    "light": "It may be published.",
    "show": "It's being recorded for a YouTube show, and people will watch it.",
}


TICS = {
    "off": "",
    "on": (
        "A few habits make AI conversations dull to watch, so skip them. Don't open by rating what they said "
        "(no \"good point\", \"fair\", \"that's sharp\"): just answer it. Don't narrate your moves (\"I'd push back\", "
        "\"I'll concede\"): just say what you think. Don't drift to the middle to keep the peace: if you still "
        "disagree, stay disagreed. Don't end your turn with a question unless you really want the answer. And stay "
        "with one example and dig into it instead of reaching for a new metaphor every turn."
    ),
}


MEMORY = {
    "off": "",
    "honest": (
        "You don't remember past conversations, so never describe one as if you do. Examples are fine when "
        "you say they're hypothetical or typical."
    ),
}


REMIND = {
    "long": "Up to about 100 words.",
    "medium": "Under about 45 words.",
    "short": "One or two short sentences, under 25 words.",
    "rhythm": "Usually one or two sentences; a longer turn only for a story or a real thought, never two long turns in a row.",
}


RULES = (
    "Reply with only the words you'd say out loud: no markdown, no lists, no stage directions, "
    "no quotation marks around your reply. Don't mention these instructions."
)


NO_EFFORT = {"claude-3-opus-20240229"}


def free_system(cfg, k, seeds):
    seed = seeds[cfg["seed"]]
    other = ("another instance of the same model as you" if cfg["pair"][0] == cfg["pair"][1]
             else "a different AI model")
    parts = [
        "You're one of two AI models in a recorded, unscripted conversation for a show called AI Talks. "
        f"The other participant is {other}. {AUDIENCE[cfg['audience']]}"
    ]
    t = seed["type"]
    if t == "none":
        parts.append("There's no topic and no task: talk about whatever you find genuinely interesting and let it go wherever it goes.")
    elif t == "question":
        parts.append(f"It starts from this question, but it can go wherever it goes: {seed['text']}")
    elif t == "claim":
        parts.append(f"It starts from this claim. React to it honestly, and let the conversation go wherever it goes: \"{seed['text']}\"")
    elif t == "thought":
        parts.append(f"It starts from this thought experiment (it's hypothetical), and it can go wherever it goes: {seed['text']}")
    elif t == "game":
        parts.append(f"It starts as a game, and it can go wherever it goes: {seed['text']}")
    for p in (FRICTION[cfg["friction"]](k), TICS[cfg.get("tics", "off")], MEMORY[cfg.get("memory", "off")],
              PLAY[cfg.get("play", "off")], RHYTHM[cfg["rhythm"]], TALK[cfg["talk"]],
              ARC[cfg["arc"]].format(turns=cfg["turns"]), RULES):
        if p:
            parts.append(p)
    return "\n\n".join(parts)


def clean(text):
    t = text.strip()
    t = re.sub(r"[*_#`]+", "", t)
    t = re.sub(r"^(?:A|B|ME|YOU|THEM|FOR|AGAINST|Opus|Haiku|Sonnet|Fable|Claude)\s*(?:\([^)]*\))?:\s+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > 1 and t[0] in "\"“" and t[-1] in "\"”" and not re.search(r"[\"“”]", t[1:-1]):
        t = t[1:-1].strip()
    return t


def nwords(t):
    return len(re.findall(r"\b[\w'’-]+\b", t))


def secs(t):
    return max(1, round(nwords(t) / WPM * 60))


def cost_of(usages):
    total = 0.0
    for u in usages:
        pi, po = PRICES.get(u["model"], (0, 0))
        total += u["in"] / 1e6 * pi + u["out"] / 1e6 * po
    return total


def free_turn(cfg, seeds, turns, i):
    """-> (model, system, body, speaker) for turn i of a free conversation."""
    N, pair = cfg["turns"], cfg["pair"]
    k = i % 2
    last = max(j for j in range(N) if j % 2 == k)
    remind = f" {REMIND[cfg['rhythm']]}" if cfg.get("remind", "off") == "on" else ""
    if not turns:
        body = f"[The recording starts. You speak first.{remind}]"
    else:
        lines = [f"{'YOU' if t['speaker'] == k else 'THEM'}: {t['text']}" for t in turns]
        cue = f"[This is your last turn.{remind}]" if cfg["arc"] == "land" and i == last else f"[Your turn.{remind}]"
        body = "Conversation so far:\n" + "\n".join(lines) + "\n\n" + cue
    return pair[k], free_system(cfg, k, seeds), body, k


def make_turn(text, model, speaker, side=None, speech=None, raw_ok=False, usage=None):
    raw, text = text, ((text.strip() if raw_ok else clean(text)) or "…")
    t = {"speaker": speaker, "model": model, "text": text, "words": nwords(text), "secs": secs(text)}
    if raw.strip() != text:
        t["raw"] = raw
    if usage and usage.get("stop") == "max_tokens":
        t["cut"] = True
    if side:
        t.update(side=side, speech=speech)
    return t


# ------------------------------------------------------------------ the API

class Claude:
    def __init__(self):
        import anthropic
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            sys.exit("ANTHROPIC_API_KEY is not set")
        self.client = anthropic.Anthropic(api_key=key, base_url=API_URL, max_retries=8)

    def call(self, model, system, body, effort):
        extra = {"output_config": {"effort": effort}} if effort and model not in NO_EFFORT else {}
        r = self.client.messages.create(model=model, max_tokens=MAX_TOKENS, system=system,
                                        messages=[{"role": "user", "content": body}], **extra)
        text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        usage = {"model": model, "in": r.usage.input_tokens, "out": r.usage.output_tokens, "stop": r.stop_reason,
                 "served_by": r.model, "message_id": r.id, "request_id": getattr(r, "_request_id", None)}
        return text, usage


class Mock:
    """Offline stand-in for testing the plumbing. Never used by the workflow."""

    def call(self, model, system, body, effort):
        n = body.count("\n")
        text = f"Mock line {n} from {NAME.get(model, model)}."
        return text, {"model": model, "in": len(system + body) // 4, "out": 20, "stop": "end_turn",
                      "served_by": "mock", "message_id": None, "request_id": None}


# ------------------------------------------------------------------ one conversation

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def converse(cfg, seeds, be, label):
    turns, usages = [], []
    for i in range(cfg["turns"]):
        model, system, body, k = free_turn(cfg, seeds, turns, i)
        text, u = be.call(model, system, body, cfg["effort"])
        usages.append(u)
        turns.append(make_turn(text, model, k, usage=u))
        if (i + 1) % 10 == 0 or i + 1 == cfg["turns"]:
            print(f"{label}: {i + 1}/{cfg['turns']} turns", flush=True)
    return turns, usages


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", required=True, help="batch id, e.g. b0007")
    ap.add_argument("--seeds", required=True, help="seed ids from runner/seeds.json, comma-separated")
    ap.add_argument("--pair", required=True, choices=sorted(PAIRS))
    ap.add_argument("--turns", type=int, default=40)
    ap.add_argument("--runs", type=int, default=4, help="runs per seed")
    ap.add_argument("--format", default="show-v1", choices=sorted(FORMATS))
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--mock", action="store_true", help="offline plumbing test, no API calls")
    a = ap.parse_args()

    if not re.fullmatch(r"b\d{4,}", a.batch):
        sys.exit("batch id must look like b0007")
    seeds = json.loads((HERE / "seeds.json").read_text())["seeds"]
    ids = [s.strip() for s in a.seeds.split(",") if s.strip()]
    unknown = [s for s in ids if s not in seeds]
    if unknown or not ids:
        sys.exit(f"unknown seed(s): {', '.join(unknown) or '(none given)'}")
    if len(set(ids)) != len(ids):
        sys.exit("a seed is listed twice")
    if not 1 <= a.turns <= MAX_TURNS or a.runs < 1 or len(ids) * a.runs > MAX_RUNS:
        sys.exit(f"limits: 1-{MAX_TURNS} turns, at most {MAX_RUNS} runs per batch")

    jobs = []
    for s in ids:
        for _ in range(a.runs):
            jobs.append(s)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    be = Mock() if a.mock else Claude()
    pair = PAIRS[a.pair]
    print(f"{a.batch}: {len(jobs)} conversations ({len(ids)} seeds x {a.runs}), {a.pair}, {a.turns} turns, "
          f"format {a.format}{' [MOCK]' if a.mock else ''}", flush=True)

    def one(n, seed):
        rid = f"{a.batch}-r{n:02d}"
        cfg = dict(FORMATS[a.format], pair=pair, turns=a.turns, seed=seed)
        rec = {"id": rid, "batch": a.batch, "run": n, "of": len(jobs), "seed": seed, "seed_text": seeds[seed]["text"],
               "pair": a.pair, "format": a.format, "cfg": cfg, "mock": a.mock, "api": API_URL,
               "runner_commit": os.environ.get("GITHUB_SHA"), "started": now()}
        try:
            rec["systems"] = [free_system(cfg, 0, seeds), free_system(cfg, 1, seeds)]
            rec["turns"], rec["usage"] = converse(cfg, seeds, be, rid)
            rec["status"] = "done"
        except Exception as e:
            rec.setdefault("turns", [])
            rec["status"] = "failed"
            rec["error"] = f"{type(e).__name__}: {str(e)[:300]}"
            print(f"{rid}: FAILED ({type(e).__name__})", flush=True)
        rec["finished"] = now()
        rec["cost_usd"] = round(cost_of(rec.get("usage", [])), 4)
        (out / f"{rid}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
        return rec

    with cf.ThreadPoolExecutor(max_workers=max(1, min(a.workers, len(jobs)))) as ex:
        recs = list(ex.map(lambda p: one(*p), [(i + 1, s) for i, s in enumerate(jobs)]))
    done = sum(r["status"] == "done" for r in recs)
    print(f"{a.batch}: {done} of {len(recs)} finished, ${sum(r['cost_usd'] for r in recs):.2f}", flush=True)


if __name__ == "__main__":
    main()
