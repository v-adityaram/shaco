# Briefing — the HIP vocabulary, and why AI on top of existing rules

For anyone who needs to understand the dashboards and the demo without an integration-platform background, and to answer the objection *"we already have 300–400 monitoring rules."*

Part 1 is a glossary of everything on the dashboard. Part 2 is the argument.

---

## Part 1 — The vocabulary

### What HIP is

Large companies run many separate systems (SAP for finance and stock, warehouse software, Salesforce, and so on). **HIP** is the platform that moves data between them, an *integration platform*. Think of it as a postal service for business data: it picks up a message from one system, translates it, and delivers it to another.

### The dashboard's core units

The dashboard is called **Sonar**. It is built on **Kibana**, the standard tool for searching and charting logs, over **ELK** (Elasticsearch, Logstash, Kibana, a log-storage stack). **KQL** is Kibana's query language; it is what the search box takes.

| Term | Meaning | Software analogy |
| --- | --- | --- |
| **Exchange** | One business transaction from start to finish, such as one delivery notice | One distributed trace |
| **Half-flow** | One stage inside an exchange (receive, translate, route, deliver) | A span within a trace |
| **`exchange.id`** | Unique ID shared by every log line of that transaction | Trace ID |
| **`halfflow.count`** | How many stages have been seen so far | |
| **`halfflow.missing` (e.g. `2/4`)** | In the demo data: the exchange is waiting at stage 2 of 4. Finished exchanges show `0/4` | |
| **Project** | The business area a flow belongs to (e.g. `SAPITCOMMON`) | Namespace |
| **Source / destination** | The systems the data travels between | |
| **`object.id` / `object.name`** | The business item being moved, e.g. a delivery number of type `DELVRY07` | Payload identity |
| **`event.code`** | Code for the type of log event (`IFP_PUB001`, `IFP_MAP001`) | Log event type |
| **`business.value`** | A business detail attached to the record | |
| **`framework.version`** | Version of the HIP framework that handled it | |

### Statuses and log levels

- **COMPLETE** — finished. **COMPLETE (F)** — finished after a failure and retry.
- **INPROGRESS** — started, not finished. This is the dangerous one, because it never raises an error by itself.
- **FAILED** — errored. **WARNING** — finished with a caveat. **REPLAYED** — re-run by a person or job.
- **ENTRYINFO / EXITINFO** — a log line written when an exchange enters or leaves a stage. **ERROR / INFO** — as they sound.

### The tiles at the top

Total exchanges in 24 hours, a count per status, **Failures %**, and **Duration Avg / Max**. The second row is the same measures counted per half-flow instead of per exchange.

### Monitoring tools (the "rules")

- **HIPMON** — the client's rule engine. When a rule matches, it raises an automatic ServiceNow ticket whose title looks like `[AUTO]|PROJECT|HALFFLOW|CODE`.
- **Splunk** — watches servers (CPU, memory, disk). Its alerts start `CAPLINERR…`.
- **Sonar hourly report** — a scheduled summary of critical exchanges.
- **Rule hit** — one alert a rule already fired. In the demo everything else the AI reads is **context**: logs, metrics and records looked up around the hits.

### Infrastructure terms

