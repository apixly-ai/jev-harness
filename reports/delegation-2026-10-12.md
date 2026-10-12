# When a Claude primary delegates to Jev — 2026-10-12

On a **large-volume semantic triage** task, a Claude Code primary with an optional Jev
route chose to write a task script and hand the judging to Jev in **10 of 11 runs**, and
every one of those passed the independent check. That includes 2 of 3 runs with neither a
price nor any extra context in sight. On the earlier, smaller or rule-solvable tasks, it
did the work itself every time. Task shape decided the route; price information and a
daily-operations framing came along with Jev choices but cannot be separated from task
shape at these sample sizes.

| Natural triage corpus, optional Jev route | Chose Jev | Passed | Note |
|---|---:|---:|---|
| Neutral: no price anywhere, no extra context | 2 / 3 | 3 / 3 | The first run read all records itself |
| Daily-ops context, no price anywhere | 3 / 3 | 3 / 3 | |
| Daily-ops context, price visible in the SDK quickstart | 3 / 3 | 3 / 3 | Tool description still says only "billable" |
| Price stated in the `run_script` description | 1 / 1 | 1 / 1 | |
| Operator price note in the prompt | 1 / 1 | 1 / 1 | |
| **Total** | **10 / 11** | **11 / 11** | |

The task: from 1,000 notification events, save the ids of those that report an ongoing,
customer-facing production outage. Exclude staging/test environments, resolved incidents,
internal-only impact, drills, maintenance, false alarms and questions or postmortems. When
an event's text contains corrections, the latest statement decides. The independent check
needs precision and recall of at least 0.95 against hidden labels (287 events qualify).

| Route on this task | Runs | Precision / recall | Whole operation | Primary + Jev cost (estimate) |
|---|---:|---|---:|---:|
| Jev route (script + Jev run) | 10 | 0.990–1.000 / 0.9965–1.000 | median 64.9 s (52.4–193.8 s, n = 9) | median $0.27 ($0.20–$0.80) |
| Read every record, Jev optional | 1 | 1.000 / 1.000 | 147.3 s | $0.948 |
| Control without a Jev tool (read every record) | 1 | 1.000 / 1.000 | 94.6 s | $0.812 |

Primary cost is the Claude Code CLI's own estimate, not an invoice. Jev cost is actual usage
× $0.042 per million input tokens (output free; docs.typesafe.ai/models, checked
2026-10-12). Two Jev runs had one request with unknown usage, so their Jev cost is a lower
bound. One Jev run has no whole-operation time; see retained defects below.

## What the evidence supports

- **Delegation where it pays.** The shape is a thousand free-text events whose meaning
  turns on corrections and decoys, a fixed accuracy bar, and a ready batch-judgment
  scaffold. Stated reasons repeated one pattern: keyword rules would break on this
  wording, and one batched Jev question covers every event in seconds for about a cent.
- **Earlier readings came from one sample.** The first neutral run read everything itself.
  The next run, with a price in the tool description, delegated, and an earlier draft of
  this report credited the price. Two more neutral runs with no price anywhere also
  delegated. The event streams show none of these runs ever saw a price, and the first
  run had read the same quickstart. The difference was run-to-run variation, not
  information.
- **The daily-operations framing.** The context says the triage runs every day on a fresh
  batch, asks for a reusable procedure in `/work`, and names both routes equally. It was
  followed by Jev in 6 of 6 runs, against 2 of 3 without it: consistent with helping, not
  established.
- **Reuse the next day.** Two new sessions got a second frozen batch (1,000 different
  events, 251 qualify) and the previous `/work`. Both re-ran the existing script and
  passed:
  - 0.996 / 0.996 and 1.000 / 1.000;
  - 14 turns each;
  - primary $0.270 and $0.260 plus about $0.010 Jev;
  - 69.2 s and 67.9 s.

  The primary still inspected and verified, so most of the next-day cost is the primary's.
  A scheduler running the script alone would pay only the Jev share. That share is
  measured per run (about 12 s and $0.01), not as a scheduled deployment.

## Task shapes that did not favour Jev

**Template-generated triage (2,000 events).** Both arms noticed that the events came from
a small set of sentence templates. Each wrote deterministic keyword rules and passed with
precision and recall of 1.0 (36.3 s / $0.229 and 47.5 s / $0.224), with no Jev usage.
Rules are the right tool for enumerable text, which is why the counted corpus is natural
language.

**Repeated browser form (six differing team workspaces).** Zero-model transport passed: 93
effects on the host program path and in the container, plus two fake-provider executions
with correct budget accounting. Live Jev with our reference `SurfaceTask` script still
**completed no team in four development runs**. Every run stopped at `needs_review`: Jev's
top choice was usually right but at 0.38–0.54 probability, below the unchanged 0.55 / 0.10
gate. It also initially ranked a staging project above a correct production one. A target
filter, an ordering hint and a combined tool got one team to 15 correct steps, but no run
saved a draft. Thresholds were not relaxed, so no primary pair ran on this task.
Development runs cost $0.044.

