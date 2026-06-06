# 🎮 Tạo Chuyển Động Pixel

**Bộ công cụ tách màu, cắt ảnh sprite sheet và tạo hoạt ảnh pixel chuyên nghiệp.**

> Tác giả: **Thuanvuse** · Telegram: [@chimdangxem](https://t.me/chimdangxem)

![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)
![PyQt6](https://img.shields.io/badge/PyQt6-Desktop_App-green?logo=qt&logoColor=white)
![License](https://img.shields.io/badge/License-Free-brightgreen)

---

## ✨ Tính Năng Chính

### 🎨 Chỉnh Sửa Màu (Color Edit)
- **Xóa màu (Erase Color)**: Xóa hoàn toàn một màu bất kỳ khỏi ảnh, biến thành trong suốt.
- **Giữ màu (Isolate Color)**: Chỉ giữ lại một màu duy nhất, phần còn lại trong suốt.
- **Color Splash**: Giữ màu đã chọn, phần còn lại chuyển trắng đen.
- **Thay màu (Replace Color)**: Đổi một màu thành màu khác, giữ nguyên chi tiết sáng/tối.
- **Hút màu (Pipette)**: Click trực tiếp lên ảnh để chọn màu chính xác với kính lúp phóng to.
- **Cọ vẽ & Tẩy (Brush & Eraser)**: Vẽ tay hoặc xóa pixel trực tiếp lên ảnh.

### ✂️ Cắt Ảnh (Slice)
- **Cắt theo lưới (Grid)**: Chia ảnh thành các ô đều nhau theo số cột × hàng.
- **Tự nhận diện (Auto-Detect)**: Dùng OpenCV tự tìm các nhân vật/vật thể riêng biệt.
- **Cắt thủ công (Manual Draw)**: Click và kéo để vẽ vùng cắt tùy ý trên ảnh.
- **Đồng bộ kích thước**: Tự động đệm (pad) tất cả ảnh cắt ra bằng kích thước ô lớn nhất.
- **Căn chỉnh vị trí từng ô**: Dùng chuột kéo hoặc phím mũi tên để căn chỉnh vị trí nhân vật trong từng khung hình.

### 🎬 Xuất Hoạt Ảnh (Animation & Export)
- **Xem trước hoạt ảnh lặp**: Phát hoạt ảnh trực tiếp trên khung vẽ.
- **Xuất GIF**: Tạo ảnh động `.gif` có nền trong suốt.
- **Xuất MP4**: Tạo video `.mp4` với phông nền đen.
- **Chọn FPS tùy ý**: Tùy chỉnh tốc độ khung hình khi xuất và xem trước.

### 🛠️ Tiện Ích Khác
- Kéo thả ảnh (Drag & Drop) để mở nhanh.
- Undo / Redo không giới hạn bước.
- Zoom / Pan mượt mà trên khung vẽ.
- Hỗ trợ ảnh PNG, JPG, BMP, WebP, TIFF.

---

## 📦 Cài Đặt & Chạy

### Cách 1: Chạy file .exe (Không cần cài Python)

1. Tải file `TaoChuyenDongPixel.exe` từ [Releases](../../releases).
2. Chạy trực tiếp — không cần cài đặt thêm gì.

### Cách 2: Chạy từ mã nguồn

```bash
# 1. Clone repo
git clone https://github.com/Thuanvuse/Tao_Chuyen_Dong_Pixel.git
cd Tao_Chuyen_Dong_Pixel

# 2. Cài thư viện
pip install PyQt6 numpy Pillow opencv-python

# 3. Chạy ứng dụng
python app.py
```

---

## 🖼️ Hướng Dẫn Sử Dụng

### Bước 1: Mở ảnh
- Vào tab **Tập Tin & Lịch Sử** → Nhấn **Mở Ảnh**, hoặc kéo thả ảnh vào cửa sổ.

### Bước 2: Xóa nền / Chỉnh màu (nếu cần)
- Vào tab **Chỉnh Sửa** → Chọn công cụ **Hút Màu** → Click lên ảnh để chọn màu nền.
- Chọn chế độ **Xóa màu đã chọn** → Kéo thanh **Độ Lệch** để điều chỉnh vùng xóa.
- Nhấn **Áp Dụng Bước Này** để lưu kết quả.

### Bước 3: Cắt ảnh
- Vào tab **Cắt Ảnh** → Chọn phương thức cắt (Lưới / Tự nhận diện / Thủ công).
- Nhấn **Cắt & Lưu Khung Ảnh** để mở menu tùy chọn xuất file.

### Bước 4: Xuất hoạt ảnh
- Sau khi cắt, chọn:
  - 📂 **Lưu bộ ảnh PNG riêng lẻ**
  - ▶ **Xem trước hoạt ảnh lặp**
  - 🖼 **Tải ảnh động GIF**
  - 🎥 **Tải video MP4**

---

## ⌨️ Phím Tắt

| Phím | Chức năng |
|------|-----------|
| `Ctrl+O` | Mở ảnh |
| `Ctrl+S` | Lưu ảnh |
| `Ctrl+Z` | Hoàn tác (Undo) |
| `Ctrl+Y` / `Ctrl+T` | Làm lại (Redo) |
| `Space` (giữ) | Kéo ảnh (Pan) trong chế độ cắt thủ công |
| `Esc` | Quay về công cụ Dịch Chuyển |

---

## 🔧 Yêu Cầu Hệ Thống

- **OS**: Windows 10/11
- **Python**: 3.8+ (nếu chạy từ mã nguồn)
- **Thư viện**: PyQt6, numpy, Pillow, opencv-python

---

## 📄 Giấy phép

Phần mềm miễn phí, tự do sử dụng.

**Made with ❤️ by [Thuanvuse](https://github.com/Thuanvuse)**
