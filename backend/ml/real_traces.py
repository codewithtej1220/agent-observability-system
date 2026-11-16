"""Real agent runs for training and evaluation: SWE-agent trajectories.

Source: nebius/SWE-agent-trajectories on Hugging Face (CC BY 4.0). Real runs of
SWE-agent (Llama-based models) trying to resolve GitHub issues. Every turn, the
model issues one shell or editor command and the environment answers.
`target` says whether the issue was actually resolved; `exit_status` says how
the run ended (e.g. it ran out of context budget).

Each trajectory becomes a `Run`:
  * an assistant turn with a command  -> tool_call (tool = the command's name)
  * the command `submit`              -> final_answer
  * an assistant turn without one     -> llm (reasoning only)
  * the next environment message      -> that step's output; error patterns
                                         ("command not found", ...) -> status=error
Token counts are estimated from text length (the dataset has none) and
latency is unknown (0).

Labels come from what actually happened in the run, with the step where it
started (`failure_onset`):
  hallucinated_tool  the agent ran a command that does not exist (the
                     environment answered "command not found")
  loop               the same command, character for character, 3 times in a row
  tool_thrashing     10+ consecutive navigation/search commands across 4+ tools
                     with no edit or execution, in a run that failed
  token_waste        the run exhausted its context/cost budget without
                     resolving the issue
  healthy            the issue was resolved and none of the above happened
Failed runs with none of these patterns are left unlabeled and not used.
These are weak labels: they describe observable behavior, not a human's
judgment. Human labels from the review queue are added on top and weighted
higher.

Splits are by GitHub issue, so runs of the same issue (by different models)
never end up in both training and test data.
"""
from __future__ import annotations

import hashlib
import logging
import pickle
import random
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .schema import Run, Step

log = logging.getLogger(__name__)

DATASET = "nebius/SWE-agent-trajectories"
LICENSE = "CC BY 4.0"
SHARDS = ["data/train-00000-of-00012.parquet", "data/train-00001-of-00012.parquet"]
CACHE_VERSION = 2
MAX_STEPS = 120

COMMAND_RE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.S)
TOOL_RE = re.compile(r"[A-Za-z0-9_./-]+")
ERROR_PATTERNS = re.compile(
    r"command not found|No such file or directory|Your proposed edit has introduced new syntax error|"
    r"^Usage: |^Error: |is not a valid|Permission denied", re.M)
NAVIGATION = {"open", "goto", "scroll_up", "scroll_down", "search_dir", "search_file", "find_file", "find", "grep",
              "ls", "cd", "cat", "pwd", "next_match"}
PROGRESS = {"edit", "create", "python", "pytest", "submit", "rm", "mv", "pip", "./reproduce.sh"}


def _command(text: str) -> Optional[str]:
    blocks = COMMAND_RE.findall(text or "")
    return blocks[-1].strip() if blocks else None


def _tool_and_args(cmd: str) -> Tuple[str, Dict]:
    first = cmd.splitlines()[0].strip()
    m = TOOL_RE.match(first)
    tool = m.group(0) if m else "invalid"
    rest = first[len(tool):].strip()
    return tool, ({"args": rest[:300]} if rest else {})