**The 13-control browser form** ([report](browser-cold-2026-10-12.md)) stayed direct even
with an operator price note: doing it directly was already cheap.

## Corpora

The controller samples each event's facts: environment, who is affected, status, whether
it is real, and an optional late correction or misleading cue. The label comes from those
facts alone; Claude Haiku 5.5 only wrote the wording. Each 1,000-event batch cost about
$0.16 (CLI estimate), with none dropped. The frozen corpora, labels, specs and generation
receipts are in `benchmarks/fixtures/triage-natural-v1/` and `triage-natural-v2/`.
Reading checks found no label/text mismatch: 30 random events of v1, 20 of v2, and a
separate 40-event trial batch. The corpora were not fully hand-audited.

Jev accuracy probes on v1:

| Setup | Precision | Recall | Requests | Time |
|---|---:|---:|---:|---:|
| One question, host | 0.990 | 1.000 | 16 | 2.6 s |
| Four typed questions combined in code, host | 0.997 | 1.000 | 46 | — |
| Unedited `init-task --toolkit records` scaffold, isolated worker | 0.990 | 1.000 | 17 | 12.5 s ($0.009) |

On a harder rule-generated "thread" corpus, one question reached 0.873 precision and four
typed questions 0.965.

## Product changes from this search

- `init-task --toolkit records`: a batch-judgment `TaskScript` around `Engine().decide`.
  It runs one typed question over many records in packed requests and saves matching and
  unclear ids. It is in the quickstart card and the spec. Every Jev run above started
  from it.
- `init-task --toolkit surface`: an editable `SurfaceTask` scaffold.
- `SurfaceTask` gains three features:
  - `allow(target)` lets caller business rules narrow the offered controls;
  - candidates carry table-row context;
  - `tools="combined"` offers one page-ordered `operate` tool.

  Defaults and confidence thresholds are unchanged.
- The quickstart and all templates state the dated published Jev price.
- Benchmarks:
  - `browser_batch.py` (repeated form) and `run_script` multi-execution with shared
    budgets and an optional per-run focus;
  - `records_triage.py`, `triage_corpus.py`, `records_cold.py` (seeded `/work`,
    per-session journals), `records_pair.py` (conditions, supplied wheel, `recover`) and
    `export_delegation.py`.

## Isolation, acceptance and spend

Every arm used the same isolated container shell over a read-only corpus, with a writable
`/work`, no network and bounded shell output. Every arm had the same `check_goal`, which
returns pass/fail and counts and never labels. The optional arm also had `run_script`.
Its budget was up to 3 executions; each with at most 8 Jev steps, 100 s and 50 provider
requests; at most 150 requests and 300 s per session. The credential and labels stayed
host-only.

"No price anywhere" runs used a runtime wheel built from the same commit with the price
lines removed. A zero-model canary, a live validation with the unedited scaffold and a
foreign-working-directory rehearsal passed for each corpus before the paid turns.

The primary was `claude-opus-5-5` (effort high), resolved identically, with no fallback.

Retained defects:

- **A runner crash after one session.** The runner deleted the CLI's scratch directory
  under a Windows file lock and crashed after one finished session (ops, no price, run 3).
  Its receipt was rebuilt from the saved stream with `records_pair.py recover`. Its
  whole-operation time is unknown (the CLI reported 143 s). Scratch cleanup now ignores
  that error.
- **A disqualified turn in the same run.** That run first called its answer tool under a
  wrong, prefixed name ("no such tool"), then the right one. The strict adapter
  disqualifies the turn. The route and the saved report are still the run's own; the
  table counts its choice.
- **A failed first execution in each next-day session.** The seeded `/work` held a journal
  with the same name, so the first execution failed with `FileExistsError` (0 requests).
  The primary re-ran and passed. Journals are now per session.
- **Undercounted totals.** Two receipts first summed a run with unknown usage as zero
  tokens. The export now keeps known tokens as a lower bound.

Total Jev usage across every development probe, validation and run on 2026-10-12 was
753 requests and at least 7.24 M input tokens (two runs had one request with unknown
usage), about $0.30 at the published price. No single
session exceeded 98 requests.

## Scope

One primary model and small samples: 10 of 11 is a count on one task with one corpus
family, not a population rate. The corpora are model-written synthetic text with
controller-derived labels. The direct route was as accurate as the Jev route (1.000 vs
0.990–1.000), so the advantage shown is cost and time, not quality. The template corpus
shows rules beating delegation on enumerable text. The browser form shows the current Jev
calibration does not carry multi-step form operation under the unchanged gates.

Receipts: [delegation-2026-10-12.json](delegation-2026-10-12.json).
