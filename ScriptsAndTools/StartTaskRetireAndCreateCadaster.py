from os import startfile
from arcpy.mp import ArcGISProject
from arcpy.da import SearchCursor, InsertCursor
from arcpy import RefreshLayer, AddMessage, GetParameterAsText, GetParameter, env as ENV
from Utils.Configs import CNFG
from Utils.TypeHints import *
from Utils.VersionManagement import open_version
from Utils.Reports import compute_matching_points_report
from Utils.Validations import validation_set, creating_record_is_duplicated, features_exist
from Utils.UpdateAttributes import retire_parcels, retire_fronts, retire_substractions_by_2D_process, retire_blocks, \
     update_record_status, reshape_transferring_block, reshape_or_construct_absorbing_blocks
from Utils.Helpers import create_shelf, get_ProcessGUID, get_RecordGUID, get_ProcessType, Type2CreateType, \
    get_BlockGUID, refresh_map_view, timestamp, activate_record, zoom_to_aoi, load_to_records, \
    filter_to_aoi, get_FinalParcel, reopen_map, start_editing, stop_editing, cursor_length, \
    set_priority, process_is_transferring, get_layer, Type2CancelType, get_process_shape, process_will_retire_its_block, \
    get_aprx_name

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

    CurrentMap.addDataFromPath(fr'{CNFG.LayerFiles}RetireAndCreateProcessGroup_{CNFG.Environment}.lyrx')
    Grouplayer: Layer = CurrentMap.listLayers('תכנית')[0]
    Grouplayer.name = f'{ProcessName} תכנית'

    Pointslayer: Layer = CurrentMap.listLayers('נקודות לשימור וחדשות')[0]
    Frontslayer: Layer = CurrentMap.listLayers('חזיתות לשימור וחדשות')[0]
    Parcelslayer: Layer = CurrentMap.listLayers('חלקות חדשות')[0]
    Processlayer: Layer = CurrentMap.listLayers('גבול תכנית')[0]
    Sequencelayer: Table = CurrentMap.listTables('פעולות בתכנית')[0]

    Pointslayer.updateDefinitionQueries([{'name': query_name, 'sql': f"PointStatus IN (2,3) AND CPBUniqueID = '{ProcessGUID}'", 'isActive': True}])
    Frontslayer.updateDefinitionQueries([{'name': query_name, 'sql': f"LineStatus IN (2,3) AND CPBUniqueID = '{ProcessGUID}'", 'isActive': True}])
    Parcelslayer.updateDefinitionQueries([{'name': query_name, 'sql': f"ParcelRole IN (2,3) AND CPBUniqueID = '{ProcessGUID}'", 'isActive': True}])
    Sequencelayer.updateDefinitionQueries([{'name': query_name, 'sql': f"CPBUniqueID = '{ProcessGUID}'", 'isActive': True}])
    Processlayer.updateDefinitionQueries([{'name': query_name, 'sql': f"GlobalID = '{ProcessGUID}'", 'isActive': True}])

    for layer in [Pointslayer, Frontslayer, Parcelslayer]:
        features_exist(layer)

    filter_to_aoi(ProcessName)


