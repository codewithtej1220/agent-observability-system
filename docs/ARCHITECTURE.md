# Architecture and design decisions

## What changed from v1, and why

| v1 | Problem | v2 |
|---|---|---|
| "Real data" loader trained on `facebook/xlsum` (news summarization) with synthetic labels attached | Not agent traces; reported metrics measured nothing | Explicit simulator of agent traffic with ground truth, failure onset, and hard negatives. Real traffic flows in through the SDK and labels come from the review queue. |
| Single anomaly score from hashed text n-grams + numeric features | Couldn't say *which* failure, and text hashing is mostly noise for behavioral failures | Behavioral features (repetition, cycles, novelty, spend vs agent baseline) + per-type rule detectors + failure-type classifier |
| Scored only completed traces | Too late: the tokens are already spent | Step-level streaming; the classifier is trained on run prefixes and alerts 1–2 steps after onset |
| HDBSCAN prediction via centroid distance | Centroids misrepresent density-based clusters | HDBSCAN used for archetype discovery; novelty from k-NN distance + IsolationForest, calibrated to percentiles of normal traffic |
| Bandit context = mean / std / max of the embedding vector | Context carries no information about the failure, so the policy can't learn per-failure actions | Context = detection output (risk, per-type probabilities, rule severity, novelty, run length, relative spend); guardrails; offline warm start; outcome-based reward |
| "Supervised learning" = the same bandit update | No supervised model existed | Gradient-boosted classifier retrained from human labels, with versioning and a no-regression promotion rule |
| Postgres required; hard-coded API keys; three-dimensional animated dashboard | Hard to run, insecure defaults, visual noise | SQLite by default (Postgres via env); keys from env; plain operational dashboard |

## Data model

A **run** is an ordered list of **steps**. A step is one agent iteration:

| field | |
|---|---|
| `type` | `tool_call`, `llm` (reasoning without a tool) or `final_answer` |
| `tool_name`, `arguments`, `output`, `status` | what was called and what came back (`ok`/`error`) |
| `input_tokens`, `output_tokens`, `latency_ms` | cost signals; input tokens grow as context accumulates |

Tables: `agents` (with optional tool registry), `runs` (totals + latest assessment + decision),
`steps`, `feedback` (label, action, outcome, reward), `model_versions`, `policy_events`.

## Detection

### Behavioral features (`ml/features.py`)

All 29 features are computable on any prefix of a run. Highlights:

- **Repetition**: longest identical tool+argument streak, share of exact repeats, near-duplicate
  arguments (string similarity ≥ 0.8), repeating tool cycles of period ≤ 3 at the end of the run.
- **Progress**: novelty of each output, measured as the share of *word bigrams* never seen
  earlier in the run. Bigrams avoid penalizing ordinary word reuse while a repeated or restated
  output contributes almost nothing new. `stall_steps` counts steps since output last added
  information.
- **Errors**: error ratio, longest error streak, recent error ratio.
- **Tool validity**: calls to tools outside the agent's registry (or, without a registry,
  outside the tools seen succeeding in its history).
- **Spend**: tokens and steps relative to *this agent's* median, plus new information per 100
  tokens. Agents have very different normal costs; absolute thresholds would misfire.

### Rules (`ml/detectors.py`)

Rules are intentionally conservative and always attach the step indexes that triggered them.
They also feed the classifier as inputs, so it can learn when a rule fires on benign patterns
(polling a job looks exactly like an identical-call loop for the first few steps).

### Fusion (`ml/engine.py`)

1. `risk = logistic(p_failure, max_rule_severity, novelty)` with weights fit on validation prefixes.
2. **Open-set gate**: if rule severity ≥ r and novelty ≥ n, risk ≥ 0.5 regardless of the classifier.
   (r, n) are chosen on validation data to maximize recall with FPR ≤ 1.5%.
3. **Exact floor**: unregistered tool calls set risk ≥ 0.5 (one call) or ≥ 0.75 (several).

Severity: healthy < 0.35 ≤ warning < 0.7 ≤ critical.

The leave-one-failure-type-out study in `ml/training.py` is the evidence for steps 2–3: without
them, unseen loops and hallucinated tools are detected only 17% and 37% of the time; with them,
59% and 100%, at about 1% FPR (see the table in the README for all four types).

## Intervention policy (`ml/bandit.py`)

Disjoint LinUCB, one ridge model per action, inverse maintained with Sherman–Morrison.

- **Context** (10-d): bias, risk, p(loop), p(thrashing), p(hallucination), p(token waste),
  rule severity, novelty, run length, relative spend.
- **Reward**: +1 if the run ultimately succeeded, minus the intervention's cost (human time,
  stronger-model spend); −0.3 if a failing run was allowed to fail; terminating a failing run
  earns +0.35 (it caps waste); terminating a healthy run costs −0.6.
- **Guardrails**: below the warning threshold the action is always `continue`; at critical,
  `continue` is not allowed. Exploration never overrides these.
- **Warm start**: 4,000 simulated decisions against an assumed outcome model, so the policy
  starts sensible. Live rewards from reviews keep updating it, and its state is written to
  disk after every update.

## Learning loop

```
review submitted ──► reward ──► policy.update()  (immediate, persisted)
                └──► label  ──► stored; after N labels (or on demand) retrain:
                                  simulated reference data + human labels (3x weight)
                                  → evaluate on held-out set
                                  → promote only if macro-F1 ≥ active − 0.02
```

## Evaluation protocol

- Train / validation / test are generated with fixed, distinct seeds; the test set has a
  higher failure rate (×1.5) so per-class metrics have support.
- Validation is used only for fusion weights and the open-set gate.
- Early detection is measured per failing test run as `first_alert_step − failure_onset`.
- "Healthy ever alerted" counts healthy runs that crossed the warning threshold at *any*
  step. It is the honest measure of alert noise for a streaming system.

## Known limitations

- The simulator is a model of reality, not reality. It exists so the pipeline can be built,
  tested and evaluated before labeled production data exists.
- Lexical novelty misses paraphrased repetition; sentence embeddings would help.
- The single-process API holds the models in memory. For horizontal scaling, load the active
  version per worker and move policy updates to a single writer (or a shared store).
