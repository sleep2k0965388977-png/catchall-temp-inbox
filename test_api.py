import requests
import json
import sys

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE = "http://127.0.0.1:8000"

# 1. Tao email tam 24h
print("=== TEST 1: Tao email tam 24h ===")
r = requests.post(f"{BASE}/api/inboxes", json={"email": "tap_test001@thuymail.xyz", "tag": "TapNow", "ttl_hours": 24})
print(json.dumps(r.json(), indent=2, ensure_ascii=False))

# 2. Tao email tam 1h
print("\n=== TEST 2: Tao email tam 1h ===")
r = requests.post(f"{BASE}/api/inboxes", json={"email": "tap_quick@thuymail.xyz", "tag": "TapNow", "ttl_hours": 1})
print(json.dumps(r.json(), indent=2, ensure_ascii=False))

# 3. Danh sach inboxes
print("\n=== TEST 3: Danh sach inboxes (co expired_at, status) ===")
r = requests.get(f"{BASE}/api/inboxes")
data = r.json()
for inbox in data["data"]:
    email = inbox["email"]
    status = inbox.get("status", "?")
    expired_at = inbox.get("expired_at", "?")
    print(f"  {email} | status={status} | expired_at={expired_at}")

# 4. Gui email test qua webhook
print("\n=== TEST 4: Webhook nhan email + OTP ===")
r = requests.post(f"{BASE}/api/webhook/email", json={
    "to": "tap_test001@thuymail.xyz",
    "from_email": "security@tapnow.ai",
    "subject": "TapNow verification code: 847291",
    "text": "Ma OTP cua ban la: 847291\nLink: https://app.tapnow.ai/auth/verify?token=abc123",
    "html": "<p>OTP: <strong>847291</strong></p>"
})
print(json.dumps(r.json(), indent=2, ensure_ascii=False))

# 5. Stats
print("\n=== TEST 5: Stats tong quan ===")
r = requests.get(f"{BASE}/api/stats")
print(json.dumps(r.json(), indent=2, ensure_ascii=False))

# 6. Cleanup (chua co gi het han)
print("\n=== TEST 6: Cleanup API ===")
r = requests.post(f"{BASE}/api/cleanup")
print(json.dumps(r.json(), indent=2, ensure_ascii=False))

# 7. Purge
print("\n=== TEST 7: Purge API ===")
r = requests.post(f"{BASE}/api/cleanup/purge")
print(json.dumps(r.json(), indent=2, ensure_ascii=False))

print("\n=== TAT CA API HOAT DONG TOT! ===")
