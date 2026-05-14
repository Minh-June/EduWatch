from nicegui import ui

# Thêm Fonts
ui.add_head_html('''
    <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@800&family=Public+Sans:wght@400;600&display=swap" rel="stylesheet">
''')

ui.add_css('''
    :root { --primary-green: #37bd74; }
    body { font-family: 'Public Sans', sans-serif; background-color: #f8faf9; }
    .brand-font, h1, h2 { font-family: 'Manrope', sans-serif; }
    .login-card { 
        box-shadow: 0 20px 50px rgba(0, 70, 37, 0.12); 
        border-radius: 24px; 
        background: white; 
        border: none !important; 
    }
''')

# Container chính: Sử dụng grid 2 cột cố định
with ui.row().classes('w-full min-h-screen items-center justify-center p-4 md:p-12'):
    with ui.grid(columns=2).classes('max-w-6xl w-full gap-8 lg:gap-20 items-center'):
        
        # --- CỘT TRÁI (Bên Branding) ---
        with ui.column().classes('w-full gap-6'):
            # Logo
            with ui.row().classes('items-center gap-3'):
                with ui.element('div').classes('w-10 h-10 bg-[#37bd74] rounded-[10px] flex items-center justify-center'):
                    ui.icon('school', color='white').classes('text-2xl')
                ui.label('EduWatch VNUA').classes('brand-font font-extrabold text-2xl text-[#37bd74]')
            
            # Tiêu đề
            with ui.column().classes('gap-0'):
                ui.label('Kiến tạo tương lai').classes('text-4xl lg:text-5xl font-extrabold text-gray-900 leading-tight')
                ui.label('số hóa giáo dục').classes('text-4xl lg:text-5xl font-extrabold text-[#37bd74] leading-tight')
            
            ui.label('Hệ thống giám sát và quản lý đào tạo hiện đại dành cho giảng viên Học viện Nông nghiệp Việt Nam') \
                .classes('text-gray-500 text-lg leading-relaxed')
            
            # Hình ảnh tòa nhà
            ui.image('https://vnua.edu.vn/storage/images/2023/05/toa-nha-trung-tam.jpg') \
                .classes('rounded-[20px] shadow-xl w-full aspect-[4/3] object-cover')

        # --- CỘT PHẢI (Bên Đăng nhập) ---
        with ui.column().classes('w-full items-center'):
            with ui.card().classes('login-card w-full p-8 lg:p-10'):
                
                with ui.column().classes('w-full items-center mb-6'):
                    ui.label('ĐĂNG NHẬP HỆ THỐNG').classes('text-2xl font-extrabold text-black tracking-tight')
                    ui.label('Cổng thông tin Giám sát Đào tạo').classes('text-gray-400 font-medium')

                with ui.column().classes('w-full gap-4'):
                    # Input Mã giảng viên
                    with ui.column().classes('w-full gap-1'):
                        ui.label('Mã giảng viên').classes('text-sm font-bold text-gray-700 ml-1')
                        ui.input(placeholder='Nhập mã số giảng viên') \
                            .classes('w-full').props('outlined color=green-7 bg-color=grey-1 prepend-icon=person')
                    
                    # Input Mật khẩu
                    with ui.column().classes('w-full gap-1'):
                        ui.label('Mật khẩu').classes('text-sm font-bold text-gray-700 ml-1')
                        ui.input(placeholder='••••••••', password=True) \
                            .classes('w-full').props('outlined color=green-7 bg-color=grey-1 prepend-icon=lock')

                    # Row Ghi nhớ & Quên mk
                    with ui.row().classes('w-full justify-between items-center mt-1'):
                        ui.checkbox('Ghi nhớ').classes('text-green-700 font-bold text-xs')
                        ui.link('Quên mật khẩu?', '#').classes('text-green-700 font-bold text-xs no-underline')

                    # Button Đăng nhập
                    ui.button('ĐĂNG NHẬP', on_click=lambda: ui.notify('Đang kết nối...')) \
                        .classes('w-full h-14 bg-[#37bd74] text-white font-bold text-lg rounded-xl shadow-lg mt-2')
                    
                    # Hoặc
                    with ui.row().classes('w-full items-center gap-2 py-1'):
                        ui.separator().classes('col opacity-40')
                        ui.label('HOẶC').classes('text-[10px] text-gray-400 font-bold')
                        ui.separator().classes('col opacity-40')
                    
                    # Button Tạo tài khoản
                    ui.button('Tạo tài khoản mới').props('outline color=green-7') \
                        .classes('w-full h-14 font-bold text-lg rounded-xl')

ui.run()
