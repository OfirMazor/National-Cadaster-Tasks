from Utils.Configs import CNFG
from Utils.TypeHints import Map
from Utils.Validations import validation_set
from Utils.VersionManagement import open_version
from Utils.Helpers import filter_to_roi, set_priority, create_shelf, activate_record, get_layer, zoom_to_aoi
from arcpy import GetParameterAsText
from arcpy.mp import ArcGISProject
from arcpy.conversion import ExportFeatures


def display_process_data(RecordName: str) -> None:
    """
    Export the free edit record as a local feature class and display it on the active map.

    Parameters:
        RecordName (str): The name of the free edit record to be edited.

    Returns:
        None
    """

    # Export the polygon feature of the record border as a local feature class in the home geodatabase
    RecordsBorders: str = fr'{CNFG.ParcelFabricDataset}{CNFG.OwnerName}CadasterRecordsBorders'
    output: str = fr"{ArcGISProject('current').defaultGeodatabase}\FreeEditRecordBorders"
    query: str = f"Name = '{RecordName}' And RecordType = 16"
    fm: str = fr'Name "שם המפה" true true true 255 Text 0 0,First,#,{RecordsBorders},Name,0,254'
    ExportFeatures(RecordsBorders, output, query, field_mapping= fm)

    # Add the exported data as a layer and adjust its place in the project
    active_map: Map = ArcGISProject('current').activeMap
    active_map.addDataFromPath(fr'{CNFG.LayerFiles}FreeEditRecordBorders.lyrx')
    active_map.moveLayer(get_layer("קדסטר בתהליך"), get_layer("גבול תכנית"), "BEFORE")


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
        create_shelf(RecordName, True)

        open_version(RecordName)

        filter_to_roi(RecordName)

        display_process_data(RecordName)

        activate_record(RecordName)

        zoom_to_aoi()


if __name__ == "__main__":
    start_task_FreeEdit(GetParameterAsText(0))
