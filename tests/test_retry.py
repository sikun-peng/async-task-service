import time
import pytest
from app.retry import retry_with_jitter


def test_retry_succeeds_before_cap(monkeypatch):
    # skip actual sleeping to make test run fast
    monkeypatch.setattr(time, "sleep", lambda s: None)

    attempts = {"count": 0}

    def flaky_request():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ConnectionError("Packet dropped")
        return "ACK"

    wrapped = retry_with_jitter(max_attempts=5, base_delay=0.1)(flaky_request)
    assert wrapped() == "ACK"
    assert attempts["count"] == 3


def test_retry_reraises_on_final_attempt(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)

    attempts = {"count": 0}

    def always_bad_request():
        attempts["count"] += 1
        raise TimeoutError("Network timeout")

    wrapped = retry_with_jitter(
        max_attempts=3,
        base_delay=0.1,
        exceptions=(TimeoutError,)
    )(always_bad_request)

    with pytest.raises(TimeoutError):
        wrapped()
    assert attempts["count"] == 3


def test_on_retry_callback_receives_attempt_and_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)

    # deterministically return upper bound for jitter
    def fake_uniform(a, b):
        return b

    monkeypatch.setattr("app.retry.random.uniform", fake_uniform)

    seen = []

    def cb(attempt, err, sleep_s):
        seen.append((attempt, type(err).__name__, sleep_s))

    attempts = {"count": 0}

    def flaky_request():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise ConnectionError("Transient drop")
        return "ACK"

    wrapped = retry_with_jitter(
        max_attempts=5,
        base_delay=0.2,
        on_retry=cb
    )(flaky_request)

    assert wrapped() == "ACK"
    assert len(seen) == 1
    assert seen[0][0] == 1
    assert seen[0][1] == "ConnectionError"
    assert seen[0][2] >= 0.2 * (1 - 0.5)  # lower bound with jitter ratio


def test_non_matching_exception_is_not_retried(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)

    attempts = {"count": 0}

    def bad_request():
        attempts["count"] += 1
        raise KeyError("Unexpected response")

    wrapped = retry_with_jitter(
        max_attempts=5,
        exceptions=(ConnectionError,)
    )(bad_request)

    with pytest.raises(KeyError):
        wrapped()
    assert attempts["count"] == 1


def test_jitter_bounds(monkeypatch):
    samples = []

    def fake_uniform(a, b):
        samples.append((a, b))
        return a  # lower bound for determinism

    monkeypatch.setattr("app.retry.random.uniform", fake_uniform)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    attempts = {"count": 0}

    def flaky_request():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ConnectionError("Packet lost")
        return "ACK"

    wrapped = retry_with_jitter(
        max_attempts=5,
        base_delay=0.5,
        backoff=2.0,
        jitter_ratio=0.4
    )(flaky_request)

    assert wrapped() == "ACK"

    # Two retries happened → check jitter bounds
    # attempt=1 → base_delay=0.5, bounds [0.3, 0.7]
    # attempt=2 → base_delay=1.0, bounds [0.6, 1.4]
    assert samples[0] == (0.5 * (1 - 0.4), 0.5 * (1 + 0.4))
    assert samples[1] == (1.0 * (1 - 0.4), 1.0 * (1 + 0.4))