def load_intermediate_parcels(ProcessName: str) -> None:
    """
    If exists, load intermediate parcels features into the Parcels2D layer.
    This function fetches intermediate parcel data from the 'חלקות בתהליך' layer and appends it to the 'חלקות' layer
    in the current ArcGIS project map.

    Parameters:
        ProcessName (str): The name of the process that creating and retiring the intermediate parcels.
    """

    inprocess_fields: list[str] = ['ParcelNumber', 'BlockNumber', 'SubBlockNumber', 'LandType', 'IsTax', 'LegalArea', 'LandDesignationPlan', 'Shape@']
    intermediate: Scur = SearchCursor(get_layer('חלקות בתהליך'), inprocess_fields, f"CPBUniqueID = '{get_ProcessGUID(ProcessName)}' And ParcelRole = 4")
    total: int = cursor_length(intermediate)
    del inprocess_fields

    if total > 0:
        AddMessage(f'\n ⭕ Adding intermediate parcels:')
        current_map: Map = ArcGISProject("current").listMaps('מפת עריכה')[0]
        Parcels2D_layer: Layer = current_map.listLayers('חלקות מבוטלות')[0]

        record_guid: str = get_RecordGUID(ProcessName, 'SHELF')
        process_type: int = get_ProcessType(ProcessName)
        CreateProcessType: int = Type2CreateType(process_type)
        CancelProcessType: int = Type2CancelType(process_type)
        parcel_type: int = 2  # סופית

        editor: Editor = start_editing(ENV.workspace)
        AddMessage(f'{timestamp()} | ⚡ {total} intermediate parcels will be added')


        Parcels2DFields: list[str] = ['ParcelNumber', 'BlockNumber', 'SubBlockNumber', 'LandType', 'IsTax', 'StatedArea', 'LandDesignationPlan', 'Shape@', 'CreatedByRecord', 'CreateProcessType', 'BlockUniqueID', 'ParcelType', 'RetiredByRecord', 'CancelProcessType']
        Parcels2DData: Icur = InsertCursor(Parcels2D_layer, Parcels2DFields)
        for idx, parcel_data in enumerate(intermediate, start=1):
            block_guid: str = get_BlockGUID(by= 'BlockName', name= f'{parcel_data[1]}/{parcel_data[2]}')
            temporary_parcel: int = parcel_data[0]
            parcel_final_number: int = get_FinalParcel(parcel_data[0], parcel_data[1], parcel_data[2])
            geometry: Polygon = get_process_shape(ProcessName) if not parcel_data[7] else parcel_data[7]  # For older in-process intermediate parcels were geoetry were not saved.
            parcel_data: tuple[Any] = (parcel_final_number,) + parcel_data[1:7] + (geometry, record_guid, CreateProcessType, block_guid, parcel_type, record_guid, CancelProcessType)
            Parcels2DData.insertRow(parcel_data)

            AddMessage(f'{timestamp()} | {idx}/{total} | ✔️ Temporary parcel {temporary_parcel} added as intermediate parcel {parcel_final_number} at block {parcel_data[1]}/{parcel_data[2]}')

        del total, current_map, record_guid, process_type, CreateProcessType, CancelProcessType, parcel_type, Parcels2DFields, Parcels2DData
        stop_editing(editor)
        RefreshLayer(Parcels2D_layer)
        del editor, Parcels2D_layer


def load_new_parcels(ProcessName: str) -> None:
    """
    Load new parcels features into the Parcels2D layer.
    This function fetches new parcel data from the 'חלקות חדשות' layer and appends it to the 'חלקות' layer
    in the current ArcGIS project map.
    """
    AddMessage(f'\n ⭕ Adding new parcels:')
    refresh_map_view()
    current_map: Map = ArcGISProject("current").listMaps('מפת עריכה')[0]
    Parcels2D_layer: Layer = current_map.listLayers('חלקות')[0]
    NewParcels_layer: Layer = current_map.listLayers('חלקות חדשות')[0]

    record_guid: str = get_RecordGUID(ProcessName, 'SHELF')
    CreateProcessType: int = Type2CreateType(get_ProcessType(ProcessName))
    parcel_type: int = 2  # סופית

    editor: Editor = start_editing(ENV.workspace)
    InProcessFields: list[str] = ['ParcelNumber', 'BlockNumber', 'SubBlockNumber', 'LandType', 'IsTax', 'LegalArea', 'LandDesignationPlan', 'Shape@']
    NewParcelsData: Scur = SearchCursor(NewParcels_layer, InProcessFields)

    total: int = cursor_length(NewParcelsData)
    AddMessage(f'{timestamp()} | ⚡ {total} New parcels will be added')

    Parcels2DFields: list[str] = ['ParcelNumber', 'BlockNumber', 'SubBlockNumber', 'LandType', 'IsTax', 'StatedArea', 'LandDesignationPlan', 'Shape@', 'CreatedByRecord', 'CreateProcessType', 'BlockUniqueID', 'ParcelType']
    Parcels2DData: Icur = InsertCursor(Parcels2D_layer, Parcels2DFields)
    for idx, parcel_data in enumerate(NewParcelsData, start=1):
        block_guid: str = get_BlockGUID(by = 'BlockName', name = f'{parcel_data[1]}/{parcel_data[2]}')
        temporary_parcel: int = parcel_data[0]
        parcel_final_number: int = get_FinalParcel(parcel_data[0], parcel_data[1], parcel_data[2])

        parcel_data: tuple[Any] = (parcel_final_number,) + parcel_data[1:8] + (record_guid, CreateProcessType, block_guid, parcel_type)
        Parcels2DData.insertRow(parcel_data)

        AddMessage(f'{timestamp()} | {idx}/{total} | ✔️ Temporary parcel {temporary_parcel} added as active parcel {parcel_final_number} at block {parcel_data[1]}/{parcel_data[2]}')

    del NewParcelsData, Parcels2DData, NewParcels_layer, total
    stop_editing(editor)
    RefreshLayer(Parcels2D_layer)
    del editor


