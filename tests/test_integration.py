# tests/test_integration.py
import time
import httpx
import pytest
import concurrent.futures
import random

BASE_URL = "http://localhost:8000"
# BASE_URL = "http://54.188.148.98:8000"

def wait_for_status(job_id, expected, timeout=5.0):
    """Poll /v1/jobs/{id} until status in expected or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        r = httpx.get(f"{BASE_URL}/v1/jobs/{job_id}")
        if r.status_code == 200 and r.json()["status"] in expected:
            return r.json()
        time.sleep(0.5)
    raise AssertionError(f"Job {job_id} did not reach {expected} in {timeout}s")


# ---------- Hash job tests ----------

@pytest.mark.integration
def test_hash_submit_success_and_complete():
    r = httpx.post(
        f"{BASE_URL}/v1/jobs",
        json={"type": "hash", "payload": {"data": "ok"}},
    )
    assert r.status_code == 200
    job_id = r.json()["jobId"]

    result = wait_for_status(job_id, ["SUCCEEDED"], timeout=5.0)
    assert result["status"] == "SUCCEEDED"
    # no result field expected, just ensure job completed
    assert "completedAt" in result


@pytest.mark.integration
def test_hash_submit_failure_and_terminal():
    r = httpx.post(
        f"{BASE_URL}/v1/jobs",
        json={"type": "hash", "payload": {"fail": True}},
    )
    assert r.status_code == 200
    job_id = r.json()["jobId"]

    result = wait_for_status(job_id, ["FAILED", "COMPENSATED"], timeout=5.0)
    assert result["status"] in ["FAILED", "COMPENSATED"]


@pytest.mark.integration
def test_hash_jobs_endpoint_lists_recent_first():
    ids = []
    for i in range(3):
        r = httpx.post(
            f"{BASE_URL}/v1/jobs",
            json={"type": "hash", "payload": {"data": f"payload-{i}"}},
        )
        assert r.status_code == 200
        ids.append(r.json()["jobId"])

    wait_for_status(ids[-1], ["SUCCEEDED", "FAILED", "COMPENSATED"], timeout=5.0)

    list_resp = httpx.get(f"{BASE_URL}/v1/jobs")
    assert list_resp.status_code == 200
    jobs = list_resp.json()
    # newest job should be first
    assert jobs[0]["id"] == ids[-1]


# ---------- Block IP job tests ----------

@pytest.mark.integration
def test_block_ip_success():
    ip = "192.168.1.123"
    r = httpx.post(
        f"{BASE_URL}/v1/jobs",
        json={"type": "block_ip", "payload": {"ip": ip, "reason": "suspicious"}},
    )
    assert r.status_code == 200
    job_id = r.json()["jobId"]

    result = wait_for_status(job_id, ["SUCCEEDED"], timeout=5.0)
    assert result["status"] == "SUCCEEDED"
    # no result payload stored, just ensure job completed
    assert "completedAt" in result


@pytest.mark.integration
def test_block_ip_missing_ip_fails():
    r = httpx.post(
        f"{BASE_URL}/v1/jobs",
        json={"type": "block_ip", "payload": {}},
    )
    # main.py validates upfront -> should be 400
    assert r.status_code == 400
    body = r.json()
    assert "block_ip requires 'ip'" in body["detail"]


@pytest.mark.integration
def test_concurrent_50_hash_jobs():
    """Submit 50 hash jobs in parallel and ensure they all complete."""
    payloads = [{"data": f"bulk-{i}-{random.randint(1,100)}"} for i in range(50)]

    job_ids = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(
                httpx.post,
                f"{BASE_URL}/v1/jobs",
                json={"type": "hash", "payload": p},
            )
            for p in payloads
        ]

        for f in futures:
            r = f.result()
            assert r.status_code == 200
            job_ids.append(r.json()["jobId"])

    # Wait for all jobs to finish
    completed = []
    for jid in job_ids:
        result = wait_for_status(jid, ["SUCCEEDED"], timeout=15.0)
        assert result["status"] == "SUCCEEDED"
        completed.append(jid)

    # Sanity check: all 50 finished
    assert len(completed) == 50