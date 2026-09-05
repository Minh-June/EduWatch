**EDUWATCH**

EduWatch là giải pháp ứng dụng Trí tuệ nhân tạo (AI) và Thị giác máy tính (Computer Vision) nhằm hỗ trợ giám sát không gian lớp học, nhận diện hành vi học tập và tự động phát hiện các vi phạm quy chế thi cử theo thời gian thực.

**I. HƯỚNG DẪN CÀI ĐẶT VÀ VẬN HÀNH**

**1. Yêu cầu môi trường**
- Python phiên bản từ 3.10 trở lên.
- Đã cài đặt Git trên máy tính.

**2. Thiết lập môi trường và cài đặt thư viện**
- Mở PowerShell tại thư mục gốc của dự án và chạy các lệnh:

- Khởi tạo môi trường ảo (khuyến nghị):
python -m venv venv
.\venv\Scripts\activate

- Cài đặt danh mục thư viện phụ thuộc:
pip install -r requirement.txt

**3. Khởi tạo cơ sở dữ liệu**
- Chạy lệnh khởi tạo cấu trúc cơ sở dữ liệu mẫu cho lần đầu vận hành:
python init_db.py

**4. Khởi chạy ứng dụng**
- Chạy lệnh kích hoạt giao diện web: streamlit run streamlit_app.py

- Sau khi ứng dụng khởi chạy thành công, truy cập trình duyệt theo địa chỉ: `http://localhost:8501`

**II. DANH SÁCH TÀI KHOẢN MẪU**

| Phân quyền | Tên đăng nhập | Mật khẩu |
| :--- | :--- | :--- |
| Quản trị viên (Admin) | `AD001` | `admin123` |
| Giảng viên / Giám thị | `GV123` | `gv123` |
| Bảo vệ / Kỹ thuật viên | `BV001` | `bv123` |

**III. LƯU Ý VẬN HÀNH**
- streamlit_app.py là cổng giao diện chính thức duy nhất, hệ thống hoàn toàn độc lập và không còn phụ thuộc vào nicegui.

- Cơ sở dữ liệu mặc định được lưu trữ cục bộ tại đường dẫn data/eduwatch.db. Trường hợp cần làm mới hoặc khôi phục lại dữ liệu mẫu gốc, vui lòng chạy lại lệnh python init_db.py.

**IV. CẤU TRÚC DỰ ÁN**

```text
EduWatch/
|-- AI_model/                     # Mô hình AI và các trọng số nhận diện hành vi
|-- data/
|   |-- eduwatch.db               # Cơ sở dữ liệu SQLite lưu trữ dữ liệu vận hành
|   |-- avatars/                  # Ảnh hồ sơ người dùng
|   |-- video/                    # Video lưu trữ mẫu
|   `-- captures/                 # Ảnh/khung hình trích xuất cảnh báo vi phạm
|-- src/
|   |-- ai_core/                  # Xử lý cốt lõi: Detector, Camera Manager, Alert
|   |-- database_query/           # Tầng truy vấn cơ sở dữ liệu (Toà nhà, Phòng, Nhật ký)
|   |-- services/                 # Xử lý nghiệp vụ logic (Detection, Quản lý vi phạm)
|   |-- components/               # Giao diện và các thành phần bổ trợ
|   `-- utils/                    # Cấu hình chung cho hệ thống (config.py)
|-- streamlit_app.py              # Điểm khởi chạy chính của hệ thống Web
|-- init_db.py                    # Mã nguồn khởi tạo cơ sở dữ liệu và dữ liệu ban đầu
|-- requirement.txt               # Danh sách thư viện phụ thuộc
`-- README.md                     # Tài liệu hướng dẫn dự án