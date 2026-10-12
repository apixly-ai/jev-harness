# Browser cold start with a Claude primary — 2026-10-12

A Claude Code primary received the same browser goal in two arms. Both chose direct
operation through the bounded browser tools, performed **13 effects** and passed the
independent check of the backend-saved draft. The optional arm could also author a task
script and hand it to live Jev; it declined, so **actual Jev inference was zero**. This is
one more negative route-choice result: the harness is not shown to be a default preference.

| Arm | Route | Effects | Independent saved-state check | Whole operation | Primary turns |
|---|---|---:|---|---:|---:|
| Direct-only control | Direct `observe`/`act` | 13 | Pass, 1 save attempt | 79.7 s | 18 |
| Same tools + optional caller-authored Jev | Direct `observe`/`act`; no task file, no `run_script` | 13 | Pass, 1 save attempt | 73.5 s | 19 |

Goal (variant 0): create a weekday failure-digest draft for all active production
projects, include failed and blocked events, use the given timezone and the existing
Preview inbox, save only a draft. Both saved drafts contained exactly the expected title,
note, timezone, frequency, events, the two active production projects, mailbox and draft
status. No send, delete or activation occurred.

The arms' stated reasons were similar: a small fixed form, fresh feedback after each
action, and no benefit from extra setup. The optional arm also cited Jev's provider
requests as a cost. These are self-reports, not measured counterfactuals.

## Primary identity and usage

Requested `claude-opus-5-5` (effort high); the stream resolved `claude-opus-5-5` in both
arms with no refusal fallback. CLI-reported usage (Claude Code `modelUsage`):

| Arm | Input | Cache read | Cache creation | Output |
|---|---:|---:|---:|---:|
| Direct-only | 32 | 247,066 | 26,467 | 2,512 |
| Optional harness | 34 | 259,317 | 27,350 | 2,894 |

The CLI also reports cost estimates (0.312 and 0.329 USD); they are not invoices. Whole
operation includes CLI start, MCP server preparation (container, owned tab, runtime
probe), all turns and the final answer. One pair is not a latency or cost comparison;
both arms used the same route, so the 6 s difference is ordinary variation.

## What the primary could and could not do

Each arm ran one headless `claude -p` turn whose effective inventory (from the stream's
init event) contained only the evaluation server's tools plus the structured-output
answer channel: no built-in tools, user skills, slash commands, settings sources or other
MCP servers. Three built-in CLI plugins (agents-md, telemetry, plugin-authoring) load
regardless and contributed no tools. The browser could be operated only through
observed opaque action IDs; filling accepted only supplied named values; send/delete
controls were excluded; a shared budget allowed 24 effects and a 600 s session. The
container shell had no network, a read-only corpus/runtime and a writable `/work`.

An earlier neutrality audit prompt that asked the primary to list its instructions
triggered an Opus 5.5 safeguard and a CLI fallback to `claude-opus-4-8`. That happened
only on the audit prompt; the adapter now records any such fallback per turn.

## Runtime evidence, not configuration

This machine's Camofox (camofox-browser 2.4.8) reports per-context `activeUserIds` in
`/health` but no headless or humanize fields. Configuration is recorded only as a
precondition for opening a tab. After the owned tab opens, the gate requires:

- the named session's full-profile context is active;
- every browser process under the service listener carries `-headless`, the session's
  own profile process is among them, and the process tree owns no visible window;
- a pointer probe in its own owned tab of the same session, clicked through the same
  route actions use, shows a humanized trajectory (pair runs: 113 and 106 moves over
  1.29 s and 1.19 s). A separate temporary instance with humanize disabled produced
  1 move and 0 ms, so the probe discriminates.

## Transport acceptance before paid turns (zero model calls)

| Check | Result |
|---|---|
| Host program path, real Camofox | 13 effects; independent check pass; 23.6 s |
| Container `RemoteSurface` program path (Docker Desktop / WSL dockerd) | 13 effects, pass; 19.5 s / 14.7 s |
| Worker `run_script` with offline fake provider | Real IPC round trips, 0 unknown submissions; stops `blocked` after one unchanged click (completion not expected) |
| Container isolation canary (WSL dockerd) | No oracle, credential canary or Docker socket; corpus/root writes and network blocked |
| Serve rehearsal from a foreign working directory | Handshake, observe (5 controls), initial check `not_saved`, 0 effects |

## Retained failures and environment changes

- **Infrastructure attempt (not a task result).** The first paid pair passed relative
  paths to the evaluation server; the CLI starts MCP servers in its own working directory,
  so the server exited and neither arm had task tools. Both answered `complete: false`.
  Usage: 2/0/4,905/572 and 2/4,328/576/748 (input/cache read/cache creation/output).
  The adapter now disqualifies a turn whose evaluation server is not connected; paths are
  absolute; the rehearsal launches the server the way the CLI does.
- **Real client behaviour fixed before the counted pair.** The CLI sends a version probe
  before `initialize` and starts its connection clock immediately: the server now answers
  the handshake at once, prepares in the background, returns JSON-RPC errors for unknown
  methods, writes durable evidence before slow cleanup, and the runner closes only the
  recorded tab or stops only the recorded container if the client terminates the server.
- **Post-completion defect in the counted pair.** After the optional arm's check had
  passed, its final shell call (to write an optional report) found the container gone: the
  WSL distribution stopped while idle between short-lived `wsl.exe` calls. Route and
  saved state were unaffected. A held `wsl.exe` session now keeps dockerd alive.
- **Host environment.** Windows AF_UNIX sockets failed system-wide during the session
  (bind succeeded, connect failed, files became inaccessible), which stopped Docker
  Desktop's backend. Instead of a reboot, the same Linux containers ran on dockerd inside
  WSL Ubuntu (installed from the Ubuntu archive).
- **Primary change.** The previous ChatGPT-account model `gpt-6.1-sol` is unavailable on
  this account and the user asked for Claude, so this pair is not comparable to the
  earlier Codex rows.

## Scope

One pair, one variant, one primary model; it measures what this primary chose on this
13-control form, not a success rate, latency or cost distribution. It does not show that
authoring a Jev script is slower or faster: no script was written. Live Jev inference and
TypeSafe usage in the counted pair were zero. Receipts:
[browser-cold-2026-10-12.json](browser-cold-2026-10-12.json); runners
`benchmarks/browser_cold.py`, `benchmarks/browser_cold_pair.py`,
`benchmarks/camofox_runtime.py`, `benchmarks/primary_claude.py`.