- **Kafka** (the client uses **Confluent**'s version) — a durable message queue. Producers write to a **topic**; **consumers** read from it.
- **Consumer lag** — messages written but not yet processed; a backlog.
- **Processing group** — in HIP, a set of running servers that consume one topic to execute half-flows.
- **Kubernetes / pod** — how the software runs; a pod is one running copy.
- **Heap / GC** — a program's working memory and the cleanup that reclaims it. When heap fills, garbage collection runs constantly and everything slows down.
- **OOMKilled** — the system kills a pod for using too much memory; it then restarts.

### Integration tools

- **Workato** — a workflow platform from a third-party vendor; one workflow is a **recipe**.
- **MFT / SFG (Sterling File Gateway)** — managed file transfer: reliable file delivery between systems.
- **Apigee / APIM** — API gateways, the front door for web-service calls. **5xx** means a server error, **4xx** a bad request.
- **Control-M** — a batch job scheduler.

### Business and SAP terms

- **SAP S/4 / SAP hubs** — the main business software. CE, UK, IT and NE appear to be regional SAP systems (inferred from the names; not confirmed).
- **PI7** — SAP's own integration hub, which sends messages into HIP.
- **IDoc** — SAP's document format, e.g. a delivery. **RFC** — a remote function call into SAP; `ConfigForDocSending` is one such function.
- **ASN** — advance shipping notice. **STO** — stock transport order (moving stock between sites).
- **Manhattan** — the warehouse management system.

### Operations terms

- **ServiceNow / INC** — the ticketing system; `INC10790101` is an incident number.
- **P1–P5** — priority; P1 is the worst.
- **Duplicate / parent–child incidents** — several tickets raised for one event, linked together.
- **L1 / L2 / L3** — support tiers, from first responders up to specialists or the vendor.
- **Bridge call** — the live conference call where engineers work out what broke.
- **Replay** — re-run a failed exchange. **Repush** — re-send the data or file from the source.
- **Change record (CHG)** — the log of planned changes to systems.
- **CMDB** — the inventory of systems and their names.

### Terms on the AI screen

- **First symptom** — the earliest event that belongs to the incident, including precursors such as a restart or a memory climb.
- **Observed timeline (FACT)** — assembled by code from source records; no inference.
- **Candidate causes (INFERRED)** — the model's ranked hypotheses, each with **Supports** and **Contradicts** columns.
- **Ruled out** — causes and alerts considered and dismissed, with the reason.
- **Diagnostic checks** — ordered cheapest and most decisive first.
- **Blast radius** — which flows and systems are affected, populated from observed data.
- **Recovery, behind the gate** — a proposed action that nothing executes until a named person approves and the approval is logged.

---

## Part 2 — "We already have 300–400 rules. What does AI add?"

### The core distinction

Rules **detect**: "this number crossed a threshold", "this error text appeared." AI **explains**: "these 30 alerts are one problem, here is the likely cause, here is what argues against it, here is what to check first." Rules answer *what is wrong*. Nobody has automated *why*.

### Evidence from the client's own data (June–August 2026)

- **3,118 incidents.** 41% were raised automatically — the alerting works.
- **868 `[AUTO]` HIPMON tickets across 190 different half-flows.**
- **12.5% of incidents are linked duplicates** of another ticket: one event regularly produces several tickets.
- **Median open-to-resolve was 6.6 hours** for auto-raised incidents. This measures the ticket's whole life, not pure diagnosis time, so quote it as "tickets stay open 6.6 hours", not "diagnosis takes 6.6 hours."
- **25% of classified closes were a replay.** The fix is often simple once someone knows what to replay.

Detection is good and resolution still takes hours. That gap is diagnosis.

### What rules structurally cannot do

1. **Correlate across systems.** Each rule watches one thing. In the S5 demo, 30+ correct alerts and six tickets came from a single cache restart 35 minutes earlier that no rule watched.
2. **Notice absence.** In S4 an exchange sits INPROGRESS for five hours and no rule fires. In S2 nothing arrives at all, and the only rule fires after 60 minutes.
3. **Read unstructured text.** A vendor release notice, or a ticket's free text, is not something a threshold can read.
4. **Cover novel combinations.** Someone must have predicted a pattern to write its rule. AI reasons about combinations nobody anticipated.
5. **Say what argues against a conclusion.** Every cause in the demo lists evidence for and against it.
6. **Propose ordered next steps** and draft the ticket note in the existing `#01–#04` close-note format.

### What AI does not do

Say this openly; it builds trust.

- It **does not replace or remove any rule**, and it does not reduce rule maintenance. The 400 rules are its input.
- It **does not act on its own.** A named person must approve every recovery action, and the approval is logged.
- It **can be wrong.** The build saw a weaker answer on one run; the guardrails exist because of that (see `FINDINGS.md`).
- It depends on **signal quality**: consistent exchange IDs, timestamps and system naming.

### The honest limit of what has been shown

The demo uses **synthetic incidents patterned on the real data**, not replays of real incidents. Accuracy on real incidents has not been measured yet.

### The pitch, in three lines

1. *"Your 400 rules are the sensors. This is the analyst."*
2. *"Detection is solved and working; diagnosis is where the hours go, and rules cannot do it."*
3. *"Give us one real past P1 and we will run it. It costs nothing and needs no production access."*

The three-month export contains **27 Critical or Major incidents** with written root causes — a ready-made test set.

### One question that usually settles it

*"On your last cross-system P1, how long was it between the first alert and everyone agreeing on the cause?"*

### Likely objections

| Objection | Answer |
| --- | --- |
| "We already have 400 rules." | Agree. They are the input. This does not replace them; it explains what they collectively mean. |
| "Why not write correlation rules?" | Someone has to anticipate each pattern first. Correlation rules cover known combinations; incidents are usually new ones. |
| "Can we trust an AI?" | It cannot execute anything. It cites evidence for and against, and a named person approves. The facts panel is assembled by code from source records. |
| "This is synthetic data." | Yes, deliberately, built from your own error strings, naming and recovery patterns. Give us one real past P1 and we will run it. |
| "Does this cut rule maintenance?" | No, and we will not claim it does. It changes what happens after rules fire. |
