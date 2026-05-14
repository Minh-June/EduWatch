import nicegui as ui
from pages.dashboard import show_dashboard

def show_sidebar():
    ui.button('Giám sát trực tiếp', onclick = lambda: ui.navigate.to('/detector'))
    ui.button('Nhật ký vi phạm', onclick = lambda: ui.navigate.to('/log'))
    ui.button('Thống kê báo cáo', onclick = lambda: ui.navigate.to('/report'))
    ui.button('Cài đặt hệ thống', onclick = lambda: ui.navigate.to('/setting'))
    ui.run()
