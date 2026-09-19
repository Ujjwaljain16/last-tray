"""The orchestrator's own logic, tested with fake stages: order, gates, failure propagation, stale-output cleanup, resume, exit classes.

No business logic is exercised here; the real stages are covered by test_pipeline_real.py.
"""
from __future__ import annotations

import pytest

from src.pipeline.exit_codes import EXIT_TABLE, STAGE_EXIT, ExitCode
from src.pipeline.orchestrate import (BLOCKED, FAILED, INVALIDATED, NOT_RUN, PASSED, REUSED, OrchestrationError, RunLogger, run_pipeline, validate_order)
from src.pipeline.stages import STAGE_ORDER, Context, StageReport, StageSpec, _cleaner


class Fake:
    """Six fake stages that each write one file into out/<name>/ so cleanup and fingerprints are real."""

    def __init__(self, out, *, fail=(), boom=(), weather=(), content="v1"):
        self.out, self.calls, self.fail, self.boom, self.weather, self.content = out, [], set(fail), set(boom), set(weather), content

    def spec(self, name: str) -> StageSpec:
        def run(ctx: Context) -> StageReport:
            self.calls.append(name)
            if name in self.boom:
                raise RuntimeError(f"{name} exploded")
            if name in self.fail:
                return StageReport(FAILED, f"{name} refused", console=f"{name} FAILED")
            d = ctx.out / name
            d.mkdir(parents=True, exist_ok=True)
            (d / "f.txt").write_text(f"{name}:{self.content}", encoding="utf-8")
            return StageReport(PASSED, weather_blocked=name in self.weather, counts={"rows": 1}, console=f"{name} ok")

        return StageSpec(name, run, _cleaner(name, ("f.txt",)), lambda out, n=name: [p for p in [out / n / "f.txt"] if p.is_file()], f"upstream of {name}")

    def specs(self, order=STAGE_ORDER):
        return tuple(self.spec(n) for n in order)

    def go(self, **kw):
        kw.setdefault("target", "sensitivity")
        return run_pipeline(self.specs(), Context(None, self.out, self.out), run_id="run-test", **kw)  # type: ignore[arg-type]


def status(res):
    return {s.name: s.status for s in res.stages}


def test_stages_run_in_the_documented_order(tmp_path):
    f = Fake(tmp_path)
    res = f.go()
    assert f.calls == list(STAGE_ORDER) == ["ingest", "stage", "validate", "model", "metrics", "sensitivity"]
    assert res.exit_code == 0 and all(s == PASSED for s in status(res).values())


@pytest.mark.parametrize("order", [tuple(reversed(STAGE_ORDER)), ("stage", "ingest", *STAGE_ORDER[2:]), STAGE_ORDER[:-1], (*STAGE_ORDER, "extra")])
def test_a_wrong_stage_order_or_set_is_refused_before_anything_runs(tmp_path, order):
    f = Fake(tmp_path)
    with pytest.raises(OrchestrationError):
        run_pipeline(tuple(f.spec(n) for n in order if n != "extra") if "extra" not in order else tuple(f.spec(n) for n in STAGE_ORDER[:1]) + (f.spec("stage"),) * 6,
                     Context(None, tmp_path, tmp_path), target="sensitivity", run_id="r")  # type: ignore[arg-type]
    assert f.calls == []


def test_validate_order_accepts_only_the_exact_sequence(tmp_path):
    f = Fake(tmp_path)
    validate_order(f.specs())
    with pytest.raises(OrchestrationError):
        validate_order(f.specs()[::-1])


@pytest.mark.parametrize("failing", STAGE_ORDER)
def test_a_failed_stage_blocks_every_later_stage_and_returns_its_own_exit_class(tmp_path, failing):
    assert Fake(tmp_path).go().exit_code == 0                           # every stage has current outputs before the failure
    f2 = Fake(tmp_path, fail=[failing])
    res = f2.go()
    i = STAGE_ORDER.index(failing)
    assert f2.calls == list(STAGE_ORDER[: i + 1]), "no stage after the failure may run"
    st = status(res)
    assert st[failing] == FAILED
    assert all(st[n] == PASSED for n in STAGE_ORDER[:i])
    assert all(st[n] == BLOCKED for n in STAGE_ORDER[i + 1:])
    assert res.exit_code == int(STAGE_EXIT[failing]) == res.first_failure.exit_class
    for n in STAGE_ORDER[i + 1:]:
        assert not (tmp_path / n / "f.txt").exists(), f"stale {n} output survived a failed {failing}"
    for n in STAGE_ORDER[:i]:
        assert (tmp_path / n / "f.txt").is_file(), f"upstream {n} output must be untouched by a later failure"


