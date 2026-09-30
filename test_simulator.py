import requests
import random
import time
import sys

# Configure UTF-8 for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


def send_test_email():
    url = "http://127.0.0.1:8000/api/webhook/email"
    
    fake_otp = random.randint(100000, 999999)
    test_inboxes = ["user01@thuymail.xyz", "tap_tester@thuymail.xyz", "admin@thuymail.xyz"]
    chosen_inbox = random.choice(test_inboxes)
    
    payload = {
        "to": chosen_inbox,
        "from_email": "security@tapnow.ai",
        "subject": f"TapNow verification code: {fake_otp}",
        "text": f"Xin chào,\n\nMã OTP xác thực tài khoản của bạn là: {fake_otp}\n\nHoặc bấm link để xác thực: https://app.tapnow.ai/auth/verify?token=magic_{random.randint(1000,9999)}",
        "html": f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; background: #f8fafc; border-radius: 8px;">
            <h2 style="color: #4f46e5;">TapNow Account Verification</h2>
            <p>Mã xác thực của bạn là:</p>
            <div style="font-size: 28px; font-weight: bold; color: #10b981; letter-spacing: 4px; padding: 10px 0;">{fake_otp}</div>
            <p>Mã này có hiệu lực trong 10 phút.</p>
            <p><a href="https://app.tapnow.ai/auth/verify?token=magic_{random.randint(1000,9999)}" style="display:inline-block; padding: 10px 20px; background: #4f46e5; color: white; border-radius: 6px; text-decoration: none;">Đăng Nhập Nhanh (Magic Link)</a></p>
        </div>
        """
    }

    try:
        print(f"[*] Đang gửi email giả lập tới: {chosen_inbox} | OTP: {fake_otp}...")
        res = requests.post(url, json=payload, timeout=5)
        print(f"[+] Kết quả Server phản hồi: {res.json()}")
    except Exception as e:
        print(f"[-] Lỗi kết nối tới Server Dashboard (hãy chắc chắn app.py đang chạy): {e}")

if __name__ == "__main__":
    send_test_email()
