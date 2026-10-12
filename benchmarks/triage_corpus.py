"""Natural-language triage corpus: sampled ground-truth states, wording written by a model.

The controller samples each event's facts (environment, who is affected, current status,
real or not, and an optional late correction or misleading cue) and derives the label
from those facts alone. A text model only writes the wording for each spec, so labels do
not depend on its judgment; specs whose wording breaks a check are regenerated or
dropped and counted. The frozen corpus, labels and generation receipts are written to an
owned directory. Generation calls the Claude Code CLI with no tools and its own login.
"""

import argparse
import hashlib
import json
import random
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from primary_claude import _environment, claude_launcher

SERVICES = [
    ("checkout", "checkout", "shoppers"),
    ("payments", "the payments API", "merchants"),
    ("login", "login / SSO", "users"),
    ("search", "product search", "customers"),
    ("mobile", "the mobile app sync", "app users"),
    ("orders", "order tracking", "buyers"),
    ("billing", "the billing portal", "account owners"),
    ("media", "image delivery / CDN", "site visitors"),
    ("notify", "email notifications", "subscribers"),
    ("support", "the help center", "customers"),
    ("video", "video playback", "viewers"),
    ("cart", "the shopping cart", "shoppers"),
]
REGIONS = ["EU", "US-East", "US-West", "APAC", "LATAM", "Japan", "all regions"]
NONPROD = ["staging", "pre-prod", "the QA cluster", "a sandbox tenant", "dev", "the perf-test env"]
INTERNAL = [
    "the internal admin console",
    "an internal ops dashboard",
    "the back-office export job used by support agents",
    "the staff-only analytics tool",
]
NOT_REAL = {
    "exercise": "it is a game day / chaos drill or rehearsal, not a real incident",
    "planned": "it describes planned maintenance (a scheduled window)",
    "hypothetical": "it is a question, a policy or a runbook rule, not an event",
    "past": "it refers to a past incident (postmortem or reminder), nothing happening now",
    "false_alarm": "it turned out to be a false alarm (broken probe or synthetic check)",
}
STYLES = [
    "a terse monitoring alert line",
    "a casual chat message from an engineer",
    "a status-page style update",
    "a short incident thread with one or two follow-up lines",
    "an email subject plus one sentence",
    "a pager notification with a short note",
]
TWISTS = {
    "none": "",
    "correction": "Include an early statement that suggests the opposite of the final truth, then "
    "a later correction or update that establishes the final truth.",
    "decoy": "Include a word or phrase that superficially suggests the opposite (for example "
    "mentioning staging, a drill, a rollback or customers in passing) without changing the "
    "final truth.",
}


def sample(count, seed):
    rng = random.Random(seed)
    specs = []
    for index in range(count):
        service, name, who = rng.choice(SERVICES)
        nature = rng.choices(["real", *NOT_REAL], weights=[70, 8, 6, 5, 5, 6], k=1)[0]
        spec = {
            "k": index,
            "service": service,
            "system": name,
            "who": who,
            "region": rng.choice(REGIONS),
            "production": rng.random() < 0.72,
            "customers": rng.random() < 0.75,
            "ongoing": rng.random() < 0.68,
            "nature": nature,
            "style": rng.choice(STYLES),
            "twist": rng.choices(list(TWISTS), weights=[45, 30, 25], k=1)[0],
            "nonprod": rng.choice(NONPROD),
            "internal": rng.choice(INTERNAL),
        }
        spec["page"] = (
            spec["production"] and spec["customers"] and spec["ongoing"] and nature == "real"
        )
        specs.append(spec)
    return specs


def facts(spec):
    """The facts a writer must convey; derived only from the sampled spec."""
    lines = [
        f"System: {spec['system']} (region {spec['region']}).",
        (
            "Environment: production / the live site."
            if spec["production"]
            else f"Environment: {spec['nonprod']} (not production)."
        ),
        (
            f"Who is affected: {spec['who']} (real customers or end users)."
            if spec["customers"]
            else f"Who is affected: only staff, via {spec['internal']}; {spec['who']} are not affected."
        ),
    ]
    if spec["nature"] == "real":
        lines.append(
            "Status: still happening now."
            if spec["ongoing"]
            else "Status: already resolved or mitigated now."
        )
        lines.append("Nature: a real incident.")
    else:
        lines.append("Nature: " + NOT_REAL[spec["nature"]] + ".")
    return " ".join(lines)


