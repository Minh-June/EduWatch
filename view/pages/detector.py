from nicegui import ui

ui.add_css('style.css')

# --- 1. HEADER (SEARCH & TABS) ---
# Header này sẽ tự động cố định ở trên cùng
with ui.header().classes('header-custom text-black p-4 flex justify-between items-center'):
    # Search Bar
    with ui.row().classes('items-center bg-gray-200/50 rounded-lg px-3 py-1 w-80'):
        ui.icon('search', color='gray')
        ui.input(placeholder='Tòa nhà, Phòng học...').props('borderless dense').classes('text-sm flex-1')
    
    # Tabs
    with ui.row().classes('gap-8 items-center'):
        ui.label('Tổng quan').classes('text-green-700 font-bold border-b-2 border-green-500 pb-1 cursor-pointer')
        ui.label('Phân tích').classes('text-gray-400 hover:text-green-700 cursor-pointer')
    
    # Icons bên phải Header
    with ui.row().classes('items-center gap-3'):
        ui.icon('notifications', color='gray').classes('cursor-pointer')
        ui.icon('settings', color='gray').classes('cursor-pointer')

# --- 2. SIDEBAR BÊN TRÁI ---
with ui.element('div').classes('sidebar-fixed p-6'):
    with ui.column().classes('w-full gap-8'):
        ui.label('EduWatch VNUA').classes('text-xl font-black text-green-700 tracking-tighter')
        
        with ui.column().classes('w-full gap-2'):
            menu = [('videocam', 'Giám sát trực tiếp', True), ('history', 'Nhật ký vi phạm', False), 
                    ('analytics', 'Thống kê báo cáo', False), ('settings', 'Yêu cầu hệ thống', False)]
            for icon, text, active in menu:
                curr_style = 'bg-green-100 text-green-700 font-bold' if active else 'text-gray-400 hover:bg-gray-50'
                with ui.row().classes(f'w-full p-3 rounded-xl items-center gap-3 cursor-pointer {curr_style}'):
                    ui.icon(icon)
                    ui.label(text).classes('text-sm')

# --- 3. NHẬT KÝ BÊN PHẢI ---
with ui.element('div').classes('right-logs overflow-y-auto'):
    ui.label('NHẬT KÝ VI PHẠM MỚI NHẤT').classes('text-[10px] font-black text-gray-400 tracking-widest mb-6')
    for _ in range(3):
        with ui.column().classes('w-full p-4 bg-gray-50 rounded-2xl mb-4 border border-gray-100'):
            ui.label('14:30:05').classes('text-[10px] font-mono text-gray-400 mb-2')
            ui.label('Sử dụng tài liệu trái phép').classes('text-sm font-bold text-red-700 mb-2')
            ui.image('https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=300').classes('rounded-xl mb-4 h-20')
            with ui.row().classes('w-full gap-2'):
                ui.button('Xác nhận').props('flat dense').classes('bg-green-600 text-white flex-1 rounded-lg text-[10px]')
                ui.button('Báo sai').props('flat dense').classes('bg-gray-200 text-gray-600 flex-1 rounded-lg text-[10px]')

# --- 4. NỘI DUNG CHÍNH (CAMERA GRID) ---
with ui.element('div').classes('main-content'):
    # Tiêu đề trang
    with ui.row().classes('w-full justify-between items-end mb-6'):
        with ui.column().classes('gap-1'):
            ui.label('Giảng đường Nguyễn Đăng - P.102').classes('text-2xl font-black headline')
            ui.label('Phòng học đang trong ca thi số 2').classes('text-xs text-gray-400')
        ui.button('Chế độ nhiều camera', icon='grid_view').props('outline color="green"').classes('rounded-xl')

    # Grid Camera 2x2
    with ui.row().classes('w-full grid grid-cols-2 gap-4'):
        for i in range(1, 5):
            with ui.element('div').classes('bg-black rounded-2xl overflow-hidden aspect-video relative'):
                ui.image('https://images.unsplash.com/photo-1524178232363-1fb2b075b655?w=600').classes('w-full h-full object-cover opacity-60')
                ui.badge(f'CAM 0{i}', color='black').classes('absolute top-4 left-4')
                ui.badge('TRỰC TIẾP', color='green').classes('absolute top-4 right-4')

    # Thanh điều khiển Floating phía dưới
    with ui.row().classes('fixed bottom-10 left-[38%] bg-white shadow-2xl p-4 rounded-2xl items-center gap-6 border border-gray-100 z-[2000]'):
        ui.button(icon='photo_camera').props('flat round color="gray"')
        ui.button(icon='radio_button_checked').props('flat round color="red"').classes('animate-pulse')
        ui.separator().props('vertical')
        with ui.column().classes('gap-0'):
            ui.label('AI ĐANG CHẠY').classes('text-[10px] font-black text-green-600')
            ui.label('Phát hiện 02 vi phạm').classes('text-[9px] text-gray-400')
        ui.switch(value=True).props('color="green"')

ui.run()
