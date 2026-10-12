"""Synthetic large-volume semantic triage: which notification events need paging now.

Records are generated from owned templates with paraphrases, qualifiers and distractors,
so a single keyword rule does not separate them. Hidden labels stay with the controller;
they are never written to the actor corpus. Importing this module starts no inference.
"""

import hashlib
import json
import random

SERVICES = [
    ("checkout", "Checkout", "shoppers"),
    ("payments", "Payments API", "merchants"),
    ("login", "Login", "users"),
    ("search", "Search", "customers"),
    ("mobile", "Mobile app sync", "app users"),
    ("orders", "Order tracking", "buyers"),
    ("billing", "Billing portal", "account owners"),
    ("media", "Image delivery", "visitors"),
    ("notify", "Email notifications", "subscribers"),
    ("support", "Help center", "customers"),
]
REGIONS = ["EU", "US-East", "US-West", "APAC", "LATAM", "all regions"]
SYMPTOMS = [
    "requests are failing for {who}",
    "{who} are getting 5xx errors",
    "is timing out for most {who}",
    "{who} cannot complete the flow",
    "is unreachable for {who}",
    "error rate above 20% for {who}",
    "{who} report blank pages",
    "latency over 30 seconds for {who}",
    "{who} are unable to sign in or pay",
    "returns errors to roughly half of {who}",
]
OPENERS = ["Alert:", "Pager:", "Incident update:", "Monitor:", "", "Heads up -", "Status:"]
ONGOING = [
    "since {time} and still happening",
    "ongoing, no mitigation yet",
    "started at {time}, still degraded",
    "continuing; engineers investigating",
    "",
    "impact growing",
]
# Distractor families: each is (label_reason, template) with no paging needed.
NEGATIVE = {
    "non_production": [
        "{opener} {name} {symptom} in staging {region}",
        "{opener} pre-prod {name}: {symptom}",
        "{opener} {name} in the QA cluster {symptom}",
        "{opener} sandbox {name} {symptom} ({region} test tenant)",
        "{opener} canary build on the dev environment: {name} {symptom}",
    ],
    "resolved": [
        "{opener} {name} {symptom} earlier; recovered at {time}, error rate back to baseline",
        "{opener} Resolved: {name} {symptom} between {time} and {time2}",
        "{opener} {name} was failing for {who} but mitigated after rollback and stable since {time}",
        "{opener} no longer seeing errors on {name} in {region}; closing the incident",
    ],
    "internal_only": [
        "{opener} {name} admin console is slow for the ops team only; {who} unaffected",
        "{opener} internal {name} dashboard timing out for employees; no customer impact",
        "{opener} {name} batch report job failing overnight; customer traffic healthy",
    ],
    "planned_or_drill": [
        "{opener} scheduled maintenance tonight: {name} in {region} will be read-only",
        "{opener} game day drill: simulated {name} outage in {region}, no real impact",
        "{opener} chaos exercise injecting faults into {name}; customers not affected",
        "{opener} tabletop rehearsal of a {name} outage planned for Friday",
    ],
    "false_alarm": [
        "{opener} {name} alert fired but traffic and success rate look normal; probe misconfigured",
        "{opener} synthetic check for {name} flapping; real {who} requests all succeed",
    ],
    "noise": [
        "{opener} {name} deploy finished successfully in {region}",
        "{opener} weekly cost report for {name} is ready",
        "{opener} {name} certificate renews in 21 days",
        "{opener} new dashboard for {name} published",
        "{opener} {name} capacity increased for the holiday peak",
    ],
}
POSITIVE = [
    "{opener} {name} {symptom} in {region} {ongoing}",
    "{opener} production {name}: {symptom} ({region}), {ongoing}",
    "{opener} {name} {region} - {symptom}; {ongoing}",
    "{opener} customers affected: {name} {symptom} in {region}",
]

