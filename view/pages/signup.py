from nicegui import ui

# 1. Thêm CSS để kiểm soát chính xác vị trí
ui.add_head_html('''
    <link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;600&display=swap" rel="stylesheet">
''')

ui.add_css('''
    :root { --primary-green: #37bd74; }
    body { font-family: 'Public Sans', sans-serif; background-color: #f1f3f2; margin: 0; }
    
    .main-card { 
        border-radius: 20px; 
        overflow: hidden; 
        background: white;
        border: none !important;
        box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        display: flex; /* Sử dụng Flexbox để đảm bảo các cột bằng chiều cao nhau */
        flex-direction: row;
    }
    
    .flat-input .q-field__control {
        background-color: #e8e8e8 !important;
        border-radius: 10px !important;
    }
    .flat-input .q-field__control:before, .flat-input .q-field__control:after {
        display: none !important;
    }

    /* Đảm bảo trên mobile banner nhảy lên trên, trên desktop nằm bên trái */
    @media (max-width: 768px) {
        .main-card { flex-direction: column; }
        .banner-side { width: 100% !important; }
        .form-side { width: 100% !important; }
    }
''')

# 2. Bố cục chính
with ui.element('div').classes('w-full min-h-screen flex items-center justify-center p-4'):
    
    # Sử dụng Flex thay vì Grid thuần để kiểm soát tốt hơn
    with ui.element('div').classes('main-card max-w-5xl w-full'):
        
        # --- CỘT TRÁI: BANNER XANH (Chiếm 35%) ---
        with ui.column().classes('banner-side bg-gradient-to-br from-[#37bd74] to-[#006d3c] p-10 text-white relative').style('width: 30%;'):
            with ui.row().classes('items-center gap-2 mb-10'):
                ui.icon('school', color='white').classes('text-3xl')
                ui.label('EduWatch VNUA').classes('font-extrabold text-xl')
            
            ui.label('Chào mừng đến với hệ thống AI quản trị học tập và thi cử') \
                .classes('text-3xl font-bold leading-tight mb-6')
            
            ui.label('Tham gia cộng đồng giảng viên tại Học viện Nông nghiệp Việt Nam để quản lý và theo dõi tiến độ đào tạo hiệu quả hơn') \
                .classes('text-white/80 text-sm')
            
            ui.icon('nature_people').classes('absolute -bottom-10 -right-10 text-[200px] opacity-10')

        # --- CỘT PHẢI: FORM ĐĂNG KÝ (Chiếm 65%) ---
        with ui.column().classes('form-side p-8 md:p-12 gap-6 bg-white flex-grow').style('width: 70%;'):
            ui.label('ĐĂNG KÝ TÀI KHOẢN').classes('text-2xl font-extrabold text-center w-full mb-2 text-gray-800')
            
            # Chia 2 cột cho các ô nhập liệu bên trong form
            with ui.grid(columns=2).classes('w-full gap-x-6 gap-y-7'):
                ui.input('Mã giảng viên').classes('w-full flat-input').props('outlined dense')
                ui.input('Họ và tên').classes('w-full flat-input').props('outlined dense')
                ui.input('Ngày sinh').classes('w-full flat-input').props('outlined dense type=date')
                
                # Chú ý: Dùng label, không dùng value để tránh lỗi ValueError
                ui.select(['Nam', 'Nữ', 'Khác'], label='Chọn giới tính').classes('w-full flat-input').props('outlined dense')
                
                ui.input('Email').classes('w-full flat-input').props('outlined dense')
                ui.input('Số điện thoại').classes('w-full flat-input').props('outlined dense')
                ui.input('Mật khẩu', password=True).classes('w-full flat-input').props('outlined dense')
                ui.input('Nhập lại mật khẩu', password=True).classes('w-full flat-input').props('outlined dense')

            ui.button('ĐĂNG KÝ', on_click=lambda: ui.notify('Đang đăng ký...')) \
                .classes('w-full h-12 bg-[#37bd74] text-white font-bold text-lg rounded-xl mt-4')
            
            with ui.row().classes('w-full justify-center gap-2 text-sm'):
                ui.label('Đã có tài khoản?').classes('text-gray-400')
                ui.link('Quay lại Đăng nhập', '#').classes('font-bold text-[#37bd74] no-underline')

ui.run()