def load_new_fronts(ProcessName: str) -> None:
    """
    Load new fronts features into the Parcels2DFronts layer.
    This function fetches new fronts data from the 'חזיתות לשימור וחדשות' layer and appends it to the 'חזיתות' layer
    in the current ArcGIS project map.
    """

    AddMessage(f'\n ⭕ Adding new fronts:')
    current_map: Map = ArcGISProject("current").listMaps('מפת עריכה')[0]
    Fronts_layer: Layer = current_map.listLayers('חזיתות')[0]
    NewFronts_layer: Layer = current_map.listLayers('חזיתות לשימור וחדשות')[0]
    record_guid: str = get_RecordGUID(ProcessName, 'SHELF')

    editor: Editor = start_editing(ENV.workspace)
    InProcessFields: list[str] = ['LegalLength', 'Radius', 'LineType', 'Shape@']
    NewFronts_data: Scur = SearchCursor(NewFronts_layer, InProcessFields, "LineStatus = 2")  # חזיתות חדשות
    new_fronts_count: int = cursor_length(NewFronts_data)

    if new_fronts_count > 0:
        AddMessage(f'{timestamp()} | ⚡ {new_fronts_count} New fronts will be added')

        FrontsFields: list[str] = ['Distance', 'Radius', 'LineType', 'Shape@', 'CreatedByRecord']
        FrontsData: Icur = InsertCursor(Fronts_layer, FrontsFields)

        for row in NewFronts_data:
            data: tuple[Any] = row + (record_guid,)
            FrontsData.insertRow(data)
        AddMessage(f'{timestamp()} | ✔️ Fronts Added successfully')

        stop_editing(editor)
        RefreshLayer(Fronts_layer)
        reopen_map()

    else:
        AddMessage(f'{timestamp()} | ✔️ No new fronts to add')

    del new_fronts_count, NewFronts_data, editor, record_guid


def start_task_RetireAndCreateCadaster(Independent: bool, ProcessName: str|None, Report: bool = True) -> None:
    """
    Workflow for starting the Retire And Create Cadaster task.

    Parameters:
        Independent (bool): An option to start the task environment for a different process than the one suggested by the APRX file. This option may be useful when the CMS is down. Default is False.
        ProcessName (str): The name of the cadaster process.
        Report (bool): Perform the matching points report. Default is True.
    """

    set_priority()

    # Whether the process is executed from CMS or independent task.
    ProcessName: str = get_aprx_name() if not Independent else ProcessName

    qualified: bool = validation_set("RetireAndCreateCadaster", ProcessName)

    if qualified:

        shelf: str = create_shelf(ProcessName)

        open_version(ProcessName)

        startfile(fr'{shelf}')

        if creating_record_is_duplicated(ProcessName):
            update_record_status(ProcessName, new_status=5)  # מעדכן סטאטוס לרשומה
        else:
            load_to_records(ProcessName)

        display_process_data(ProcessName)

        activate_record(ProcessName)  # Known issue: The records layer is not updated till the end of the execution of gp tool.

        zoom_to_aoi()

        # Retire
        retire_parcels(ProcessName)

        retire_fronts(ProcessName)

        #    If there are active substractions in the AOI
        retire_substractions_by_2D_process(ProcessName)

        transfer_included: bool = process_is_transferring(ProcessName, 'MAP')
        block_should_retire: bool = process_will_retire_its_block(ProcessName)

        if transfer_included and block_should_retire:
            retire_blocks(ProcessName)

        # Create
        load_new_parcels(ProcessName)

        load_intermediate_parcels(ProcessName)

        load_new_fronts(ProcessName)

        # Transfer action blocks adjustments
        if transfer_included:
            # reshape_sender_block(ProcessName)
            reshape_or_construct_absorbing_blocks(ProcessName)
            reshape_transferring_block(ProcessName)


        # Closers
        reopen_map()
        zoom_to_aoi()

        # Report
        if Report:
            compute_matching_points_report(ProcessName, task= 'RetireAndCreateCadaster')
            startfile(fr'{shelf}/PointsDistanceReport-{ProcessName.replace("/","_")}.xlsx')

        del shelf, transfer_included, block_should_retire


if __name__ == "__main__":
    start_task_RetireAndCreateCadaster(Independent= GetParameter(0), ProcessName= GetParameterAsText(1), Report= GetParameter(2))
