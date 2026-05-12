import os
import re
from flask import Flask, render_template, request, jsonify
from flask_bcrypt import Bcrypt

app = Flask(__name__, template_folder='.')
bcrypt = Bcrypt(app)

# Dữ liệu đối soát giả lập từ VNUA
DANH_SACH_NHA_TRUONG = {
    "GV12345": {"name": "Nguyễn Văn A", "dob": "1985-05-20"},
    "BV001": {"name": "Lê Văn B", "dob": "1970-10-10"}
}

def validate_password_full(password):
    if len(password) < 8: return False
    if not re.search(r"[A-Z]", password): return False
    if not re.search(r"[a-z]", password): return False
    if not re.search(r"\d", password): return False
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password): return False
    return True

@app.route('/')
@app.route('/register')
def register():
    return render_template('giao diện đki.html')

@app.route('/api/register', methods=['POST'])
def api_register():
    try:
        data = request.form
        ma_so = data.get('teacher_id')
        ho_ten = data.get('fullname')
        ngay_sinh = data.get('dob')
        email = data.get('email')
        phone = data.get('phone')
        gender = data.get('gender') # 'nam', 'nu', 'khac'
        pw = data.get('password')
        confirm_pw = data.get('confirm_password')

        # 1. Đối soát thông tin nhà trường
        user_info = DANH_SACH_NHA_TRUONG.get(ma_so)
        if not user_info or user_info['name'].lower() != ho_ten.lower() or user_info['dob'] != ngay_sinh:
            return jsonify({"error": "Thông tin Mã số, Họ tên hoặc Ngày sinh không khớp với dữ liệu VNUA!"}), 400

        # 2. Kiểm tra Email VNUA
        if not email or not email.endswith("@vnua.edu.vn"):
            return jsonify({"error": "Vui lòng sử dụng Email định dạng @vnua.edu.vn"}), 400

        # 3. Kiểm tra Số điện thoại
        if not re.match(r"^(03|05|07|08|09)\d{8}$", phone):
            return jsonify({"error": "Số điện thoại không hợp lệ!"}), 400

        # 4. Kiểm tra Mật khẩu chặt chẽ
        if pw != confirm_pw:
            return jsonify({"error": "Mật khẩu xác nhận không trùng khớp!"}), 400
        if not validate_password_full(pw):
            return jsonify({"error": "Mật khẩu chưa đạt yêu cầu bảo mật!"}), 400

        # 5. Mã hóa mật khẩu (Chuẩn bị lưu vào DB sau này)
        hashed_pw = bcrypt.generate_password_hash(pw).decode('utf-8')
        
        # In log để kiểm tra (Trong thực tế sẽ lưu vào Database tại đây)
        print(f"Đăng ký thành công: {ma_so} - {ho_ten} ({gender}) - Email: {email}")

        return jsonify({"success": f"Chào thầy/cô {ho_ten}, tài khoản đã được đăng ký thành công!"}), 201

    except Exception as e:
        print(f"Lỗi hệ thống: {str(e)}")
        return jsonify({"error": "Đã có lỗi xảy ra trên hệ thống."}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)