def test_stale_outputs_are_removed_even_for_stages_the_run_would_not_have_reached(tmp_path):
    Fake(tmp_path).go()
    f = Fake(tmp_path, fail=["ingest"])
    res = f.go(target="stage")                                          # only asked for stage; ingest fails; sensitivity outputs are still stale
    assert not any((tmp_path / n / "f.txt").exists() for n in STAGE_ORDER[1:])
    assert status(res)["sensitivity"] == BLOCKED and res.exit_code == int(ExitCode.SOURCE)


def test_an_unexpected_exception_is_an_orchestration_failure_and_removes_that_stage_outputs(tmp_path):
    Fake(tmp_path).go()
    f = Fake(tmp_path, boom=["model"])
    res = f.go()
    assert res.exit_code == int(ExitCode.ORCHESTRATION) == 11
    assert status(res)["model"] == FAILED and "exploded" in res.first_failure.reason
    assert not (tmp_path / "model" / "f.txt").exists() and not (tmp_path / "metrics" / "f.txt").exists()
    assert (tmp_path / "validate" / "f.txt").is_file()


def test_the_first_failure_wins_the_exit_code(tmp_path):
    f = Fake(tmp_path, fail=["validate", "metrics"])
    res = f.go()
    assert res.exit_code == int(ExitCode.VALIDATION) and "metrics" not in f.calls


def test_a_weather_block_exits_6_without_stopping_or_hiding_anything(tmp_path):
    f = Fake(tmp_path, weather=["stage"])
    res = f.go()
    assert f.calls == list(STAGE_ORDER), "the weather lane must not close the core gate"
    assert res.exit_code == 6 and res.weather_blocked and all(s == PASSED for s in status(res).values())


def test_a_core_failure_outranks_a_weather_block(tmp_path):
    res = Fake(tmp_path, weather=["stage"], fail=["model"]).go()
    assert res.exit_code == int(ExitCode.MODEL)


def test_nothing_is_skipped_because_an_output_already_exists(tmp_path):
    Fake(tmp_path).go()
    f = Fake(tmp_path)
    f.go()
    assert f.calls == list(STAGE_ORDER), "existing outputs must never cause a stage to be skipped"


def test_resume_reuses_upstream_without_running_it_and_runs_the_rest(tmp_path):
    Fake(tmp_path).go()
    f = Fake(tmp_path)
    res = f.go(resume_from="model")
    assert f.calls == ["model", "metrics", "sensitivity"]
    st = status(res)
    assert [st[n] for n in STAGE_ORDER[:3]] == [REUSED] * 3 and [st[n] for n in STAGE_ORDER[3:]] == [PASSED] * 3
    assert res.exit_code == 0


def test_resume_failure_still_blocks_downstream_but_leaves_reused_upstream_alone(tmp_path):
    Fake(tmp_path).go()
    before = {n: (tmp_path / n / "f.txt").read_bytes() for n in STAGE_ORDER[:3]}
    f = Fake(tmp_path, fail=["model"])
    res = f.go(resume_from="model")
    assert res.exit_code == int(ExitCode.MODEL)
    assert {n: (tmp_path / n / "f.txt").read_bytes() for n in STAGE_ORDER[:3]} == before
    assert not (tmp_path / "metrics" / "f.txt").exists()


def test_resume_from_after_the_target_or_an_unknown_stage_is_refused(tmp_path):
    f = Fake(tmp_path)
    with pytest.raises(OrchestrationError):
        f.go(target="stage", resume_from="model")
    with pytest.raises(OrchestrationError):
        f.go(target="nope")
    assert f.calls == []


def test_a_partial_run_leaves_later_outputs_alone_when_upstream_is_unchanged(tmp_path):
    Fake(tmp_path).go()
    f = Fake(tmp_path)
    res = f.go(target="validate")
    st = status(res)
    assert st["model"] == st["metrics"] == st["sensitivity"] == NOT_RUN
    assert all((tmp_path / n / "f.txt").is_file() for n in STAGE_ORDER)