def _est(text: str) -> int:
    return max(1, len(text or "") // 4)


def to_run(row: Dict) -> Tuple[Run, Optional[str], Optional[int]]:
    """One dataset row -> (Run, label or None, onset step or None)."""
    traj = row["trajectory"]
    system = next((m.get("system_prompt") or "" for m in traj if m["role"] == "system"), "")
    issue = next((m.get("text") or "" for m in traj if m["role"] == "user"), "")
    task = next((ln.strip() for ln in issue.splitlines() if ln.strip() and not ln.startswith("We're currently")), "")
    if task.upper().startswith("ISSUE:"):
        task = next((ln.strip() for ln in issue.split("ISSUE:", 1)[1].splitlines() if ln.strip()), task)

    steps: List[Step] = []
    commands: List[Optional[str]] = []
    base_ctx = _est(system) + _est(issue)
    recent: List[int] = []
    msgs = [m for m in traj if m["role"] in ("ai", "user")][1:]  # drop the issue itself
    i = 0
    while i < len(msgs) and len(steps) < MAX_STEPS:
        m = msgs[i]
        if m["role"] != "ai":
            i += 1
            continue
        text = m.get("text") or ""
        obs = msgs[i + 1].get("text") or "" if i + 1 < len(msgs) and msgs[i + 1]["role"] == "user" else ""
        cmd = _command(text)
        out_tok = _est(text)
        in_tok = base_ctx + sum(recent[-10:])
        idx = len(steps)
        if cmd is None:
            steps.append(Step(idx, "llm", output=text[:2000], input_tokens=in_tok, output_tokens=out_tok))
        else:
            tool, args = _tool_and_args(cmd)
            if tool == "submit":
                steps.append(Step(idx, "final_answer", output=obs[:2000], input_tokens=in_tok, output_tokens=out_tok))
            else:
                status = "error" if ERROR_PATTERNS.search(obs[:3000]) else "ok"
                steps.append(Step(idx, "tool_call", tool_name=tool, arguments=args, output=obs[:2000], status=status,
                                  input_tokens=in_tok, output_tokens=out_tok))
        commands.append(cmd)
        recent += [out_tok, _est(obs)]
        i += 2 if obs else 1

    # Several attempts per issue and model exist, so the id hashes the agent's own turns too.
    sig = "".join(m.get("text") or "" for m in traj if m["role"] == "ai")
    run = Run(run_id="swe-" + hashlib.sha1(f"{row['instance_id']}|{row['model_name']}|{sig}".encode()).hexdigest()[:24],
              agent_id=row["model_name"], steps=steps, task=task[:300], model=row["model_name"])
    label, onset = label_run(run, commands, bool(row["target"]), row.get("exit_status") or "")
    run.source_label, run.failure_onset = label, onset
    return run, label, onset


def label_run(run: Run, commands: Sequence[Optional[str]], resolved: bool, exit_status: str):
    found: List[Tuple[int, int, str]] = []  # (onset, priority, label)
    for s in run.steps:
        if s.type == "tool_call" and "command not found" in s.output[:500]:
            found.append((s.index, 0, "hallucinated_tool"))
            break
    # A loop repeats the same command and gets the same answer: no new information.
    # (Scrolling three times is the same command but shows new lines each time.)
    seen = [(c, s.output[:1000]) for c, s in zip(commands, run.steps)]
    for k in range(len(seen) - 2):
        if seen[k][0] and seen[k] == seen[k + 1] == seen[k + 2]:
            found.append((k, 1, "loop"))
            break
    if not resolved:
        streak_start, tools = None, []
        for s in run.steps:
            nav = s.type == "tool_call" and s.tool_name in NAVIGATION
            if nav:
                streak_start = s.index if streak_start is None else streak_start
                tools.append(s.tool_name)
                if s.index - streak_start + 1 >= 10 and len(set(tools)) >= 4:
                    found.append((streak_start + 5, 2, "tool_thrashing"))
                    break
            else:
                streak_start, tools = None, []
        if "exit_context" in exit_status or "exit_cost" in exit_status:
            found.append((max(1, int(len(run.steps) * 0.6)), 3, "token_waste"))
    if found:
        onset, _, label = min(found)
        return label, onset
    return ("healthy", None) if resolved else (None, None)


# --------------------------------------------------------------------------- loading
def data_dir(base: Path) -> Path:
    return base / "real_traces"


def shard_paths(base: Path) -> List[Path]:
    return [data_dir(base) / Path(s).name for s in SHARDS]


def available(base: Path) -> bool:
    return all(p.exists() for p in shard_paths(base))


def load_runs(base: Path) -> List[Run]:
    """All labeled runs from the downloaded shards (cached after the first parse)."""
    paths = shard_paths(base)
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"Real agent traces not found ({', '.join(missing)}). Download them with: python -m scripts.fetch_real_traces")
    key = hashlib.sha1(repr([(p.name, p.stat().st_size, CACHE_VERSION, MAX_STEPS) for p in paths]).encode()).hexdigest()[:12]
    cache = data_dir(base) / f"runs-{key}.pkl"
    if cache.exists():
        with open(cache, "rb") as f:
            return pickle.load(f)

    import polars as pl  # local: only needed when (re)building the cache

    runs: List[Run] = []
    counts: Counter = Counter()
    for p in paths:
        df = pl.read_parquet(p, columns=["instance_id", "model_name", "target", "exit_status", "trajectory"])
        for row in df.iter_rows(named=True):
            run, label, _ = to_run(row)
            counts[label] += 1
            if label is not None and run.steps:
                run.task = run.task or row["instance_id"]
                run.issue = row["instance_id"]  # used for the split, not a model input
                runs.append(run)
    log.info("Real traces: %s", dict(counts))
    with open(cache, "wb") as f:
        pickle.dump(runs, f)
    return runs


def _bucket(run: Run) -> int:
    return int(hashlib.sha1(getattr(run, "issue", run.run_id).encode()).hexdigest(), 16) % 10


def splits(base: Path, n_train: int = 3000, n_val: int = 800, n_test: int = 1500,
           seed: int = 7) -> Tuple[List[Run], List[Run], List[Run]]:
    """Train / validation / test, split by GitHub issue (70 / 10 / 20), then sampled.

    Training is class-balanced where the data allows (minority classes kept in
    full); validation and test keep the real class mix.
    """
    runs = load_runs(base)
    rng = random.Random(seed)
    train = [r for r in runs if _bucket(r) < 7]
    val = [r for r in runs if _bucket(r) == 7]
    test = [r for r in runs if _bucket(r) >= 8]

    by_label: Dict[str, List[Run]] = {}
    for r in train:
        by_label.setdefault(r.source_label, []).append(r)
    per_class = n_train // max(1, len(by_label))
    picked: List[Run] = []
    for label, rs in sorted(by_label.items()):
        rng.shuffle(rs)
        picked += rs[:per_class]
    chosen = {r.run_id for r in picked}
    rest = [r for r in train if r.run_id not in chosen]
    rng.shuffle(rest)
    picked += rest[: max(0, n_train - len(picked))]
    rng.shuffle(val)
    rng.shuffle(test)
    return picked, val[:n_val], test[:n_test]


def summary(runs: Sequence[Run]) -> Dict[str, int]:
    return dict(Counter(r.source_label for r in runs))
