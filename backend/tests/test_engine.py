from ml import CLASSES
from ml.simulator import generate_dataset
from ml.training import evaluate, prefix_label


def test_assessment_shape(small_engine, make_run):
    a = small_engine.assess(make_run("healthy"))
    assert set(a["probabilities"]) == set(CLASSES)
    assert abs(sum(a["probabilities"].values()) - 1) < 1e-3
    assert 0 <= a["risk_score"] <= 1
    assert a["severity"] in ("healthy", "warning", "critical")
    assert len(a["coords"]) == 2


def test_hallucination_is_flagged(small_engine, make_run):
    a = small_engine.assess(make_run("hallucinated_tool", agent="travel-planner", seed=5))
    assert a["severity"] != "healthy"
    assert a["failure_type"] == "hallucinated_tool"


def test_batched_trajectories_match_single(small_engine, make_run):
    runs = [make_run("loop", seed=1), make_run("healthy", seed=2)]
    batched = small_engine.trajectories(runs)
    for run, tr in zip(runs, batched):
        single = small_engine.trajectory(run)
        assert single["first_flag_step"] == tr["first_flag_step"]
        assert len(tr["risk"]) == len(run.steps)


def test_prefix_labels_respect_onset(make_run):
    run = make_run("loop", seed=4)
    assert prefix_label(run, run.failure_onset) == "healthy"
    assert prefix_label(run, len(run.steps)) == "loop"


def test_held_out_quality(small_engine):
    m = evaluate(small_engine, generate_dataset(300, seed=99, failure_scale=1.5))
    fused = next(c for c in m["approach_comparison"] if c["approach"] == "Fused engine")
    assert fused["roc_auc"] > 0.9
    assert m["binary"]["recall"] > 0.8
    assert m["early_detection"]["detected_rate"] > 0.8
