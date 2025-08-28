# tests/test_retry.py
import time
import pytest
from app.retry import retry_with_jitter


def test_retry_succeeds_before_cap(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return "ok"

    wrapped = retry_with_jitter(max_attempts=5, base_delay=0.1)(flaky)
    assert wrapped() == "ok"
    assert calls["n"] == 3


def test_retry_reraises_on_final_attempt(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)

    attempts = {"n": 0}

    def always_bad():
        attempts["n"] += 1
        raise ValueError("still bad")

    wrapped = retry_with_jitter(max_attempts=3, base_delay=0.1, exceptions=(ValueError,))(always_bad)
    with pytest.raises(ValueError):
        wrapped()
    assert attempts["n"] == 3


def test_on_retry_callback_receives_attempt_and_sleep(monkeypatch):
    # make sleep a no-op
    monkeypatch.setattr(time, "sleep", lambda s: None)

    # force jitter sampler to return upper bound deterministically
    def fake_uniform(a, b):
        return b

    monkeypatch.setattr("app.retry.random.uniform", fake_uniform)

    seen = []

    def cb(attempt, err, sleep_s):
        seen.append((attempt, type(err).__name__, sleep_s))

    count = {"n": 0}

    def flaky():
        count["n"] += 1
        if count["n"] < 2:
            raise RuntimeError("x")
        return "ok"

    wrapped = retry_with_jitter(max_attempts=5, base_delay=0.2, on_retry=cb)(flaky)
    assert wrapped() == "ok"
    # One retry happened (attempt=1)
    assert len(seen) == 1
    assert seen[0][0] == 1
    assert seen[0][1] == "RuntimeError"
    assert seen[0][2] >= 0.2 * (1 - 0.5)  # default jitter_ratio 0.5 lower bound


def test_non_matching_exception_is_not_retried(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)

    calls = {"n": 0}

    def oops():
        calls["n"] += 1
        raise KeyError("nope")

    wrapped = retry_with_jitter(max_attempts=5, exceptions=(RuntimeError,))(oops)
    with pytest.raises(KeyError):
        wrapped()
    assert calls["n"] == 1


def test_jitter_bounds(monkeypatch):
    samples = []

    def fake_uniform(a, b):
        samples.append((a, b))
        return a  # return lower bound to be deterministic

    monkeypatch.setattr("app.retry.random.uniform", fake_uniform)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    tries = {"n": 0}

    def flaky():
        tries["n"] += 1
        if tries["n"] < 3:
            raise RuntimeError("boom")
        return "ok"

    wrapped = retry_with_jitter(max_attempts=5, base_delay=0.5, backoff=2.0, jitter_ratio=0.4)(flaky)
    assert wrapped() == "ok"

    # Two retries happened; verify bounds for attempt 1 and 2
    # attempt=1: delay=0.5 * 2^(0)=0.5 -> bounds [0.3, 0.7]
    # attempt=2: delay=0.5 * 2^(1)=1.0 -> bounds [0.6, 1.4]
    assert samples[0] == (0.5 * (1 - 0.4), 0.5 * (1 + 0.4))
    assert samples[1] == (1.0 * (1 - 0.4), 1.0 * (1 + 0.4))