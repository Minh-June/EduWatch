import nicegui as ui
from cameras_database import insertCamera

def addCamera():
    with ui.dialog() as dialog, ui.card():
        camera_name = ui.input(label = 'Camera', placeholder = 'Nhap ten camera')
        camera_angle = ui.input(label = 'Angle', placeholder = 'Nhap goc quay')
        camera_source = ui.text_input(label = "Source", placeholder = 'Nhap nguon ket noi')
    
    if ui.button("Chấp nhận"):
        insertCamera(
            camera_name, 
            camera_angle, 
            camera_source
        )