QUESTION = (
    "Does this notification report a customer-facing production outage or severe "
    "degradation that is still ongoing and needs someone paged now? Not staging, test, dev "
    "or sandbox; not already resolved or mitigated; not internal-only; not planned "
    "maintenance, drills or false alarms; not routine notices."
)


def _fill(template, rng):
    service, name, who = rng.choice(SERVICES)
    hour = rng.randint(0, 22)
    values = {
        "opener": rng.choice(OPENERS),
        "name": name,
        "who": who,
        "region": rng.choice(REGIONS),
        "time": f"{hour:02d}:{rng.randint(0, 59):02d} UTC",
        "time2": f"{hour + 1:02d}:{rng.randint(0, 59):02d} UTC",
        "ongoing": rng.choice(ONGOING),
    }
    values["symptom"] = rng.choice(SYMPTOMS).format(**values)
    text = " ".join(template.format(**values).split()).strip(" ,;-")
    return service, text


def generate(count=1000, *, seed=20261012, positive_share=0.22):
    """Return (records, labels). records carry id/text/service only."""
    rng = random.Random(seed)
    records, labels, seen = [], {}, set()
    families = list(NEGATIVE)
    while len(records) < count:
        positive = rng.random() < positive_share
        template = rng.choice(POSITIVE) if positive else rng.choice(NEGATIVE[rng.choice(families)])
        service, text = _fill(template, rng)
        if text in seen:
            continue
        seen.add(text)
        identifier = (
            "evt-" + hashlib.sha256(f"{seed}:{len(records)}:{text}".encode()).hexdigest()[:10]
        )
        records.append({"id": identifier, "service": service, "text": text})
        labels[identifier] = positive
    return records, labels


NONPROD = ["staging", "pre-prod", "QA", "sandbox", "dev", "perf-test"]
TEAMS = ["payments", "identity", "storefront", "platform", "mobile", "search"]
BASE = {
    "plain": [
        "{name} {symptom} in {region}.",
        "Seeing {name} {symptom} ({region}).",
        "{name}: {symptom}, {region}.",
        "Getting reports that {name} {symptom} in {region}.",
    ],
    "prod": [
        "Prod {name} {symptom} in {region}.",
        "Production {name}: {symptom} ({region}).",
        "Live site: {name} {symptom} in {region}.",
    ],
    "nonprod": [
        "{Env} {name} {symptom}.",
        "{name} in {env}: {symptom}.",
        "On the {env} stack, {name} {symptom}.",
    ],
    "internal": [
        "{name} admin console is timing out for the ops team in {region}.",
        "Internal {name} dashboard erroring for staff.",
        "{name} back-office export failing for support agents.",
    ],
    "drill": [
        "[Game day] {name} {symptom} in {region}.",
        "Drill in progress: {name} {symptom}.",
        "Chaos exercise: injecting faults so {name} {symptom}.",
    ],
    "planned": [
        "Heads up for tomorrow: maintenance will make {name} unavailable for {who} in {region}.",
        "Planned window tonight: {name} read-only for {who}.",
    ],
    "hypothetical": [
        "If {name} ever {symptom2}, page the on-call immediately.",
        "Question: should we page when {name} {symptom2}?",
    ],
    "past": [
        "Postmortem draft: last Tuesday {name} {symptom2} for two hours.",
        "Reminder: the {name} outage last week was caused by a bad config.",
    ],
}
FOLLOW = {
    ("status", "resolved"): [
        "Update {time}: rolled back, error rate back to baseline.",
        "Fixed by restarting the pool; healthy since {time}.",
        "Recovered at {time}.",
        "All clear now.",
        "Mitigated: traffic shifted and {who} are fine.",
    ],
    ("status", "ongoing"): [
        "Update {time}: the rollback did not help, still failing.",
        "Thought it was fixed, but errors came back at {time}.",
        "Not resolved yet.",
        "The restart did not stick; still failing.",
    ],
    ("env", "nonprod"): [
        "Correction: this is the {env} cluster, not production.",
        "Never mind, it is only the {env} environment.",
    ],
    ("env", "prod"): [
        "Correction: it is production, not {env}.",
        "{Env} is fine; this is the live site.",
    ],
    ("impact", "internal"): [
        "Only staff tools are affected; {who} are fine.",
        "Customer traffic is healthy, only internal dashboards.",
    ],
    ("impact", "customer"): [
        "Confirmed customer impact: {who} are complaining.",
        "Not just internal, {who} see it too.",
    ],
    ("kind", "drill"): [
        "This is part of today's game day exercise.",
        "Planned chaos test, expected.",
    ],
    ("kind", "real"): ["Not a drill.", "This is real, not the exercise."],
    ("kind", "false_alarm"): [
        "False alarm: probe misconfigured, {who} unaffected.",
        "Turned out to be a broken synthetic check; real traffic is fine.",
    ],
}
NOISE = [
    "Ticket INC-{n}.",
    "Owner: {team} team.",
    "Dashboard link in thread.",
    "cc on-call.",
    "Region lead notified.",
]
THREAD_RULES = (
    "An event concerns production unless its text says otherwise. When an event contains "
    "updates or corrections, the latest statement about each fact decides."
)