PROMPT = """Write realistic operations notifications for a synthetic incident-triage dataset.
For each spec, write ONE notification as {style}-like text (the style is given per spec).
Rules:
- Convey every listed fact so a careful reader can determine it, but in natural, varied
  wording: do not copy the spec phrasing, vary vocabulary, abbreviations and sentence shapes.
- Never state whether someone should be paged, and never use the words "spec", "fact" or "label".
- Apply the twist instruction when given. The FINAL truth must still be the listed facts.
- 1 to 3 sentences, at most 260 characters. Plain ASCII.
Return ONLY a JSON array of objects {{"k": <spec k>, "text": "<notification>"}}, one per spec.
Specs:
{specs}"""


def _batch_prompt(batch):
    rows = []
    for spec in batch:
        twist = TWISTS[spec["twist"]]
        rows.append(
            json.dumps(
                {
                    "k": spec["k"],
                    "style": spec["style"],
                    "facts": facts(spec),
                    **({"twist": twist} if twist else {}),
                }
            )
        )
    return PROMPT.format(style="the given", specs="\n".join(rows))


def _call(prompt, model, timeout):
    completed = subprocess.run(
        [
            *claude_launcher(),
            "-p",
            "--output-format",
            "json",
            "--model",
            model,
            "--tools",
            "",
            "--setting-sources",
            "",
            "--disable-slash-commands",
            "--strict-mcp-config",
        ],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_environment(),
        timeout=timeout,
    )
    envelope = json.loads(completed.stdout)
    text = envelope.get("result", "")
    start, end = text.find("["), text.rfind("]")
    rows = json.loads(text[start : end + 1])
    return rows, {
        "usage": envelope.get("usage"),
        "cost_usd_estimate": envelope.get("total_cost_usd"),
        "model_usage": envelope.get("modelUsage"),
        "is_error": envelope.get("is_error"),
    }


def generate(output, *, count, seed, model, batch_size=40, workers=4, timeout=240):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    specs = sample(count, seed)
    batches = [specs[i : i + batch_size] for i in range(0, len(specs), batch_size)]
    receipts, texts = [], {}

    def run(batch):
        try:
            rows, receipt = _call(_batch_prompt(batch), model, timeout)
        except Exception as error:  # retained, never retried silently
            return batch, [], {"error_type": type(error).__name__}
        return batch, rows, receipt

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for batch, rows, receipt in pool.map(run, batches):
            wanted = {spec["k"] for spec in batch}
            got = 0
            for row in rows:
                if (
                    isinstance(row, dict)
                    and row.get("k") in wanted
                    and isinstance(row.get("text"), str)
                    and 10 <= len(row["text"]) <= 400
                ):
                    texts[row["k"]] = " ".join(row["text"].split())
                    got += 1
            receipts.append({"batch_first_k": batch[0]["k"], "returned": got, **receipt})
    records, labels, dropped = [], {}, []
    for spec in specs:
        text = texts.get(spec["k"])
        if text is None or any(word in text.lower() for word in ("label", "spec ", "facts")):
            dropped.append(spec["k"])
            continue
        identifier = "evt-" + hashlib.sha256(f"{seed}:{spec['k']}:{text}".encode()).hexdigest()[:10]
        records.append({"id": identifier, "service": spec["service"], "text": text})
        labels[identifier] = spec["page"]
    with open(output / "records.jsonl", "w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    (output / "labels.json").write_text(json.dumps(labels), encoding="utf-8")
    (output / "specs.json").write_text(json.dumps(specs), encoding="utf-8")
    summary = {
        "count_requested": count,
        "records": len(records),
        "dropped": len(dropped),
        "positive": sum(labels.values()),
        "seed": seed,
        "model": model,
        "seconds": time.perf_counter() - started,
        "receipts": receipts,
        "records_sha256": hashlib.sha256((output / "records.jsonl").read_bytes()).hexdigest(),
    }
    (output / "generation.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261012)
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument("--batch-size", type=int, default=40)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    summary = generate(
        args.output,
        count=args.count,
        seed=args.seed,
        model=args.model,
        batch_size=args.batch_size,
        workers=args.workers,
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "receipts"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
