## Dự án web AI nhận diện hành vi

## Cài đặt github
Gói cài đặt: https://git-scm.com/install/windows

Hoặc sử dụng winget
```powershell
winget install --id Git.Git -e --source winget
```

Clone:
```
git clone https://github.com/Nolan-21-6-2005/BehaviorNet.git
```
## Khởi tạo

```github
git init
```

## Thêm file

```
git add .
```

```
git commit -m "message"
```

## Đẩy file

```
git push
```
## Cách chạy

### Backend
```
uvicorn main:app --reload
```

### Frontend
```
streamlit run main.py
```
