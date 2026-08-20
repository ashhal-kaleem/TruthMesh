"""
verify_real_api.py — Real API verification script for FactAgent.

Run this ONLY after quota reset to verify the live pipeline with real
Gemini + Serper calls. It exercises every endpoint of a running server.

Usage:
  python verify_real_api.py                         # localhost:8000
  python verify_real_api.py --base-url https://your-app.railway.app
  python verify_real_api.py --base-url http://localhost:8000 --image fact-check.png

Requirements:
  - Server must be running with a real GOOGLE_API_KEY and SERPER_API_KEY
  - No mocks; all calls are real
  - Do NOT run this during normal development or CI
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

import requests

CLAIMS = [
    {
        "claim": "The Eiffel Tower is located in Paris, France.",
        "expected_verdict": "SUPPORT",
    },
    {
        "claim": "The Great Wall of China is visible from space with the naked eye.",
        "expected_verdict": "REFUTE",
    },
    {
        "claim": "Water boils at 100 degrees Celsius at sea level.",
        "expected_verdict": "SUPPORT",
    },
]

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"


def print_section(title: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


def check_health(base_url: str) -> bool:
    print_section("Health Check")
    try:
        resp = requests.get(f"{base_url}/", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        ok = data.get("status") == "ok"
        print(f"  {PASS if ok else FAIL}  GET /  → {data}")
        return ok
    except Exception as exc:
        print(f"  {FAIL}  Cannot reach server: {exc}")
        return False


def verify_auth(base_url: str) -> Optional[str]:
    """Register + login; return JWT token or None on failure."""
    print_section("Auth: Register + Login")
    username = f"verify_user_{int(time.time())}"
    payload = {"username": username, "email": f"{username}@verify.test", "password": "Verify1234!"}

    # Register
    resp = requests.post(f"{base_url}/auth/register", json=payload, timeout=10)
    if resp.status_code != 201:
        print(f"  {FAIL}  POST /auth/register → {resp.status_code}: {resp.text}")
        return None
    token = resp.json().get("access_token")
    print(f"  {PASS}  POST /auth/register → 201, token received")

    # Login
    resp = requests.post(
        f"{base_url}/auth/login",
        json={"username": username, "password": "Verify1234!"},
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"  {FAIL}  POST /auth/login → {resp.status_code}: {resp.text}")
        return None
    print(f"  {PASS}  POST /auth/login   → 200, token received")
    return resp.json().get("access_token")


def verify_claim(
    base_url: str,
    claim: str,
    expected_verdict: str,
    token: Optional[str] = None,
    image_path: Optional[Path] = None,
) -> bool:
    print(f"\n  Claim: {claim!r}")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    data = {"claim": claim}
    files = {}

    if image_path and image_path.exists():
        files["image"] = (image_path.name, image_path.read_bytes(), "image/png")
        print(f"  Image: {image_path.name}")

    try:
        resp = requests.post(
            f"{base_url}/check_claim",
            data=data,
            files=files if files else None,
            headers=headers,
            timeout=120,   # real Gemini calls can take a while
        )
        resp.raise_for_status()
    except Exception as exc:
        print(f"  {FAIL}  Request error: {exc}")
        return False

    result = resp.json()
    verdict = result.get("verdict", "MISSING")
    confidence = result.get("confidence", -1)
    citations_count = len(result.get("evidence_citations", []))

    match = verdict == expected_verdict
    status_icon = PASS if match else FAIL
    print(f"  {status_icon}  Verdict: {verdict} (expected: {expected_verdict})")
    print(f"         Confidence: {confidence:.3f}  |  Citations: {citations_count}")
    print(f"         image_analyzed: {result.get('image_analyzed')}  |  "
          f"past_context_used: {result.get('past_context_used')}")
    return match


def verify_history(base_url: str, token: str) -> bool:
    print_section("GET /me/history")
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{base_url}/me/history", headers=headers, timeout=10)
    if resp.status_code != 200:
        print(f"  {FAIL}  → {resp.status_code}: {resp.text}")
        return False
    data = resp.json()
    print(f"  {PASS}  → {len(data)} records in history")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Real API verification script for FactAgent")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--image", default=None, help="Optional image file path to include")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    image_path = Path(args.image) if args.image else None

    print(f"\n{'='*60}")
    print(f"  FactAgent API Verification")
    print(f"  Target: {base_url}")
    print(f"{'='*60}")

    results = []

    # Health
    if not check_health(base_url):
        print("\n✗ Server not reachable — aborting.")
        sys.exit(1)
    results.append(True)

    # Auth
    token = verify_auth(base_url)
    results.append(token is not None)

    # Claims
    print_section("Claims: End-to-End Pipeline (real Gemini + Serper)")
    for item in CLAIMS:
        ok = verify_claim(
            base_url,
            claim=item["claim"],
            expected_verdict=item["expected_verdict"],
            token=token,
            image_path=image_path,
        )
        results.append(ok)

    # History (requires successful auth)
    if token:
        results.append(verify_history(base_url, token))

    # Summary
    passed = sum(results)
    total = len(results)
    print(f"\n{'='*60}")
    print(f"  Result: {passed}/{total} checks passed")
    print(f"{'='*60}\n")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
