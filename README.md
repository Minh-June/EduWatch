# EduWatch VNUA

### He Thong Giam Sat Thai Do Hoc Tap Va Vi Pham Quy Che Thi Bang AI

EduWatch la giai phap ung dung Tri tue nhan tao (AI) va Thi giac may tinh (Computer Vision) ho tro giam sat phong hoc, danh gia thai do hoc tap va tu dong phat hien cac hanh vi vi pham quy che thi theo thoi gian thuc.

He thong duoc phat trien tren nen tang **Streamlit**, ho tro quan ly tap trung tu luong Camera IP den xu ly phan tich du lieu va xuat bao cao tu dong.

---

## 1. Huong Dan Cai Dat va Khoi Chay

### Yeu cau moi truong
- Python 3.10 tro len
- Git

### Cac buoc thuc hien

**Buoc 1: Khoi tao moi truong ao va cai dat thu vien**
```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirement.txt
Buoc 2: Khoi tao co so du lieu ban dauPowerShellpython init_db.py
Buoc 3: Khoi chay ung dung StreamlitPowerShellstreamlit run streamlit_app.py
Sau khi khoi chay thanh cong, truy cap he thong tai dia chi:Plaintexthttp://localhost:8501
2. Danh Sach Tai Khoan Thu NghiemPhan quyenMa nguoi dungMat khau mac dinhQuan tri vien (Admin)AD001admin123Giang vien / Giam thiGV123gv123Bao ve / Ky thuat vienBV001bv123Ghi chu: Neu mat khau tai khoan GV123 co su thay doi, vui long doi chieu voi cau hinh khoi tao trong tep init_db.py.3. Cau Truc Thu Muc Du AnPlaintextEduWatch/
|-- AI_model/                     # Mo hinh AI, trong so huan luyen va cau hinh nhan dien
|-- data/
|   |-- eduwatch.db               # Co so du lieu SQLite luu tru nguoi dung va nhat ky
|   |-- avatars/                  # Hinh anh dai dien nguoi dung
|   |-- video/                    # Tap tin video mau
|   `-- captures/                 # Khung hinh trich xuat cac truong hop vi pham
|-- src/
|   |-- ai_core/                  # Module xu ly AI: Detector, Camera Manager, Alert
|   |-- database_query/           # Module truy van co so du lieu (Buildings, Rooms, Logs,...)
|   |-- services/                 # Xu ly nghiep vu he thong (Detection, Violation Log)
|   |-- components/               # Cac thanh phan giao dien bo tro
|   `-- utils/                    # Tep cau hinh he thong (config.py)
|-- streamlit_app.py              # Diem khoi chay chinh cua he thong Website
|-- init_db.py                    # Script khoi tao cau truc du lieu va tai khoan mau
|-- requirement.txt               # Danh sach cac thu vien phu thuoc
`-- README.md                     # Tai lieu huong dan du an
4. Luu Y Ky ThuatTep streamlit_app.py la giao dien chinh thuc cua du an va khong con phu thuoc vao thu vien nicegui.Co so du lieu mac dinh duoc luu tru tai data/eduwatch.db. Truong hop can thiet lap lai toan bo du lieu mau ban dau, thuc hien chay lai lenh:PowerShellpython init_db.py