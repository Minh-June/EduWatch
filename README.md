# EduWatch VNUA - Hệ Thống Giám Sát Thái Độ Học Tập & Thi Cử Bằng AI

EduWatch là giải pháp ứng dụng AI và Thị giác máy tính (Computer Vision) hỗ trợ giám sát phòng học, đánh giá thái độ học tập và phát hiện các hành vi vi phạm quy chế thi theo thời gian thực.

Hệ thống được phát triển trên nền tảng **Streamlit**, hỗ trợ quản lý tập trung từ luồng Camera IP đến xử lý dữ liệu và xuất báo cáo tự động.

## Hướng dẫn cài đặt & Khởi chạy

### 1. Yêu cầu môi trường
- Python 3.10+ trở lên.
- Đã cài đặt Git.

### 2. Cài đặt các thư viện cần thiết
Mở terminal tại thư mục gốc của dự án và chạy:

# Khởi tạo môi trường ảo (khuyến nghị)
python -m venv venv
.\venv\Scripts\activate

# Cài đặt thư viện
pip install -r requirement.txt

### 3. Khởi tạo cơ sở dữ liệu (lần đầu chạy)
python init_db.py

### 4. Khởi chạy ứng dụng Streamlit
streamlit run streamlit_app.py

### 5. Mở trình duyệt và truy cập
http://localhost:8501

### 6. Tài khoản Demo
Phân quyền              Mã người dùng       Mật khẩu mặc định
Quản trị viên (Admin)       AD001               admin123
Giảng viên / Giám thị       GV123               gv123
Bảo vệ / Kỹ thuật viên      BV001               bv123

### 7. Cấu trúc thư mục chính
EduWatch/
|-- AI_model/                     # Chứa mô hình AI (trọng số, cấu hình nhận diện)
|-- data/
|   |-- eduwatch.db               # SQLite database lưu trữ người dùng & lịch sử
|   |-- avatars/                  # Ảnh hồ sơ người dùng
|   |-- video/                    # Video lưu trữ mẫu
|   `-- captures/                 # Ảnh/khung hình chụp vi phạm
|-- src/
|   |-- ai_core/                  # Core xử lý AI: Detector, Camera Manager, Alert
|   |-- database_query/           # Tương tác truy vấn DB (Buildings, Rooms, Logs,...)
|   |-- services/                 # Xử lý logic dịch vụ (Detection, Violation Log)
|   |-- components/               # Giao diện & Component phụ trợ
|   `-- utils/                    # Cấu hình hệ thống (config.py)
|-- streamlit_app.py              # Entrypoint chính của hệ thống Website
|-- init_db.py                    # Script bootstrap schema và tài khoản mẫu
|-- requirement.txt               # Danh sách thư viện phụ thuộc
`-- README.md                     # Tài liệu hướng dẫn dự án

### 8. Ghi chú
streamlit_app.py là giao diện chính thức, không phụ thuộc vào nicegui.

Cơ sở dữ liệu mặc định nằm tại data/eduwatch.db. Để làm mới toàn bộ dữ liệu mẫu, chạy lại python init_db.py.