# Hướng dẫn Thiết lập Máy chủ Nhạc Docker trên Proxmox LXC

Tài liệu này hướng dẫn từng bước để bạn tạo một Container LXC trên Proxmox, cài đặt Docker và khởi chạy máy chủ lưu trữ nhạc để ứng dụng Desktop có thể kết nối phát nhạc trực tiếp và tải lên/xuống.

---

## Bước 1: Tạo Container LXC trên Proxmox VE

Để chạy Docker ổn định bên trong một Container LXC của Proxmox, bạn cần cấu hình một số tùy chọn đặc biệt (Nesting và Keyctl).

1. Truy cập vào giao diện web Proxmox VE.
2. Nhấn nút **Create CT** ở góc trên cùng bên phải.
3. Trong tab **General**:
   - Nhập **Hostname** (ví dụ: `music-server`).
   - Đặt mật khẩu cho tài khoản `root`.
4. Trong tab **Template**:
   - Chọn một template Linux (khuyên dùng **debian-12** hoặc **ubuntu-22.04**).
5. Trong tab **Disks**:
   - Chọn dung lượng ổ cứng phù hợp với lượng nhạc của bạn (ví dụ: 20G - 100G).
6. Trong tab **CPU** & **Memory**:
   - Phân bổ tài nguyên (khuyên dùng ít nhất 1 Core CPU và 1GB RAM).
7. Trong tab **Network**:
   - Chọn chế độ mạng (thường là DHCP để nhận IP tự động từ Router, hoặc đặt IP tĩnh để dễ kết nối).
8. Hoàn thành việc tạo container (nhưng **chưa khởi động**).

---

## Bước 2: Kích hoạt Nesting & Keyctl cho LXC

Đây là bước quan trọng nhất để Docker có thể chạy trong LXC.

1. Chọn Container LXC vừa tạo trong danh sách của Proxmox.
2. Đi tới phần **Options** ở menu bên cạnh.
3. Tìm tùy chọn **Features** -> Nhấp đúp (hoặc chọn và nhấn **Edit**).
4. Tích chọn vào 2 ô:
   - **Nesting** (Cho phép ảo hóa lồng nhau).
   - **Keyctl** (Cần thiết để Docker chạy trình quản lý bộ nhớ driver overlay2).
5. Nhấn **OK** để lưu lại.
6. Bây giờ, bạn có thể **Start** Container LXC này lên.

---

## Bước 3: Cài đặt Docker & Docker Compose bên trong LXC

Mở bảng điều khiển **Console** của Container LXC trên Proxmox và chạy các lệnh sau:

1. Cập nhật hệ thống:
   ```bash
   apt update && apt upgrade -y
   ```
2. Cài đặt các công cụ phụ trợ:
   ```bash
   apt install -y curl git gnupg lsb-release
   ```
3. Cài đặt Docker Engine:
   ```bash
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   ```
4. Kiểm tra xem Docker đã hoạt động chưa:
   ```bash
   docker --version
   docker ps
   ```

---

## Bước 4: Triển khai Music Server

1. Tạo một thư mục làm việc trên LXC:
   ```bash
   mkdir -p /opt/music-server
   cd /opt/music-server
   ```
2. Sao chép 3 file từ thư mục `server/` của dự án này vào `/opt/music-server`:
   - `Dockerfile`
   - `docker-compose.yml`
   - `server.py`
3. Tạo thư mục nhạc để lưu trữ các file nhạc của bạn:
   ```bash
   mkdir -p /opt/music-server/music
   ```
   *(Bạn có thể chép sẵn nhạc của mình vào thư mục `/opt/music-server/music` này).*
4. Khởi chạy Docker Compose để build và chạy server:
   ```bash
   docker compose up -d --build
   ```
5. Kiểm tra xem container đã chạy chưa:
   ```bash
   docker ps
   ```
   Nếu thành công, server sẽ chạy ở port **8000** trên IP của container LXC (ví dụ: `http://192.168.1.150:8000`).

---

## Bước 5: Cấu hình trên Client (Desktop App)

1. Mở file `constants.py` trên máy tính của bạn.
2. Sửa biến `SERVER_URL` thành địa chỉ IP máy chủ LXC của bạn:
   ```python
   SERVER_URL = "http://<IP-CỦA-LXC>:8000"
   ```
   *(Thay `<IP-CỦA-LXC>` bằng IP thực tế của máy chủ Proxmox LXC).*
3. Khởi chạy lại ứng dụng Desktop.
   - Bạn sẽ thấy dòng chữ thông báo đang tải nhạc từ Server.
   - Khi nhấp chuột phải vào bài hát, bạn sẽ có thêm các lựa chọn "Tải lên Server" (với bài hát offline) hoặc "Tải về máy tính" (với bài hát online từ Server).