def test_a_partial_run_invalidates_later_outputs_when_upstream_outputs_changed(tmp_path):
    Fake(tmp_path, content="v1").go()
    res = Fake(tmp_path, content="v2").go(target="validate")
    st = status(res)
    assert st["model"] == st["metrics"] == st["sensitivity"] == INVALIDATED
    assert not any((tmp_path / n / "f.txt").exists() for n in ("model", "metrics", "sensitivity")), "outputs built on replaced upstream outputs must not survive"
    assert all((tmp_path / n / "f.txt").is_file() for n in ("ingest", "stage", "validate"))


def test_rerunning_a_later_stage_leaves_upstream_files_byte_identical(tmp_path):
    Fake(tmp_path).go()
    before = {n: ((tmp_path / n / "f.txt").read_bytes(), (tmp_path / n / "f.txt").stat().st_mtime_ns) for n in STAGE_ORDER[:4]}
    Fake(tmp_path).go(resume_from="metrics")
    assert {n: ((tmp_path / n / "f.txt").read_bytes(), (tmp_path / n / "f.txt").stat().st_mtime_ns) for n in STAGE_ORDER[:4]} == before


def test_every_stage_record_carries_its_gate_hashes_and_the_upstream_it_verifies(tmp_path):
    res = Fake(tmp_path).go()
    for prev, rec in zip([None, *res.stages], res.stages):
        assert rec.gate == ("open" if prev is None else f"{prev.name} PASSED")
        assert rec.outputs and rec.outputs[0]["sha256"] and rec.outputs[0]["bytes"] > 0 and rec.verifies


def test_logger_emits_ordered_structured_events_without_paths(tmp_path):
    f = Fake(tmp_path, fail=["model"])
    log = RunLogger("run-test")
    f.go(logger=log)
    kinds = [(e["event"], e["stage"]) for e in log.events]
    assert kinds[0] == ("run_start", None) and kinds[-1] == ("run_end", None)
    assert ("stage_end", "model") in kinds and ("stage_blocked", "metrics") in kinds and ("stage_start", "sensitivity") not in kinds
    assert all(e["run_id"] == "run-test" and "ts" in e for e in log.events)
    assert str(tmp_path) not in repr(log.events)


def test_exit_codes_are_distinct_documented_and_stage_specific():
    codes = [int(c) for c, _, _ in EXIT_TABLE]
    assert len(codes) == len(set(codes)) and set(codes) == {0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11}
    assert STAGE_EXIT["validate"] == 7 and STAGE_EXIT["model"] == 8 and STAGE_EXIT["metrics"] == 9 and STAGE_EXIT["sensitivity"] == 10
    assert STAGE_EXIT["ingest"] == STAGE_EXIT["stage"] == 4


def _recorded(out, stage):
    import hashlib
    p = out / stage / "f.txt"
    return {f"{stage}/f.txt": hashlib.sha256(p.read_bytes()).hexdigest()}


def test_a_reused_stage_matching_the_last_manifest_is_reused(tmp_path):
    Fake(tmp_path).go()
    prev = {n: _recorded(tmp_path, n) for n in STAGE_ORDER}
    f = Fake(tmp_path)
    res = f.go(resume_from="validate", previous=prev)
    assert f.calls == ["validate", "model", "metrics", "sensitivity"] and res.exit_code == 0
    assert "matches the last run manifest" in res.stages[0].gate


def test_a_reused_stage_that_differs_from_the_last_manifest_fails_with_its_own_class_and_is_removed(tmp_path):
    Fake(tmp_path).go()
    prev = {n: _recorded(tmp_path, n) for n in STAGE_ORDER}
    (tmp_path / "stage" / "f.txt").write_text("edited after the last run", encoding="utf-8")
    f = Fake(tmp_path)
    res = f.go(resume_from="validate", previous=prev)
    assert f.calls == [], "nothing may run on top of an artifact that changed since it was recorded"
    assert status(res) == {"ingest": REUSED, "stage": FAILED, "validate": BLOCKED, "model": BLOCKED, "metrics": BLOCKED, "sensitivity": BLOCKED}
    assert res.exit_code == int(STAGE_EXIT["stage"]) and "stage/f.txt" in res.first_failure.reason
    assert not (tmp_path / "stage" / "f.txt").exists() and (tmp_path / "ingest" / "f.txt").is_file()
