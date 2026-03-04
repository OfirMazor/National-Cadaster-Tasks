from os import startfile
from Utils.Configs import CNFG
from Utils.TypeHints import Layer, Map
from Utils.Validations import validation_set
from Utils.VersionManagement import open_version
from Utils.Helpers import filter_to_roi, set_priority, create_shelf, activate_record, get_layer, zoom_to_aoi
from arcpy import GetParameterAsText
from arcpy.mp import ArcGISProject
from arcpy.conversion import ExportFeatures


def display_process_data(RecordName: str) -> None:

    RecordsBorders: str = fr'{CNFG.ParcelFabricDataset}{CNFG.OwnerName}CadasterRecordsBorders'
    output: str = fr"{ArcGISProject('current').defaultGeodatabase}\FreeEditRecordBorders"

    ExportFeatures(RecordsBorders, output, f"Name = '{RecordName}'", field_mapping= fr'Name "שם המפה" true true true 255 Text 0 0,First,#,{RecordsBorders},Name,0,254')
    current_map: Map = ArcGISProject('current').activeMap
    current_map.addDataFromPath(fr'{CNFG.LayerFiles}FreeEditRecordBorders.lyrx')
    layer: Layer = get_layer("גבול תכנית")
    layer.name = f'{RecordName} גבול תכנית'


def start_task_FreeEdit(RecordName: str) -> None:
    """
    Workflow for starting the Free Editing task.

    Parameters:
        RecordName (str): The name of the free edit record to be edited.

    Returns:
        None
    """

    set_priority()

    qualified: bool = validation_set('FreeEdit', RecordName)

    if qualified:
        shelf: str = create_shelf(RecordName)

        open_version(RecordName)

        startfile(fr'{shelf}')

        filter_to_roi(RecordName)

        display_process_data(RecordName)

        activate_record(RecordName)

        zoom_to_aoi()


if __name__ == "__main__":
    start_task_FreeEdit(GetParameterAsText(0))