def _thread(rng):
    service, name, who = rng.choice(SERVICES)
    env = rng.choice(NONPROD)
    hour = rng.randint(0, 21)
    values = {
        "name": name,
        "who": who,
        "region": rng.choice(REGIONS),
        "env": env,
        "Env": env[0].upper() + env[1:],
        "time": f"{hour:02d}:{rng.randint(0, 59):02d} UTC",
        "n": rng.randint(1000, 9999),
        "team": rng.choice(TEAMS),
    }
    values["symptom"] = rng.choice(SYMPTOMS).format(**values)
    values["symptom2"] = rng.choice(["fails for " + who, "returns 5xx", "times out", "goes down"])
    base = rng.choices(list(BASE), weights=[30, 14, 14, 10, 9, 6, 6, 6], k=1)[0]
    state = {
        "env": "nonprod" if base == "nonprod" else "prod",
        "impact": "internal" if base == "internal" else "customer",
        "status": "ongoing",
        "kind": base if base in ("drill", "planned", "hypothetical", "past") else "real",
    }
    sentences = [rng.choice(BASE[base]).format(**values)]
    if state["kind"] in ("real", "drill"):
        for _ in range(rng.choices([0, 1, 2], weights=[30, 45, 25], k=1)[0]):
            key = rng.choice(list(FOLLOW))
            sentences.append(rng.choice(FOLLOW[key]).format(**values))
            state[key[0]] = key[1]
    for _ in range(rng.choice([0, 0, 1, 2])):
        sentences.insert(rng.randint(0, len(sentences)), rng.choice(NOISE).format(**values))
    positive = state == {
        "env": "prod",
        "impact": "customer",
        "status": "ongoing",
        "kind": "real",
    }
    return service, " ".join(sentences), positive


def generate_threads(count=1000, *, seed=20261012):
    """Multi-sentence events whose latest update or correction decides the label."""
    rng = random.Random(seed)
    records, labels, seen = [], {}, set()
    while len(records) < count:
        service, text, positive = _thread(rng)
        if text in seen:
            continue
        seen.add(text)
        identifier = (
            "evt-" + hashlib.sha256(f"{seed}:{len(records)}:{text}".encode()).hexdigest()[:10]
        )
        records.append({"id": identifier, "service": service, "text": text})
        labels[identifier] = positive
    return records, labels


def score(selected, labels):
    selected = set(selected)
    truth = {k for k, v in labels.items() if v}
    unknown = selected - set(labels)
    tp, fp, fn = len(selected & truth), len(selected - truth), len(truth - selected)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "submitted": len(selected),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "unknown_ids": len(unknown),
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }


def write_corpus(path, records):
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
