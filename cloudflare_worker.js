/**
 * Cloudflare Email Worker - Tự động bắt mọi email Catch-All và POST về Dashboard
 * Hướng dẫn:
 * 1. Vào Cloudflare Dashboard -> Email Routing -> Email Workers -> Create Worker
 * 2. Dán toàn bộ mã nguồn bên dưới vào Worker.
 * 3. Thay đổi WEBHOOK_URL thành địa chỉ IP / ngrok / domain server của bạn.
 * 4. Vào Email Routing -> Routing Rules -> Catch-all -> Chọn "Send to Worker" và chọn Worker này.
 */

// Địa chỉ Webhook nhận email (Thay thế bằng domain / ngrok / Cloudflare Tunnel của bạn)
const WEBHOOK_URL = "https://catchall-temp-inbox.vercel.app/api/webhook/email";

// Thư viện phân tích email đơn giản
import PostalMime from 'postal-mime';

export default {
  async email(message, env, ctx) {
    try {
      const rawEmail = await new Response(message.raw).arrayBuffer();
      const parser = new PostalMime();
      const parsedEmail = await parser.parse(rawEmail);

      const payload = {
        to: message.to,
        from_email: message.from,
        subject: parsedEmail.subject || "(Không có tiêu đề)",
        text: parsedEmail.text || "",
        html: parsedEmail.html || ""
      };

      // Gửi dữ liệu về Dashboard
      const response = await fetch(env.WEBHOOK_URL || WEBHOOK_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });

      console.log(`Đã chuyển tiếp email gửi tới ${message.to} về Dashboard. Status: ${response.status}`);
    } catch (err) {
      console.error("Lỗi xử lý email:", err);
    }
  }
};
