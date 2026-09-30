# Catch-All Temp Mail & OTP Auto-Capture Hub

Hệ thống quản lý hàng nghìn email ảo theo tên miền riêng (`@domaincuaban.com`), tự động nhận email, trích xuất mã OTP và Magic Link theo thời gian thực (Real-time). **Email tự hủy sau 24 giờ**.

---

## 🎯 3 Khái Niệm Quan Trọng Cần Nắm Rõ

| Loại | Bản chất | Có dùng được "Continue with Google"? | Chi phí | Tự động hóa |
| :--- | :--- | :---: | :---: | :---: |
| **1. `@gmail.com` thật** | Google trực tiếp phát hành. Bắt buộc qua bước thẩm định số điện thoại / CAPTCHA của Google. | **CÓ** | Miễn phí (nhưng bị giới hạn số lượng tạo) | Rất khó do anti-bot của Google |
| **2. Google Account bằng Email riêng** (`SignUpWithoutGmail`) | Dùng email riêng (ví dụ `a01@domain.com`) để đăng ký Google Account tại [Google SignUp](https://accounts.google.com/SignUpWithoutGmail). Google sẽ gửi 6 số OTP về email đó để kích hoạt. Sau khi kích hoạt, nó trở thành Google Account thật. | **CÓ** | Miễn phí (chỉ cần tiền mua tên miền) | Rất cao khi kết hợp với hệ thống Catch-All này |
| **3. Email Catch-All thông thường** | Mọi email gửi tới `*@domain.com` đều được Cloudflare đón và gửi về Dashboard này. Dùng đăng ký qua ô **"Email address"** trên TapNow. | **KHÔNG** (Trừ khi đã làm bước 2) | Rất rẻ (chỉ cần 1 tên miền ~1-2$/năm) | Không giới hạn số lượng |

---

## ✅ Tính Năng Đầy Đủ

| Tính năng | Trạng thái |
|---|:---:|
| Tạo email hàng loạt | ✅ |
| Nhận email via webhook | ✅ |
| Trích xuất OTP/Magic Link | ✅ |
| SSE real-time update | ✅ |
| Cloudflare Worker | ✅ |
| **Tự động xóa sau 24h** | ✅ |
| **Trường `expired_at` / `status`** | ✅ |
| **Countdown timer trên UI** | ✅ |
| **Stats dashboard** | ✅ |
| **API cleanup / purge** | ✅ |
| **Background cron dọn dẹp** | ✅ |
| **Chọn TTL linh hoạt (1h-72h)** | ✅ |

---

## 🏗️ Kiến Trúc Hoàn Chỉnh

```text
TẠO EMAIL (chọn TTL: 1h / 6h / 12h / 24h / 48h / 72h)
    ↓
ACTIVE - countdown đếm ngược
    ↓
Nhận email từ TapNow / Google / bất kỳ
    ↓
Cloudflare Catch-All → Worker → Webhook
    ↓
Extract OTP / Magic Link tự động
    ↓
SSE realtime hiển thị lên Dashboard
    ↓
Countdown về 00:00:00
    ↓
EXPIRED (đánh dấu, không xóa alias)
    ↓
Background cleanup mỗi 5 phút dọn dữ liệu
```

---

## 🚀 Hướng Dẫn Khởi Chạy Ứng Dụng

### Bước 1: Chạy Server Dashboard (Local)
Mở Terminal tại thư mục này và chạy:
```powershell
python app.py
```
Sau đó mở trình duyệt truy cập: **[http://localhost:8000](http://localhost:8000)**

### Bước 2: Thử nghiệm giả lập (Test ngay không cần chờ Cloudflare)
Bạn có thể bấm nút **"Gửi Test"** trên giao diện Web, hoặc chạy lệnh:
```powershell
python test_simulator.py
```
Bạn sẽ thấy mã OTP 6 số và Magic Link xuất hiện tức thì trên giao diện cùng với nút **"Copy OTP"** 1 chạm.

### Bước 3: Test toàn bộ API
```powershell
python test_api.py
```

---

## 📡 API Endpoints

| Method | Path | Mô tả |
|---|---|---|
| `GET` | `/api/inboxes` | Danh sách inbox (có `expired_at`, `status`) |
| `POST` | `/api/inboxes` | Tạo inbox mới (hỗ trợ `ttl_hours`) |
| `DELETE` | `/api/inboxes/{id}` | Xóa inbox |
| `GET` | `/api/emails` | Danh sách email đã nhận |
| `POST` | `/api/webhook/email` | Webhook nhận email từ Cloudflare |
| `GET` | `/api/stats` | Thống kê tổng quan |
| `POST` | `/api/cleanup` | Dọn dẹp inbox hết hạn (đánh dấu expired) |
| `POST` | `/api/cleanup/purge` | Xóa vĩnh viễn các inbox expired khỏi DB |
| `GET` | `/api/events` | SSE stream realtime |

---

## 🌐 Hướng Dẫn Kết Nối Tên Miền Riêng (Cloudflare) Miễn Phí

1. **Mua 1 tên miền giá rẻ**: (ví dụ `.xyz`, `.site`, `.fun` chỉ khoảng 20k - 50k VNĐ/năm).
2. **Trỏ tên miền về Cloudflare** (miễn phí).
3. Vào mục **Email Routing** trên Cloudflare:
   - Kích hoạt **Email Routing** (Cloudflare sẽ tự thêm bản ghi MX).
   - Vào **Email Workers** → Bấm **Create Worker** → Dán nội dung trong file `cloudflare_worker.js` vào.
   - Vào **Routing Rules** → **Catch-all rule** → Chọn hành động **Send to Worker** (chọn Worker vừa tạo).
4. Giờ đây, bất kỳ ai gửi email tới `tap001@domaincuaban.com`, `xyz999@domaincuaban.com`,... toàn bộ thư và mã OTP sẽ tự động đổ thẳng về Dashboard của bạn!
