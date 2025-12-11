from os import startfile
from Utils.Configs import CNFG
from Utils.TypeHints import *
from Utils.Helpers import create_shelf, get_ProcessGUID, activate_record, load_to_records, filter_to_aoi, zoom_to_aoi, \
                          set_priority, rewrite_record_data, get_aprx_name
from Utils.VersionManagement import open_version
from Utils.Validations import process_in_records, features_exist, validation_set
from Utils.Reports import compute_matching_points_report
from arcpy import GetParameter, GetParameterAsText, env as ENV
from arcpy.mp import ArcGISProject


ENV.preserveGlobalIds = False

 
def display_process_data(ProcessName: str) -> None:
    """
    Display process-related data layers in the current ArcGIS project map.

    Parameters:
        ProcessName (str): The name of the process for which data is displayed.
    """
    CurrentMap: Map = ArcGISProject("current").listMaps('מפת עריכה')[0]
    ProcessGUID: str = get_ProcessGUID(ProcessName)
    query_name: str = f'Process {ProcessName}'

    CurrentMap.addDataFromPath(fr'{CNFG.LayerFiles}ImprovementProcessGroup_{CNFG.Environment}.lyrx')
    Group: Layer = CurrentMap.listLayers('תכנית')[0]
    Group.name = f'{ProcessName} תכנית'
    
    Pointslayer: Layer = CurrentMap.listLayers('נקודות ביסוס')[0]
    Frontslayer: Layer = CurrentMap.listLayers('חזיתות ביסוס')[0]
    Parcelslayer: Layer = CurrentMap.listLayers('חלקות ביסוס')[0]
    Processlayer: Layer = CurrentMap.listLayers('גבול תכנית')[0]
    Sequencelayer: Table = CurrentMap.listTables('פעולות בתכנית')[0]
    
    Pointslayer.updateDefinitionQueries([{'name': query_name, 'sql': f"PointStatus IN (1,3) AND CPBUniqueID = '{ProcessGUID}'", 'isActive': True}])
    Frontslayer.updateDefinitionQueries([{'name': query_name, 'sql': f"LineStatus IN (1,3) AND CPBUniqueID = '{ProcessGUID}'", 'isActive': True}])
    Parcelslayer.updateDefinitionQueries([{'name': query_name, 'sql': f"ParcelRole IN (1,3) AND CPBUniqueID = '{ProcessGUID}'", 'isActive': True}])
    Sequencelayer.updateDefinitionQueries([{'name': query_name, 'sql': f"CPBUniqueID = '{ProcessGUID}'", 'isActive': True}])
    Processlayer.updateDefinitionQueries([{'name': query_name, 'sql': f"GlobalID = '{ProcessGUID}'", 'isActive': True}])
    
    for layer in [Pointslayer, Frontslayer, Parcelslayer]:
        features_exist(layer)

    filter_to_aoi(ProcessName)


def start_task_ImproveCurrentCadaster(Independent: bool, ProcessName: str|None, Report: bool = True) -> None:
    """
    Workflow for starting the Improve Current Cadaster task.

    Parameters:
        Independent (bool): An option to start the task environment for a different process than the one suggested by the APRX file. This option may be useful when the CMS is down. Default is False.
        ProcessName (str, Optional): The name of the cadaster process returned from the APRX file name (if the workflow began from CMS)
                                     or by an independent process name given by the user.
        Report (bool): Perform the matching points report. Default is True.

    """

    set_priority()

    # Whether the process is executed from CMS or independent task.
    ProcessName: str = get_aprx_name() if not Independent else ProcessName

    qualified: bool = validation_set('ImproveCurrentCadaster', ProcessName)

    if qualified:

        shelf: str = create_shelf(ProcessName)

        open_version(ProcessName)

        startfile(fr'{shelf}')

        if process_in_records(ProcessName):
            rewrite_record_data(ProcessName)
        else:
            load_to_records(ProcessName)

        display_process_data(ProcessName)

        activate_record(ProcessName)

        zoom_to_aoi()

        # Report
        if Report:
            compute_matching_points_report(ProcessName, 'ImproveCurrentCadaster')
            startfile(fr'{shelf}/PointsDistanceReport-{ProcessName.replace("/","_")}.xlsx')


if __name__ == "__main__":
    start_task_ImproveCurrentCadaster(Independent= GetParameter(0), ProcessName= GetParameterAsText(1), Report= GetParameter(2))
