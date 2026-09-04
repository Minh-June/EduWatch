# EduWatch VNUA

EduWatch hiện có entrypoint Streamlit mới để thay thế giao diện NiceGUI cũ, trong khi `app.py` vẫn được giữ lại để đối chiếu.

## Run

```powershell
cd C:\Users\Admin\Desktop\EduWatch - Copy
python init_db.py
streamlit run streamlit_app.py
```

Mở ứng dụng tại:

```text
http://localhost:8501
```

## Demo Accounts

```text
Admin: AD001 / admin123
Giảng viên/Giám thị: GV123 / 

Bảo vệ/Kỹ thuật: BV001 / bv123
```

## Main Files

```text
EduWatch/
|-- data/
|   |-- eduwatch.db
|   |-- avatars/
|   |-- video/
|   `-- captures/
|-- AI_model/
|-- src/
|   |-- ai_core/
|   |-- database_query/
|   |-- services/
|   |-- utils/
|   `-- database_bootstrap.py
|-- view/
|-- app.py
|-- streamlit_app.py
|-- init_db.py
|-- requirement.txt
`-- README.md
```

## Notes

- `streamlit_app.py` không phụ thuộc `nicegui`.
- Database hiện tại trong `data/eduwatch.db` được giữ nguyên và không bị reset.
- `init_db.py` vẫn là lệnh khởi tạo schema/demo data chuẩn cho project.
