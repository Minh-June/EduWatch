import nicegui as ui
from src.database_query import insertBuildings



def addBuildings():
    @st.dialog("Thêm tòa nhà")
    buildings_name = st.text_input("Buildings")
    
    if ui.button("Chấp nhận"):
        insertBuilding(buildings_name)

def updateBuildings():
    @st.dialog("Cập nhật tòa nhà")


