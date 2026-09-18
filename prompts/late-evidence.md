You previously diagnosed this incident and returned the JSON diagnosis included below as `previous_diagnosis`. One additional event has now arrived late: `late_event`. It was not available at the time of your original diagnosis.

Re-run your full diagnosis from scratch using the original event list plus this new event, following the same system prompt and schema as before (see `analyst-system.md` — the same rules apply: hypotheses need both supports and contradicts, every citation must be a real `event_id`, checks ordered by decisiveness, recovery is a proposal only).

In addition to the standard output schema, also return a `diff` object describing what changed as a direct result of the new evidence:

```json
{
  "diff": {
    "new_event": { "event_id": "...", "ts": "...", "source": "...", "component": "...", "description": "...", "is_first_symptom": false },
    "changed_summary": "one sentence: what changed in the diagnosis and why",
    "rank_before": [{ "cause": "...", "rank": 1 }, { "cause": "...", "rank": 2 }],
    "rank_after": [{ "cause": "...", "rank": 1 }, { "cause": "...", "rank": 2 }],
    "what_changed": [
      "specific, concrete statements naming the evidence that moved a hypothesis up or down"
    ]
  }
}
```

Do not compute the diff by comparing JSON structurally — explain your own revision in your own words, the way an analyst would say "I'm changing my mind because of X." Return the full diagnosis object (all standard schema fields) plus this `diff` object, as one JSON document, no preamble, no markdown fences.
