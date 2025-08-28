import time
import httpx

BASE_URL = "http://localhost:8000"


def wait_for_status(job_id, expected, timeout=5.0):
    """Poll /v1/jobs/{id} until status in expected or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        r = httpx.get(f"{BASE_URL}/v1/jobs/{job_id}")
        if r.status_code == 200 and r.json()["status"] in expected:
            return r.json()
        time.sleep(0.5)
    raise AssertionError(f"Job {job_id} did not reach {expected} in {timeout}s")


def test_submit_and_status_roundtrip():
    # Simulate hashing a network payload (e.g., a packet string)
    packet = {
        "src_ip": "10.0.0.5",
        "dst_ip": "10.0.0.200",
        "src_port": 44321,
        "dst_port": 443,
        "protocol": "tcp",
        "payload": "GET /login HTTP/1.1",
    }

    create = httpx.post(
        f"{BASE_URL}/v1/jobs",
        json={"type": "hash", "payload": {"data": str(packet)}},
    )
    assert create.status_code == 200
    job_id = create.json()["jobId"]

    result = wait_for_status(job_id, ["SUCCEEDED"], timeout=5.0)
    assert result["status"] == "SUCCEEDED"
    assert "completedAt" in result


def test_jobs_lists_recent_first():
    ids = []
    packets = [
        {
            "src_ip": f"10.0.0.{i}",
            "dst_ip": "10.0.0.200",
            "src_port": 10000 + i,
            "dst_port": 443,
            "protocol": "tcp",
            "payload": f"Packet {i} - SYN",
        }
        for i in range(3)
    ]

    for pkt in packets:
        r = httpx.post(
            f"{BASE_URL}/v1/jobs",
            json={"type": "hash", "payload": {"data": str(pkt)}},
        )
        assert r.status_code == 200
        ids.append(r.json()["jobId"])

    # wait for last job to succeed
    wait_for_status(ids[-1], ["SUCCEEDED"], timeout=5.0)

    list_resp = httpx.get(f"{BASE_URL}/v1/jobs")
    assert list_resp.status_code == 200
    jobs = list_resp.json()
    assert jobs[0]["id"] == ids[-1]  # most recent first