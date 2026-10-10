from ml.detectors import run_detectors
from ml.features import FEATURE_NAMES, feature_vector, profile_run
from ml.schema import Run, Step


def _run(steps, tools=("search", "fetch", "summarize")):
    return Run(run_id="r", agent_id="a", registered_tools=list(tools),
               steps=[Step(index=i, **s) for i, s in enumerate(steps)])


def call(tool, out="result", status="ok", **args):
    return {"type": "tool_call", "tool_name": tool, "arguments": args, "output": out, "status": status,
            "input_tokens": 500, "output_tokens": 50}


def test_feature_vector_has_all_features():
    p = profile_run(_run([call("search", q="x")]))
    assert feature_vector(p).shape == (len(FEATURE_NAMES),)


def test_identical_calls_detected_as_loop():
    run = _run([call("search", out="same answer here", q="x") for _ in range(5)])
    p = profile_run(run)
    assert p.features["max_identical_streak"] == 5
    sig = [s for s in run_detectors(p) if s.detector == "identical_calls"]
    assert sig and sig[0].severity == 1.0 and sig[0].evidence_steps == [0, 1, 2, 3, 4]


def test_two_step_cycle_without_progress():
    steps = []
    for _ in range(4):
        steps += [call("search", out="alpha beta gamma", q="x"), call("fetch", out="delta epsilon zeta", url="u")]
    p = profile_run(_run(steps))
    assert p.cycle_period == 2
    assert any(s.detector == "tool_cycle" for s in run_detectors(p))


def test_pagination_is_not_a_loop():
    steps = [call("search", out=f"page {i} result {i * 7} distinct words number{i} item{i * 3}", q="x", page=i)
             for i in range(1, 5)]
    p = profile_run(_run(steps))
    assert p.features["max_identical_streak"] == 1
    assert p.features["output_novelty"] > 0.5
    assert not any(s.failure_type == "loop" and s.severity >= 0.5 for s in run_detectors(p))


def test_unregistered_tool_is_hallucination():
    run = _run([call("search", q="x"), call("database_lookup", out="ERROR: not registered", status="error", q="y")])
    sigs = run_detectors(profile_run(run))
    hall = [s for s in sigs if s.failure_type == "hallucinated_tool"]
    assert hall and hall[0].evidence_steps == [1]


def test_known_tools_fallback_when_not_registered():
    run = Run(run_id="r", agent_id="a", steps=[Step(index=0, **call("made_up_tool"))])
    p = profile_run(run, known_tools={"search"})
    assert p.unknown_steps == [0]


def test_clean_run_has_no_signals(make_run):
    p = profile_run(make_run("healthy", seed=3))
    assert all(s.severity < 0.7 for s in run_detectors(p))


def test_simulated_failures_trigger_matching_detector(make_run):
    # The thrashing rule is deliberately conservative (it must not fire on
    # healthy multi-tool workflows); the classifier covers what it misses.
    min_hits = {"loop": 8, "hallucinated_tool": 10, "tool_thrashing": 4}
    for label, expected in min_hits.items():
        hits = 0
        for seed in range(10):
            sigs = run_detectors(profile_run(make_run(label, agent="research-agent", seed=seed)))
            hits += any(s.failure_type == label for s in sigs)
        assert hits >= expected, (label, hits)
