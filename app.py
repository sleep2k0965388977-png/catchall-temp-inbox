import sqlite3
import re
import json
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
import os

# Fix encoding cho Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Trên Render, dùng /data để lưu trữ persistent (nếu có Disk)
# Nếu không có Disk, dùng thư mục hiện tại
DATA_DIR = os.environ.get("DATA_DIR", ".")
DB_PATH = os.path.join(DATA_DIR, "emails.db")

# Thời gian sống mặc định của email (giờ)
DEFAULT_TTL_HOURS = 24

# Khởi tạo database SQLite
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inboxes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            tag TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expired_at TIMESTAMP,
            status TEXT DEFAULT 'active',
            note TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            to_email TEXT NOT NULL,
            from_email TEXT NOT NULL,
            subject TEXT,
            body_text TEXT,
            body_html TEXT,
            otp_code TEXT,
            magic_link TEXT,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_read INTEGER DEFAULT 0
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_to_email ON emails(to_email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_expired_at ON inboxes(expired_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON inboxes(status)")

    # Migration: thêm cột expired_at và status nếu chưa có (cho DB cũ)
    try:
        cursor.execute("ALTER TABLE inboxes ADD COLUMN expired_at TIMESTAMP")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE inboxes ADD COLUMN status TEXT DEFAULT 'active'")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

init_db()


# Background task: dọn dẹp email hết hạn mỗi 5 phút
async def cleanup_expired_loop():
    """Chạy liên tục trong background, cứ 5 phút quét 1 lần xóa inbox đã hết hạn"""
    while True:
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            # Tìm các inbox đã hết hạn (expired_at <= now AND status = 'active')
            cursor.execute("""
                SELECT id, email FROM inboxes
                WHERE expired_at IS NOT NULL AND expired_at <= ? AND status = 'active'
            """, (now,))
            expired_inboxes = cursor.fetchall()

            cleaned_count = 0
            for inbox_id, email in expired_inboxes:
                # Xóa toàn bộ email liên quan
                cursor.execute("DELETE FROM emails WHERE to_email = ?", (email,))
                # Cập nhật status thành 'expired'
                cursor.execute("UPDATE inboxes SET status = 'expired' WHERE id = ?", (inbox_id,))
                cleaned_count += 1

            if cleaned_count > 0:
                conn.commit()
                print(f"[Cleanup] Đã dọn {cleaned_count} inbox hết hạn tại {now}")

                # Gửi thông báo qua SSE
                event_data = {
                    "type": "cleanup",
                    "message": f"Đã dọn {cleaned_count} inbox hết hạn",
                    "cleaned_count": cleaned_count,
                    "timestamp": datetime.now().strftime("%H:%M:%S %d/%m/%Y")
                }
                for queue in sse_subscribers:
                    await queue.put(event_data)

            conn.close()
        except Exception as e:
            print(f"[Cleanup Error] {e}")

        await asyncio.sleep(300)  # 5 phút quét 1 lần


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Quản lý lifecycle: bắt đầu background cleanup khi app khởi động"""
    cleanup_task = asyncio.create_task(cleanup_expired_loop())
    print("[*] Background cleanup task started (mỗi 5 phút sẽ dọn inbox hết hạn)")
    yield
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Catch-All Temp Mail & OTP Hub", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Danh sách kết nối SSE để đẩy tin nhắn real-time
sse_subscribers: List[asyncio.Queue] = []

def extract_otp_and_links(subject: str, text_content: str, html_content: str = ""):
    """Tự động phân tích và trích xuất mã OTP và Magic Link từ nội dung email"""
    combined = f"{subject}\n{text_content}\n{html_content}"

    # 1. Tìm mã OTP (thường là 4-8 chữ số liên tiếp đi kèm các từ khóa)
    otp = None

    # Pattern ưu tiên có context: "code is 123456", "Mã xác thực: 123456", "OTP: 123456", "verification code: 123456"
    context_patterns = [
        r"(?:code|mã|otp|pin|verification|xác thực|xác minh)[\s\:\-\=islàđược]+(\d{4,8})\b",
        r"\b(\d{4,8})\b[\s]+(?:là mã|is your|is the code|để xác thực)",
        r"(?:TapNow|Google|Login|Register)[\s\S]{0,30}?(\d{4,8})\b"
    ]
    for cp in context_patterns:
        match = re.search(cp, combined, re.IGNORECASE)
        if match:
            otp = match.group(1)
            break

    # Nếu chưa tìm thấy, quét số 6 chữ số độc lập nổi bật
    if not otp:
        standalone = re.findall(r"\b\d{6}\b", combined)
        if standalone:
            otp = standalone[0]
        else:
            four_or_eight = re.findall(r"\b\d{4,8}\b", combined)
            if four_or_eight:
                otp = four_or_eight[0]

    # 2. Tìm Magic Link / Verify URL
    magic_link = None
    # Tìm các link chứa verify, confirm, login, auth, token, passwordless
    urls = re.findall(r'https?://[^\s<>"\'\\)]+', combined)
    for url in urls:
        url_lower = url.lower()
        if any(keyword in url_lower for keyword in ["verify", "confirm", "magic", "token", "passwordless", "auth", "signin", "login", "credential"]):
            magic_link = url
            break

    if not magic_link and urls:
        # Nếu chỉ có 1 url trong mail, khả năng cao là action button
        magic_link = urls[0]

    return otp, magic_link

# Models
class EmailPayload(BaseModel):
    to: str
    from_email: Optional[str] = "unknown@sender.com"
    subject: Optional[str] = "(Không có tiêu đề)"
    text: Optional[str] = ""
    html: Optional[str] = ""

class CreateInboxRequest(BaseModel):
    email: str
    tag: Optional[str] = "TapNow"
    note: Optional[str] = ""
    ttl_hours: Optional[int] = DEFAULT_TTL_HOURS

# API Endpoints
@app.get("/api/inboxes")
def get_inboxes(include_expired: bool = False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    status_filter = "" if include_expired else "WHERE i.status = 'active'"

    cursor.execute(f"""
        SELECT i.id, i.email, i.tag, i.created_at, i.expired_at, i.status, i.note,
               COUNT(e.id) as email_count,
               MAX(e.received_at) as last_email_at,
               (SELECT otp_code FROM emails WHERE to_email = i.email AND otp_code IS NOT NULL ORDER BY id DESC LIMIT 1) as latest_otp,
               (SELECT magic_link FROM emails WHERE to_email = i.email AND magic_link IS NOT NULL ORDER BY id DESC LIMIT 1) as latest_magic_link
        FROM inboxes i
        LEFT JOIN emails e ON i.email = e.to_email
        {status_filter}
        GROUP BY i.id
        ORDER BY i.id DESC
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"status": "success", "data": rows}

@app.post("/api/inboxes")
def create_inbox(req: CreateInboxRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now(timezone.utc)
    expired_at = now + timedelta(hours=req.ttl_hours)

    try:
        cursor.execute(
            "INSERT INTO inboxes (email, tag, note, created_at, expired_at, status) VALUES (?, ?, ?, ?, ?, ?)",
            (req.email.strip().lower(), req.tag, req.note,
             now.strftime("%Y-%m-%d %H:%M:%S"),
             expired_at.strftime("%Y-%m-%d %H:%M:%S"),
             "active")
        )
        conn.commit()
        inbox_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return {"status": "exists", "message": "Email này đã tồn tại trong danh sách"}
    conn.close()
    return {
        "status": "success",
        "id": inbox_id,
        "email": req.email.strip().lower(),
        "expired_at": expired_at.strftime("%Y-%m-%d %H:%M:%S"),
        "ttl_hours": req.ttl_hours
    }

@app.delete("/api/inboxes/{inbox_id}")
def delete_inbox(inbox_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM inboxes WHERE id = ?", (inbox_id,))
    row = cursor.fetchone()
    if row:
        email = row[0]
        cursor.execute("DELETE FROM emails WHERE to_email = ?", (email,))
        cursor.execute("DELETE FROM inboxes WHERE id = ?", (inbox_id,))
        conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/cleanup")
def manual_cleanup():
    """API dọn dẹp thủ công: xóa dữ liệu các inbox đã hết hạn"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, email FROM inboxes
        WHERE expired_at IS NOT NULL AND expired_at <= ? AND status = 'active'
    """, (now,))
    expired = cursor.fetchall()

    cleaned = 0
    for inbox_id, email in expired:
        cursor.execute("DELETE FROM emails WHERE to_email = ?", (email,))
        cursor.execute("UPDATE inboxes SET status = 'expired' WHERE id = ?", (inbox_id,))
        cleaned += 1

    conn.commit()
    conn.close()
    return {"status": "success", "cleaned_count": cleaned, "message": f"Đã dọn {cleaned} inbox hết hạn"}

@app.post("/api/cleanup/purge")
def purge_expired():
    """Xóa hoàn toàn (DELETE) các inbox đã expired ra khỏi database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM inboxes WHERE status = 'expired'")
    expired = cursor.fetchall()

    purged = 0
    for (email,) in expired:
        cursor.execute("DELETE FROM emails WHERE to_email = ?", (email,))
        cursor.execute("DELETE FROM inboxes WHERE email = ?", (email,))
        purged += 1

    conn.commit()
    conn.close()
    return {"status": "success", "purged_count": purged}

@app.get("/api/emails")
def get_emails(to_email: Optional[str] = None, limit: int = 50):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if to_email:
        cursor.execute("""
            SELECT * FROM emails WHERE to_email = ? ORDER BY id DESC LIMIT ?
        """, (to_email.strip().lower(), limit))
    else:
        cursor.execute("""
            SELECT * FROM emails ORDER BY id DESC LIMIT ?
        """, (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"status": "success", "data": rows}

@app.get("/api/stats")
def get_stats():
    """Thống kê tổng quan: số inbox active, expired, tổng email, OTP detected"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM inboxes WHERE status = 'active'")
    active_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM inboxes WHERE status = 'expired'")
    expired_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM emails")
    total_emails = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM emails WHERE otp_code IS NOT NULL")
    otp_detected = cursor.fetchone()[0]

    conn.close()
    return {
        "active_inboxes": active_count,
        "expired_inboxes": expired_count,
        "total_emails": total_emails,
        "otp_detected": otp_detected
    }

@app.post("/api/webhook/email")
async def webhook_receive_email(payload: EmailPayload):
    """Webhook nhận email từ Cloudflare Worker hoặc Mail Server"""
    to_addr = payload.to.strip().lower()
    from_addr = payload.from_email.strip() if payload.from_email else "unknown@sender.com"
    subject = payload.subject or "(Không có tiêu đề)"
    body_text = payload.text or ""
    body_html = payload.html or ""

    otp_code, magic_link = extract_otp_and_links(subject, body_text, body_html)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Kiểm tra xem inbox có active không
    cursor.execute("SELECT status FROM inboxes WHERE email = ?", (to_addr,))
    inbox_row = cursor.fetchone()
    if inbox_row and inbox_row[0] == 'expired':
        conn.close()
        return {"status": "rejected", "reason": "Inbox đã hết hạn"}

    # Tự động lưu inbox vào danh sách nếu chưa có
    now = datetime.now(timezone.utc)
    expired_at = now + timedelta(hours=DEFAULT_TTL_HOURS)
    cursor.execute(
        "INSERT OR IGNORE INTO inboxes (email, tag, created_at, expired_at, status) VALUES (?, ?, ?, ?, ?)",
        (to_addr, "Catch-All", now.strftime("%Y-%m-%d %H:%M:%S"), expired_at.strftime("%Y-%m-%d %H:%M:%S"), "active")
    )

    cursor.execute("""
        INSERT INTO emails (to_email, from_email, subject, body_text, body_html, otp_code, magic_link)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (to_addr, from_addr, subject, body_text, body_html, otp_code, magic_link))
    email_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Phát sự kiện Realtime qua SSE tới tất cả trình duyệt đang mở
    event_data = {
        "type": "new_email",
        "id": email_id,
        "to_email": to_addr,
        "from_email": from_addr,
        "subject": subject,
        "otp_code": otp_code,
        "magic_link": magic_link,
        "received_at": datetime.now().strftime("%H:%M:%S %d/%m/%Y")
    }

    for queue in sse_subscribers:
        await queue.put(event_data)

    return {
        "status": "received",
        "id": email_id,
        "otp_detected": otp_code,
        "magic_link_detected": magic_link
    }

@app.get("/api/events")
async def sse_events(request: Request):
    """Server-Sent Events để cập nhật Email & OTP tức thì lên màn hình"""
    async def event_generator():
        queue = asyncio.Queue()
        sse_subscribers.append(queue)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat
                    yield ": ping\n\n"
        finally:
            sse_subscribers.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# Static files & Web UI
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
def serve_index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"[*] Catch-All Temp Mail Hub is running on: http://localhost:{port}")
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
