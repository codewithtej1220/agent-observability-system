"""Conversion and labeling of real SWE-agent trajectories (ml/real_traces.py)."""
from ml.bandit import MIN_LEARNED_UPDATES, STATIC_PLAYBOOK, LinUCBPolicy, build_context
from ml.real_traces import to_run

SYSTEM = {"role": "system", "system_prompt": "SETTING: You are an autonomous programmer...", "text": None}
ISSUE = {"role": "user", "system_prompt": None,
         "text": "We're currently solving the following issue within our repository. Here's the issue text:\nISSUE:\nCrash on empty config\n"}


def _turn(command, observation, thought="Let's look."):
    return [{"role": "ai", "system_prompt": None, "text": f"{thought}\n```\n{command}\n```"},
            {"role": "user", "system_prompt": None, "text": observation}]


def _row(turns, target=False, exit_status="submitted", model="swe-agent-llama-70b"):
    traj = [SYSTEM, ISSUE] + [m for t in turns for m in t]
    return {"instance_id": "acme__widgets-42", "model_name": model, "target": target, "exit_status": exit_status,
            "trajectory": traj}


def test_steps_tools_and_errors():
    run, label, onset = to_run(_row([
        _turn("find_file config.py", "Found 1 matches for \"config.py\""),
        _turn("open src/config.py", "[File: src/config.py (40 lines total)]\n1:import os"),
        _turn("frobnicate --all", "/bin/bash: line 1: frobnicate: command not found"),
        _turn("edit 3:3\n    return {}\nend_of_edit", "File updated."),
        _turn("submit", "diff --git a/src/config.py b/src/config.py"),
    ], target=True))
    assert run.agent_id == "swe-agent-llama-70b" and run.task == "Crash on empty config"
    assert [s.type for s in run.steps] == ["tool_call"] * 4 + ["final_answer"]
    assert [s.tool_name for s in run.steps[:4]] == ["find_file", "open", "frobnicate", "edit"]
    assert run.steps[0].arguments == {"args": "config.py"} and run.steps[3].arguments == {"args": "3:3"}
    assert run.steps[2].status == "error" and run.steps[1].status == "ok"
    assert run.steps[1].input_tokens > run.steps[0].input_tokens  # context grows
    # A resolved run that still called a non-existent command is labeled by that behavior.
    assert (label, onset) == ("hallucinated_tool", 2)


def test_resolved_clean_run_is_healthy():
    _, label, onset = to_run(_row([_turn("open a.py", "[File: a.py]"), _turn("submit", "diff")], target=True))
    assert (label, onset) == ("healthy", None)


def test_loop_needs_same_command_and_same_output():
    top = "[File: a.py (90 lines total)]\n1:import os"
    _, label, onset = to_run(_row([_turn("open a.py", top)] + [_turn("scroll_up", top)] * 3))
    assert (label, onset) == ("loop", 1)
    # Scrolling that shows new lines each time is navigation, not a loop.
    _, label, _ = to_run(_row([_turn("scroll_down", f"[File: a.py]\n{i * 100}:line") for i in range(3)], target=True))
    assert label == "healthy"


def test_budget_exhausted_without_fix_is_token_waste():
    turns = [_turn(f"open file{i}.py", f"[File: file{i}.py]") for i in range(4)]
    turns += [_turn("python reproduce.py", f"output {i}") for i in range(6)]
    _, label, onset = to_run(_row(turns, target=False, exit_status="submitted (exit_context)"))
    assert label == "token_waste" and onset == 6


def test_navigation_without_progress_is_tool_thrashing():
    nav = ["open a.py", "search_file foo", "goto 30", "find_file b.py", "open b.py", "scroll_down",
           "search_dir bar", "goto 10", "open c.py", "search_file baz", "scroll_down"]
    _, label, onset = to_run(_row([_turn(c, f"view {i}") for i, c in enumerate(nav)], target=False))
    assert (label, onset) == ("tool_thrashing", 5)


def test_failed_run_without_a_pattern_is_unlabeled():
    _, label, _ = to_run(_row([_turn("open a.py", "[File: a.py]"), _turn("submit", "diff")], target=False))
    assert label is None


def test_policy_follows_playbook_until_enough_real_outcomes():
    p = LinUCBPolicy()
    a = {"risk_score": 0.8, "failure_type": "token_waste", "probabilities": {"token_waste": 0.9}, "rule_severity": 0.5,
         "novelty_score": 0.1, "n_steps": 12, "tokens_vs_baseline": 3.0}
    d = p.decide(a)
    assert d.action == STATIC_PLAYBOOK["token_waste"] and d.by_policy and "Playbook" in d.reason
    for _ in range(MIN_LEARNED_UPDATES):
        p.update(build_context(a), "reflect", 1.0)
    assert "Playbook" not in p.decide(a).reason
