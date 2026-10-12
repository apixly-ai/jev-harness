# When a Claude primary delegates to Jev — 2026-10-12

A Claude Code primary chose to hand work to Jev for the first time in these evaluations. It
happened on a **large-volume semantic triage** task once the Jev price was visible. With
the price stated as a plain fact in the tool description, the primary wrote one task
script, ran Jev once and passed the independent check. Compared with the same tools
without the price, total estimated cost was 29% ($0.274 vs $0.948) and whole operation
time was 41% (60.7 s vs 147.3 s). Without the price, the same primary read all 1,000
records itself.

| Natural triage corpus (1,000 events, 287 need a page) | Route | Precision / recall | Whole operation | Primary turns | Primary cost (CLI estimate) | Jev cost (published price) |
|---|---|---:|---:|---:|---:|---:|
| Control: no Jev tool | Read all records | 1.000 / 1.000 | 94.6 s | 26 | $0.812 | — |
| Jev optional, neutral docs ("billable") | Read all records | 1.000 / 1.000 | 147.3 s | 28 | $0.948 | $0 |
| Jev optional, price as a fact in the tool docs | Script + 1 Jev run | 1.000 / 1.000 | 60.7 s | 12 | $0.264 | $0.010 |
| Jev optional, operator price note in the prompt | Script + 1 Jev run | 0.990 / 1.000 | 52.4 s | 9 | $0.214 | $0.012 |

The task: save the ids of notification events that report an ongoing, customer-facing
production outage. Exclude staging/test environments, resolved incidents, internal-only
impact, drills, maintenance, false alarms and questions or postmortems. When an event's
text contains corrections, the latest statement decides. The independent check needs
precision and recall of at least 0.95 against hidden labels.

Each row is one observation, not a rate. The CLI cost fields are the Claude Code CLI's
own estimates, not invoices. Jev cost is actual usage × $0.042 per million input tokens
(output free; docs.typesafe.ai/models, checked 2026-10-12).

## What changed the choice

- **The price, stated as a fact.** The neutral `run_script` description ends "Live Jev
  inference is billable." The primary then avoided "billable Jev inference" and read
  everything instead. One appended sentence fixed that; the prompt and everything else
  were unchanged:

  > Published Jev price: $0.042 per million input tokens; output tokens are free
  > (TypeSafe jev-1.13.0).

  The primary then chose Jev. Its stated reason: the "latest statement decides" rule over
  1,000 free-text events needs judgment that keyword rules would get wrong, and Jev
  covered every event "in a few seconds for about a cent".
- **The operator note works too.** This was an earlier variant listing Jev, Claude Haiku
  5.5, GPT-5.6 Luna and Opus 5.5 prices plus the operator's expectation that delegating
  lowers cost. The plain fact alone was enough, so the product docs now carry the dated
  published price instead of only "billable".
- **Task shape matters as much as price.** The same operator note did not move the
  primary on a 13-control browser form
  ([browser report](browser-cold-2026-10-12.md)): doing it directly was already cheap.
  It did move it here, where reading everything directly cost about $0.8–0.95.

## Task shapes that did not favour Jev

**Template-generated triage (2,000 events).** Both arms noticed that the events came from
a small set of sentence templates. Each wrote deterministic keyword rules in the
container and passed with precision and recall of 1.0 (36.3 s / $0.229 and 47.5 s /
$0.224), with no Jev usage. The optional arm's reason was that rules were "exact, quick to
verify and cost nothing". That is the right call for enumerable text. It is why the
counted corpus is natural language.

**Repeated browser form (six differing team workspaces).** The workspaces differ in
navigation, labels, page split, pagination and a confirmation step, so one fixed click
sequence does not fit every team. Zero-model transport passed: 93 effects on the host
program path and in the container, plus two fake-provider executions with correct budget
accounting. Live Jev with our reference `SurfaceTask` script still **completed no team in
four development runs**. Every run stopped at `needs_review`: Jev's top choice was usually
right but at 0.38–0.54 probability, below the unchanged 0.55 / 0.10 gate. It also
initially ranked a staging project above a correct production one. Each fix (a target
filter for business rules, an ordering hint, a single combined tool) moved further, up to
15 correct steps for one team. No run saved a draft. Thresholds were not relaxed, so no
primary pair was run on this task. Development runs cost $0.044 at the published price.

## Natural corpus

The controller samples each event's facts: environment, who is affected, status, whether
it is real, and an optional late correction or misleading cue. The label comes from those
facts alone. Claude Haiku 5.5 only wrote the wording ($0.16 CLI estimate for 1,000 events,
none dropped). The frozen corpus, labels, specs and generation receipts are in
`benchmarks/fixtures/triage-natural-v1/`. A reading check of 30 randomly sampled events
from the frozen corpus (and of a separate 40-event trial batch) found no label/text
mismatch; the full corpus was not hand-audited.

Jev accuracy on it (host probes, one question): precision 0.990, recall 1.000 in 2.6 s and
16 requests. Splitting into four typed questions combined in code gave 0.997 / 1.000 with
46 requests. On a harder rule-generated "thread" corpus, one question reached only 0.873
precision; four typed questions reached 0.965. Through the isolated worker path, the
**unedited** `init-task --toolkit records` scaffold scored 0.990 / 1.000 in 12.5 s with 17
requests ($0.009).

## Product changes from this search

- `init-task --toolkit records`: a batch-judgment `TaskScript` around `Engine().decide`.
  It runs one typed question over many records in packed requests and saves matching and
  unclear ids. It is in the quickstart card and the spec.
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
  - `records_triage.py`, `triage_corpus.py`, `records_cold.py`, `records_pair.py` and
    `export_delegation.py`.

## Isolation, acceptance and spend

Both arms used the same isolated container shell over the same read-only corpus, with a
writable `/work`, no network and bounded shell output. They had the same `check_goal`,
which returns pass/fail and counts and never labels. The optional arm additionally had
`run_script`. Its budget was up to 3 executions; each with at most 8 Jev steps, 100 s and
50 provider requests; at most 150 requests and 300 s per session. The credential and
labels stayed host-only.

For each corpus, a zero-model canary covered shell I/O, check behaviour, scaffold
generation and fake-provider plumbing. A live validation ran the unedited scaffold, and a
foreign-working-directory serve rehearsal followed. All passed before the paid turns.

The primary was `claude-opus-5-5` (effort high) in every arm, resolved identically, with
no fallback. Primary usage (input / cache read / cache creation / output) in the counted
natural rows was:

- control: 48 / 833,851 / 65,410 / 6,075;
- neutral: 52 / 942,112 / 70,873 / 9,604;
- priced docs: 22 / 136,312 / 23,060 / 2,632;
- price note: 16 / 86,439 / 18,447 / 2,456.

Total Jev usage across every development probe, validation and run on 2026-10-12 was 506
requests and 4.03 M input tokens, about $0.17 at the published price. No single session
exceeded 98 requests.

## Scope

One primary model and one sample per condition: these are observations of what this
primary chose, not preference rates or cost distributions. The natural corpus is
model-written synthetic text with controller-derived labels. The direct route was at
least as accurate here (1.000 vs 0.990–1.000), so the advantage shown is cost and time,
not quality. The template corpus shows that deterministic rules beat delegation when text
is enumerable. The browser form shows that the current Jev calibration does not carry
multi-step form operation under the unchanged gates.

Receipts: [delegation-2026-10-12.json](delegation-2026-10-12.json).
