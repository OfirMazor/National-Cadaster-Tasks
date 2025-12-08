from arcpy import AddMessage, AddError, env as ENV, RefreshLayer
from arcpy.mp import ArcGISProject
from arcpy.parcel import BuildParcelFabric
from arcpy.da import SearchCursor, UpdateCursor
from arcpy.management import SelectLayerByLocation as SelectByLocation, SelectLayerByAttribute as SelectByAttribute, \
                              MakeFeatureLayer as MakeLayer, GetCount, Dissolve, CalculateField, Merge
from Utils.Configs import CNFG
from Utils.TypeHints import *
from Utils.Validations import compare_counts
from Utils.Helpers import timestamp, get_ProcessGUID, get_RecordGUID, get_ActiveParcel2DGUID, get_ProcessType, \
                          get_layer, Type2CancelType, start_editing, stop_editing, get_BlockGUID, refresh_map_view, \
                          get_DomainValue, get_StartPointGUID, get_EndPointGUID, cursor_length, \
                          get_AbsorbingBlockGUIDs, get_BlockStatus, get_BlockName, reopen_map, activate_record, delete_file, get_ActiveRecord, \
                          process_will_retire_its_block

ENV.overwriteOutput = True


def modify_ParcelsAttributes(ProcessName: str) -> None:
    """
    Replacing the current value of LandDesignationPlan field in the Parcels2D feature class
    with a new value from the matching parcels in the InProcessParcels2D.
    """

    Parcels2D: Layer = get_layer('חלקות')
    RecordGUID: str = get_RecordGUID(ProcessName, 'MAP')

    Scursor: Scur = SearchCursor(get_layer('חלקות ביסוס'), ['ParcelNumber', 'BlockNumber', 'SubBlockNumber', 'LandDesignationPlan'])
    total: int = cursor_length(Scursor)

    AddMessage('\n ⭕ Modifying parcels attributes:')
    editor: Editor = start_editing(ENV.workspace)

    for idx, row in enumerate(Scursor, start=1):
        ParcelNumber, BlockNumber, SubBlockNumber, NewLandDesignation = row[0], row[1], row[2], row[3]
        if NewLandDesignation in ['None', '', 'none']:
            NewLandDesignation: None = None

        Ucursor: Ucur = UpdateCursor(Parcels2D, ['LandDesignationPlan', 'UpdatedByRecord'], f"Name = '{ParcelNumber}/{BlockNumber}/{SubBlockNumber}'")

        for value in Ucursor:
            PreviousUpdateRecord: str|None = value[1]
            value[1]: str = RecordGUID

            PreviousLandDesignation: str|None = value[0]
            if PreviousLandDesignation != NewLandDesignation:
                value[0]: str = NewLandDesignation

            Ucursor.updateRow(value)
            AddMessage(fr"{timestamp()} | {idx}/{total} | ✔️ Parcel {ParcelNumber} at block {BlockNumber}/{SubBlockNumber} modified:")
            AddMessage(fr"               | LandDesignation: {PreviousLandDesignation} ->> {NewLandDesignation}")
            AddMessage(fr"               | UpdateByRecord: {PreviousUpdateRecord} ->> {RecordGUID}")

    stop_editing(editor)
    del Ucursor, Scursor, RecordGUID, Parcels2D, editor


def modify_CurrentFrontsAttributes(ProcessName: str) -> None:
    """Modifies attributes of current fronts based on newer fronts of an improvement process."""

    AddMessage('\n ⭕ Modifying fronts attributes:')
    current_map: Map = ArcGISProject("current").activeMap
    current_map.clearSelection()
    RecordGUID: str = get_RecordGUID(ProcessName, 'MAP')

    process_fronts_layer: Layer = current_map.listLayers('חזיתות ביסוס')[0]
    process_fronts_guids: list[str] = [guid[0] for guid in SearchCursor(process_fronts_layer, 'GlobalID')]
    total: int = len(process_fronts_guids)
    field_that_update: list[str] = ['LegalLength', 'Radius', 'LineType']

    current_fronts_layer: Layer = current_map.listLayers('חזיתות')[0]
    fields_to_update: list[str] = ['Distance', 'Radius', 'LineType', 'UpdatedByRecord', 'StartPointUniqueID', 'EndPointUniqueID', 'Shape@', 'GlobalID']

    ENV.addOutputsToMap = False
    editor: Editor = start_editing(ENV.workspace)
    for idx, guid in enumerate(process_fronts_guids, start=1):
        process_front: Layer = MakeLayer(process_fronts_layer, 'process_front', where_clause = f"GlobalID = '{guid}'")
        current_front: Layer = SelectByLocation(in_layer= current_fronts_layer, select_features= process_front, overlap_type= 'ARE_IDENTICAL_TO')
        count_matches: int = int(current_front.getOutput(2))

        if count_matches == 0:
            AddMessage(f"{timestamp()} | {idx}/{total} | ⚠️ The process front {guid} does not match any current front and will not be modified. \n ")
        if count_matches > 1:
            AddMessage(f"{timestamp()} | {idx}/{total} | ⚠️ The process front {guid} matched with {count_matches} current fronts and will not be modified. \n ")
        if count_matches == 1:
            process_data: Scur = SearchCursor(process_front, field_that_update)
            process_data: dict[str, Any] = [{'LegalLength': i[0], 'Radius': i[1], 'LineType': i[2]} for i in process_data][0]

            current_data = UpdateCursor(current_front.getOutput(0), fields_to_update)
            for row in current_data:
                prior: dict[str, Any] = {'Distance': row[0], 'Radius': row[1], 'LineType': row[2], 'UpdatedByRecord': row[3],
                                         'StartPointUniqueID': row[4], 'EndPointUniqueID': row[5], 'Shape@': row[6], 'GlobalID': row[7]}

                row[0]: float      = process_data['LegalLength']
                row[1]: float|None = process_data['Radius']
                row[2]: int        = process_data['LineType']
                row[3]: str        = RecordGUID
                row[4]: str|None   = get_StartPointGUID(row[6])  # Time Consuming Calculation
                row[5]: str|None   = get_EndPointGUID(row[6])    # Time Consuming Calculation

                current_data.updateRow(row)
                AddMessage(f"{timestamp()} | {idx}/{total} | ✔️ The front {prior['GlobalID']} modified: \n \
               | Distance: {prior['Distance']} ->> {process_data['LegalLength']} \n \
               | LineType: {prior['LineType']} ->> {process_data['LineType']} \n \
               | Radius:   {prior['Radius']} ->> {process_data['Radius']} \n \
               | StartPointUniqueID: {prior['StartPointUniqueID']} ->> {row[4]} \n \
               | EndPointUniqueID: {prior['EndPointUniqueID']} ->> {row[5]} \n \
               | UpdatedByRecord: {prior['UpdatedByRecord']} ->> {RecordGUID} \n ")

            del current_data, process_data


    ENV.addOutputsToMap = True
    current_map.clearSelection()
    stop_editing(editor)
    del editor, current_map, fields_to_update, current_fronts_layer


def modify_CurrentAndNewFrontsAttributes() -> None:

    AddMessage('\n ⭕ Modifying fronts attributes:')
    current_map: Map = ArcGISProject("current").listMaps('מפת עריכה')[0]
    current_map.clearSelection()

    process_fronts_layer: Layer = current_map.listLayers('חזיתות לשימור וחדשות')[0]
    process_fronts_guids: list[str] = [guid[0] for guid in SearchCursor(process_fronts_layer, 'GlobalID')]
    total: int = len(process_fronts_guids)

    current_fronts_layer: Layer = current_map.listLayers('חזיתות')[0]

    ENV.addOutputsToMap = False
    editor: Editor = start_editing(ENV.workspace)
    for idx, guid in enumerate(process_fronts_guids, start=1):
        process_front: Layer = MakeLayer(process_fronts_layer, 'process_front', where_clause = f"GlobalID = '{guid}'")
        current_front: Layer = SelectByLocation(in_layer= current_fronts_layer, select_features= process_front, overlap_type= 'ARE_IDENTICAL_TO')
        count_matches: int = int(current_front.getOutput(2))

        if count_matches == 0:
            AddMessage(f"{timestamp()} | {idx}/{total} | ⚠️ The process front {guid} does not match any current front and will not be modified. \n ")
        if count_matches > 1:
            AddMessage(f"{timestamp()} | {idx}/{total} | ⚠️ The process front {guid} matched with {count_matches} current fronts and will not be modified. \n ")
        if count_matches == 1:
            process_data: Scur = SearchCursor(process_front, ['LegalLength', 'Radius', 'LineType'])
            process_data: dict[str, Any] = [{'LegalLength': i[0], 'Radius': i[1], 'LineType': i[2]} for i in process_data][0]

            current_data = UpdateCursor(current_front.getOutput(0), ['GlobalID', 'Distance', 'LineType', 'Radius', 'Shape', 'StartPointUniqueID', 'EndPointUniqueID', 'Shape@'])
            for row in current_data:
                prior: dict[str, Any] = {'GlobalID': row[0], 'Distance': row[1], 'LineType': row[2], 'Radius': row[3],
                                         'Shape': row[4], 'StartPointUniqueID': row[5], 'EndPointUniqueID': row[6], 'Shape@': row[7]}

                row[1]: float      = process_data['LegalLength']
                row[2]: int        = process_data['LineType']
                row[3]: float|None = process_data['Radius']
                row[5]: str|None   = get_StartPointGUID(row[7])
                row[6]: str|None   = get_EndPointGUID(row[7])

                current_data.updateRow(row)
                AddMessage(f"{timestamp()} | {idx}/{total} | ✔️ The front {prior['GlobalID']} modified: \n \
               | Distance: {prior['Distance']} ->> {process_data['LegalLength']} \n \
               | LineType: {prior['LineType']} ->> {process_data['LineType']} \n \
               | Radius:   {prior['Radius']} ->> {process_data['Radius']} \n \
               | StartPointUniqueID: {prior['StartPointUniqueID']} ->> {row[5]} \n \
               | EndPointUniqueID: {prior['EndPointUniqueID']} ->> {row[6]} \n ")

            del current_data, process_data


    ENV.addOutputsToMap = True
    current_map.clearSelection()
    stop_editing(editor)
    del editor, current_map, current_fronts_layer, count_matches, process_fronts_layer, process_fronts_guids, total


def modify_PointsAttributes(ProcessName: str, task: TaskType) -> None:
    """
    Modifies the Name attribute of current points based on newer points of a process by coordinates match.
    """

    RecordGUID: str = get_RecordGUID(ProcessName, 'MAP')
    current_map: Map = ArcGISProject("current").activeMap
    current_map.clearSelection()

    if task == 'ImproveCurrentCadaster':
        process_points_layer: Layer = current_map.listLayers('נקודות ביסוס')[0]
    elif task == 'RetireAndCreateCadaster':
        process_points_layer: Layer = current_map.listLayers('נקודות לשימור וחדשות')[0]
    else:
        process_points_layer: None = None
        AddError('task argument must be one of [ImproveCurrentCadaster, RetireAndCreateCadaster]')

    points_layer: Layer = current_map.listLayers('נקודות גבול')[0]
    selection_params: dict[str, Any] = {'in_layer': points_layer, 'select_features': process_points_layer, 'selection_type': 'NEW_SELECTION', 'overlap_type': 'ARE_IDENTICAL_TO'}
    current_points_layer: Layer = SelectByLocation(**selection_params).getOutput(0)

    if not compare_counts(process_points_layer, current_points_layer):
        AddMessage(' ⚠️ Warning: Not all points are matched')

    # Modify in edit session
    AddMessage('\n ⭕ Modifying points attributes: \n')
    editor: Editor = start_editing(ENV.workspace)
    process_points_names: Scur = SearchCursor(process_points_layer, ['PointName', 'Shape'])
    total: int = cursor_length(process_points_names)
    for idx, process_point in enumerate(process_points_names, start=1):
        new_name: str = process_point[0]
        new_geom: str = process_point[1]

        current_points_data: Ucur = UpdateCursor(current_points_layer, ['Name', 'Shape', 'UpdatedByRecord'])
        for current_point in current_points_data:
            current_name: str = current_point[0]
            current_geom: str = current_point[1]

            if current_geom == new_geom:
                current_point[0]: str = new_name
                if task == 'ImproveCurrentCadaster':
                    current_point[2]: str = RecordGUID

                current_points_data.updateRow(current_point)
                AddMessage(f'{timestamp()} | {idx}|{total}    ✔️ Modifying point name from {current_name} to {new_name}')

        del current_points_data

    stop_editing(editor)
    current_map.clearSelection()
    del RecordGUID, current_map, points_layer, selection_params, current_points_layer, editor, process_points_names, total


def modify_3DPointsAttributes(ProcessName) -> None:
    """
    Modifies active 3D points attributes that were used in a 3D process as points with preservation role (Role=3).
    The attributes that will be updated:
        - Name: The name of the 3D points.
        - Class: The class of the point (1, 12, 13, or 24)
        - UpdatedByRecord: The GUID of the current record that is modifying.

    Parameters:
        ProcessName (str): The name of the process that currently modifying.
    """
    ENV.addOutputsToMap = False

    RecordGUID: str = get_ActiveRecord('GUID')

    query: str = f"CPBUniqueID = '{get_ProcessGUID(ProcessName)}' And Role = 3"
    points_to_preserve: Layer = MakeLayer(fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}/InProcessBorderPoints3D", 'points_to_preserve', query).getOutput(0)
    data: Scur = SearchCursor(points_to_preserve, ['Name', 'Class', 'Shape'])
    total: int = cursor_length(data)

    active_points: Layer = SelectByLocation(get_layer('נקודות גבול תלת ממדיות'), 'ARE_IDENTICAL_TO', points_to_preserve).getOutput(0)

    if total > 0:
        AddMessage('\n ⭕ Modifying points attributes: \n')

        if not compare_counts(points_to_preserve, active_points):
            AddMessage(' ⚠️ Warning: Not all 3D points are matched')

        for idx, point in enumerate(data, start=1):
            preserved_point_name: str = point[0]
            preserved_point_class: int = point[1]
            preserved_point_coord: Point = point[2]

            points_to_update: Ucur = UpdateCursor(active_points, ['Name', 'Class', 'UpdatedByRecord', 'Shape'], f"Shape == {preserved_point_coord}")
            for row in points_to_update:
                current_name: str = row[0]
                current_class: int = row[1]
                current_updated_record: str = row[2]

                AddMessage(f'{timestamp()} | {idx}|{total}  Modifying point {current_name}')

                if current_name != preserved_point_name:
                    row[0]: str = preserved_point_name
                    AddMessage(f'{timestamp()} | ✔️ Updated name: {preserved_point_name}')

                if current_class != preserved_point_class:
                    row[1]: int = preserved_point_class
                    AddMessage(f'{timestamp()} | ✔️ Updated class: {preserved_point_class}')

                if current_updated_record != RecordGUID:
                    row[3]: str = RecordGUID
                    AddMessage(f'{timestamp()} | ✔️ Updated by record ID: {RecordGUID}')

                points_to_update.updateRow(row)

        del points_to_update

    else:
        AddMessage(f'{timestamp()} | ✔️ No preserved 3D points to update')

    del RecordGUID, points_to_preserve, data, total, active_points


def modify_BlockAttributes(ProcessName: str) -> None:
    """Modifies the StatedArea attribute of current block based on modifications in the block parcels."""

    AddMessage(f'\n ⭕ Modifying block attributes: \n')

    BlockGUID: str = get_BlockGUID(by='ProcessName', name=ProcessName)
    Parcels2D: Layer = get_layer('חלקות')
    Blocks: Layer = get_layer('גושים')

    # Summarize stated area
    Areas_list: list[float] = []
    Parcels2D_areas: Scur = SearchCursor(Parcels2D, 'StatedArea', where_clause = f"BlockUniqueID = '{BlockGUID}'")
    for value in Parcels2D_areas:
        StatedArea: float = value[0]
        if StatedArea not in [None, '', 'None']:
            Areas_list.append(StatedArea)

    TotalArea: float = sum(Areas_list)

    del Areas_list, Parcels2D_areas, Parcels2D

    # Modify in edit session
    editor: Editor = start_editing(ENV.workspace)
    Block_area: Ucur = UpdateCursor(Blocks, ['Name', 'StatedArea'], f"GlobalID = '{BlockGUID}'")

    if cursor_length(Block_area) > 0:
        for row in Block_area:
            BlockName: str = row[0]
            PreviousStatedArea: float = row[1]
            row[1]: float = TotalArea

            Block_area.updateRow(row)
            AddMessage(f"{timestamp()} | ✔️ The Block {BlockName} stated area modified from {PreviousStatedArea} to {TotalArea} square meters \n ")
    else:
        AddMessage(f"{timestamp()} | ✔️ No updates require \n ")

    stop_editing(editor)
    del editor, Block_area, TotalArea, Blocks


def retire_parcels(ProcessName: str, method: Literal[1, 2] = 1) -> None:
    """
    Retire substantiated parcels associated with a given record name.

    Parameters:
        ProcessName (str): The name of the record.
        method (int): The method to update the fields in the active parcels layer.
                      1 will use the CalculateField f
    """

    AddMessage('\n ⭕ Retiring substantiated parcels: \n')
    CurrentMap: Map = ArcGISProject("current").listMaps('מפת עריכה')[0]
    CurrentMap.clearSelection()

    Parcels2D: Layer = CurrentMap.listLayers('חלקות')[0]
    InProcessParcels: Layer = CurrentMap.listLayers('חלקות בתהליך')[0]
    RecordGUID: str = get_RecordGUID(ProcessName, 'SHELF')
    CancelProcessType: int = Type2CancelType(get_ProcessType(ProcessName))

    ToRetire: Scur = SearchCursor(InProcessParcels, ['ParcelNumber', 'BlockNumber', 'SubBlockNumber'], f"CPBUniqueID = '{get_ProcessGUID(ProcessName, 'MAP')}' AND ParcelRole = 1")
    ToRetire: list[str] = sorted([f'{row[0]}/{row[1]}/{row[2]}' for row in ToRetire])

    parcel_numbers: list[int] = [int(p.split('/')[0]) for p in ToRetire]
    ToRetire_expression: str = f', '.join(f'\'{p}\'' for p in ToRetire)
    substantiated_block: str = f'{ToRetire[0].split("/")[1]}/{ToRetire[0].split("/")[2]}'

    # Save the retiring 2D parcels  names in a text file.
    # Since there is a bug of gp tool applying the edits the text file will be used in the block_has_active_parcels function if needed.
    text_file: str = fr"{CNFG.Library}{ProcessName.replace('/', '_')}/RetiredParcels2D.txt"
    delete_file(text_file)
    with open(text_file, "w") as f:
        f.write(ToRetire_expression)

    AddMessage(f'{timestamp()} | 🚫 The following {len(ToRetire)} parcels at block {substantiated_block} will retire: \n              {parcel_numbers}')

    if method == 1:
        SelectByAttribute(in_layer_or_view= Parcels2D, selection_type= 'NEW_SELECTION', where_clause= f"Name IN ({ToRetire_expression})")
        CalculateField(in_table= Parcels2D, expression_type= 'PYTHON3', field= 'CancelProcessType',  expression= CancelProcessType)
        CalculateField(in_table= Parcels2D, expression_type= 'PYTHON3', field= 'RetiredByRecord', expression= f"'{RecordGUID}'")
        CurrentMap.clearSelection()

    elif method == 2:
        parcels_cursor: Ucur = UpdateCursor(Parcels2D, ['RetiredByRecord', 'CancelProcessType'], f"Name IN ({ToRetire_expression})")
        for parcel in parcels_cursor:
            parcel[0]: str = RecordGUID
            parcel[1]: int = CancelProcessType
            parcels_cursor.updateRow(parcel)

        del parcels_cursor

    else:
        AddError(f'{timestamp()} | method Parameter must be one of [1, 2] to retire parcels')

    RefreshLayer(Parcels2D)
    del CurrentMap, Parcels2D, InProcessParcels, RecordGUID, CancelProcessType, ToRetire, parcel_numbers, ToRetire_expression, substantiated_block
    AddMessage(f'{timestamp()} | ✔️ Parcels retired successfully')
    refresh_map_view()
    reopen_map()


def retire_3D_parcels_and_substractions(ProcessName: str) -> None:
    """
    Retires substantiated 3D parcels and their corresponding substractions associated with a given record name.

    Parameters:
        ProcessName (str): The name of the record whose associated 3D parcels and substractions are to be retired.

    """
    AddMessage('\n ⭕ Retiring substantiated 3D parcels and their substractions: \n')
    # Verify whether the process contains substantiated 3D parcels to retire
    inprocess_parcels_3D: str = fr'{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessParcels3D'
    fields: list[str] = ['ParcelNumber', 'BlockNumber', 'SubBlockNumber']
    query: str = f"CPBUniqueID = '{get_ProcessGUID(ProcessName)}' AND Role = 1"
    inprocess_parcels_3D: Scur = SearchCursor(inprocess_parcels_3D, fields, query)

    inprocess_substractions: str = fr'{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessSubstractions'
    fields: list[str] = ['FinalSubstractionNumber', 'BlockNumber', 'SubBlockNumber']
    inprocess_substractions: Scur = SearchCursor(inprocess_substractions, fields, query)

    if cursor_length(inprocess_parcels_3D) > 0 and cursor_length(inprocess_substractions) > 0:

        CurrentMap: Map = ArcGISProject("current").listMaps('סצנת עריכה')[0]
        CurrentMap.clearSelection()
        RecordGUID: str = get_RecordGUID(ProcessName, 'SHELF')
        CancelProcessType: int = Type2CancelType(get_ProcessType(ProcessName))  # For Tamar should be 4

        parcels_3D: Layer = CurrentMap.listLayers('חלקות תלת-ממדיות')[0]
        parcels3d_to_retire: list[str] = sorted([f'{row[0]}/{row[1]}/{row[2]}' for row in inprocess_parcels_3D])  # --> ['ParcelNumber/BlockNumber/SubBlockNumber', ...]
        parcel_numbers: list[int] = [int(p.split('/')[0]) for p in parcels3d_to_retire]  # --> [ParcelNumber, ParcelNumber, ...]
        ToRetire_expression: str = f', '.join(f'\'{p}\'' for p in parcels3d_to_retire)  # --> "ParcelName, ParcelName, ..."
        substantiated_block: str = f'{parcels3d_to_retire[0].split("/")[1]}/{parcels3d_to_retire[0].split("/")[2]}'  # --> "BlockName"

        AddMessage(f'{timestamp()} | 🚫 The following {len(parcels3d_to_retire)} 3D parcels at block {substantiated_block} will retire: \n              {parcel_numbers}')
        SelectByAttribute(in_layer_or_view= parcels_3D, selection_type= 'NEW_SELECTION', where_clause= f"Name IN ({ToRetire_expression})")
        CalculateField(in_table= parcels_3D, expression_type= 'SQL', field= 'CancelProcessType',  expression= CancelProcessType)
        CalculateField(in_table= parcels_3D, expression_type= 'SQL', field= 'RetiredByRecord', expression= f"'{RecordGUID}'")

        AddMessage(f'{timestamp()} | ✔️ 3D Parcels retired successfully')
        CurrentMap.clearSelection()

        # ! If there are 3D parcels to retire there must be substractions to retire.
        substractions: Layer = CurrentMap.listLayers('גריעות')[0]
        substractions_to_retire: list[str] = sorted([f'{row[0]}/{row[1]}/{row[2]}' for row in inprocess_substractions])
        substraction_numbers: list[int] = [int(p.split('/')[0]) for p in substractions_to_retire]
        ToRetire_expression: str = f', '.join(f'\'{p}\'' for p in substractions_to_retire)

        AddMessage(f'{timestamp()} | 🚫 The following {len(substractions_to_retire)} substractions at block {substantiated_block} will retire: \n              {substraction_numbers}')
        SelectByAttribute(in_layer_or_view= substractions, selection_type= 'NEW_SELECTION', where_clause= f"Name IN ({ToRetire_expression})")
        CalculateField(in_table= substractions, expression_type= 'SQL', field= 'CancelProcessType',  expression= CancelProcessType)
        CalculateField(in_table= substractions, expression_type= 'SQL', field= 'RetiredByRecord', expression= f"'{RecordGUID}'")

        AddMessage(f'{timestamp()} | ✔️ Substractions retired successfully')
        del parcels_3D, substractions
        CurrentMap.clearSelection()
        refresh_map_view()

    else:
        AddMessage(f'{timestamp()} | ✔️ No 3D parcels or substractions to retire')


    del inprocess_parcels_3D, inprocess_substractions


def retire_fronts(ProcessName: str) -> None:
    """
    Retire substantiated fronts associated with a given record name.

    Parameters:
        ProcessName (str): The name of the record.
    """
    AddMessage('\n ⭕ Retiring substantiated fronts: \n')
    CurrentMap: Map = ArcGISProject("current").listMaps('מפת עריכה')[0]
    CurrentMap.clearSelection()

    Fronts: Layer = CurrentMap.listLayers('חזיתות')[0]
    InProcessFronts: Layer = CurrentMap.listLayers('חזיתות בתהליך')[0]
    RecordGUID: str = get_RecordGUID(ProcessName, 'SHELF')

    ENV.addOutputsToMap = False
    substantiated_fronts: Layer = MakeLayer(InProcessFronts, 'InProcessFronts_layer', f"""CPBUniqueID = '{get_ProcessGUID(ProcessName, 'MAP')}' AND LineStatus = 1""").getOutput(0)
    count_substantiated: int = int(GetCount(substantiated_fronts)[0])

    if count_substantiated > 0:
        AddMessage(f'{timestamp()} | 🚫 {count_substantiated} Fronts will retire')
        SelectByLocation(in_layer = Fronts, overlap_type = "ARE_IDENTICAL_TO", select_features = substantiated_fronts, selection_type = 'NEW_SELECTION').getOutput(0)
        CalculateField(in_table = Fronts, expression_type = 'PYTHON3', field = 'RetiredByRecord', expression = f"'{RecordGUID}'")
        CurrentMap.clearSelection()

        unmatched_fronts = SelectByLocation(in_layer= substantiated_fronts, overlap_type= "ARE_IDENTICAL_TO", select_features= Fronts, selection_type= 'NEW_SELECTION', invert_spatial_relationship= 'INVERT').getOutput(0)
        count_unmatched_fronts: int = int(GetCount(unmatched_fronts)[0])
        if count_unmatched_fronts > 0:
            unmatched_fronts: list[str] = [row[0] for row in SearchCursor(unmatched_fronts, 'GlobalID')]
            total_unmatched: int = len(unmatched_fronts)
            AddMessage(f'{timestamp()} | ⚠️ {total_unmatched} out of {count_substantiated} Substantiated fronts does not aligning to any current fronts, manually retire the following front in your edit session:')
            for idx, sf in enumerate(unmatched_fronts, start=1):
                AddMessage(f"         | {idx}/{total_unmatched} | {sf}")

        message_type: str = "with warnings" if count_unmatched_fronts > 0 else "successfully"


        AddMessage(f'{timestamp()} | ✔️ Fronts retired {message_type}')

    else:
        AddMessage(f'{timestamp()} | ✔️ No fronts to retire')

    ENV.addOutputsToMap = True
    CurrentMap.clearSelection()
    refresh_map_view()


def retire_substractions_by_2D_process(ProcessName: str) -> None:
    """
    Retires active substractions associated with a 2D Parcel that has retired in the 2D process.

    This function identifies active substractions related to a specific process,
    selects them based on certain criteria, and sets them as retired.
    If no substractions are found in the Area of Interest, the function passes.
    If the substractions found in the Area of Interest are not associated with the relevant 2D parcels, the function will pass.

    Parameters:
        ProcessName (str): The name of the process that retires the substractions.
    """


    active_substractions: Layer = get_layer('גריעות', 'מפת עריכה')
    RefreshLayer(active_substractions)
    count: int = int(GetCount(active_substractions)[0])

    # Continue if there are active substraction in the AOI
    if count > 0:
        parcels_query: str = f"CPBUniqueID = '{get_ProcessGUID(ProcessName, 'MAP')}' AND ParcelRole = 1"
        parcels_to_retire: Scur = SearchCursor(get_layer('חלקות בתהליך'), ['ParcelNumber', 'BlockNumber', 'SubBlockNumber'], parcels_query)
        parcels_to_retire: dict[str, str|None] = {f'{r[0]}/{r[1]}/{r[2]}': get_ActiveParcel2DGUID(f'{r[0]}/{r[1]}/{r[2]}') for r in parcels_to_retire}
        expression: str = f', '.join(f'\'{p}\'' for p in parcels_to_retire.values())

        substraction_to_retire: Result = SelectByAttribute(active_substractions, 'NEW_SELECTION', f""" Parcel2DUniqueID IN ({expression}) """)
        total: int = int(substraction_to_retire[1])

        # Continue if there are active substraction associated with the retiring 2D parcels
        if total > 0:
            AddMessage('\n ⭕ Retiring associated substractions: \n')
            block_name: list[str] = list(parcels_to_retire.keys())[0].split('/')[1:3]
            block_name: str = f'{block_name[0]}/{block_name[1]}'
            substraction_numbers: list[int] = [s[0] for s in SearchCursor(substraction_to_retire, 'SubstractionNumber')]
            CancelProcessType: int = Type2CancelType(get_ProcessType(ProcessName))
            RecordGUID: str = get_RecordGUID(ProcessName, 'SHELF')

            AddMessage(f'{timestamp()} | 🚫 The following {total} substractions at block {block_name} will retire: \n              {substraction_numbers}')
            CalculateField(in_table= substraction_to_retire, expression_type= 'PYTHON3', field= 'CancelProcessType', expression= CancelProcessType)
            CalculateField(in_table= substraction_to_retire, expression_type= 'PYTHON3', field= 'RetiredByRecord', expression= f"'{RecordGUID}'")

            del substraction_numbers, block_name, CancelProcessType, RecordGUID
            AddMessage(f'{timestamp()} | ⚠️ After completion of the current task session, a subtraction-recalculation task should follow to yield newer subtractions')


    del active_substractions, count


def retire_blocks(ProcessName: str) -> None:
    """
    Retire substantiated block tht been modified in a process.

    Parameters:
        ProcessName (str): The name of the process that retiring it block.
    """

    AddMessage('\n ⭕ Retiring substantiated block: \n')

    text_file: str = fr"{CNFG.Library}{ProcessName.replace('/', '_')}/RetiredBlocks.txt"
    delete_file(text_file)

    block_to_retire: Ucur = UpdateCursor(get_layer('גושים'), ['Name', 'RetiredByRecord'], f"""GlobalID = '{get_BlockGUID("ProcessName", ProcessName)}' AND RetiredByRecord IS NULL""")

    for value in block_to_retire:
        value[1]: str = get_RecordGUID(ProcessName, 'SHELF')
        block_to_retire.updateRow(value)

        with open(text_file, "w") as f:
            f.write(value[0])

        AddMessage(f"{timestamp()} | ✔️ Block {value[0]} retired")

    del block_to_retire, text_file


def retire_3D_points(ProcessName: str, tolerance: float = 0.002) -> None:
    """
    Retires 3D border points based on a given process name and tolerance (in Meters).
    This function identifies 3D border points that intersect with the given
    process's boundary and are ready to be retired. It updates their status
    by assigning a cancellation process type and marking them with the
    corresponding record GUID.

    Parameters:
        ProcessName (str): The name of the process that identifies which
                            3D border points to retire.
        tolerance (float, optional): The tolerance distance for 3D intersection.
                                      Default is 0.002.
    """
    AddMessage('\n ⭕ Retiring 3D border points: \n')
    ENV.addOutputsToMap = False

    active_points_layer: Layer = get_layer('נקודות גבול תלת-ממדיות')
    query: str = f"CPBUniqueID = '{get_ProcessGUID(ProcessName, 'MAP')}' AND Role = 1"
    points_to_retire: Layer = MakeLayer(get_layer('נקודות גבול תלת-ממדיות בתהליך'), 'points_to_retire', query)

    to_retire: Result = SelectByLocation(active_points_layer, 'INTERSECT_3D', points_to_retire, f"{tolerance} Meters")
    total: int = int(to_retire.getOutput(2))

    if total > 0:
        record_guid: str = get_RecordGUID(ProcessName, 'SHELF')
        cancel_process_type: int = Type2CancelType(get_ProcessType(ProcessName))

        AddMessage(f'{timestamp()} | 🚫 {total} 3D border points will retire')
        CalculateField(in_table=to_retire.getOutput(0), expression_type='PYTHON3', field='CancelProcessType', expression=cancel_process_type)
        CalculateField(in_table=to_retire.getOutput(0), expression_type='PYTHON3', field='RetiredByRecord', expression=f"'{record_guid}'")

        del record_guid, cancel_process_type
        AddMessage(f'{timestamp()} | ✔️ 3D Points retired successfully')

    else:
        AddMessage(f'{timestamp()} | ✔️ No 3D points to retire')

    del active_points_layer, query, points_to_retire, to_retire, total


def reshape_transferring_block(ProcessName: str) -> None:
    """
    Reshapes the borders of the block from which parcels were transferred in the given process.
    The workflow depends on whether the process retires its sender block:
    1. If the block is fully retired by the process (e.g. there is no more active parcels left in the block):
       No geometry update is required and the function exits.
    2. If the block remains active:
       The function performs the following steps:
         - Identifies the sender block by its process name.
         - Retrieves the parcels retired by the process.
         - Selects all remaining active parcels of the block (excluding the retired ones).
         - Selects the new parcels added by the process that belong to the same block.
         - Merges the remaining and new parcels to build the updated block geometry.
         - Dissolves the merged geometry to create a single polygon.
         - Updates the block’s geometry in the layer containing active blocks ('גושים').
    """


    # (1) The block retired by the process
    if process_will_retire_its_block(ProcessName):
        #   No borders reshape is needed if the block has retires.
        pass

    # (2) The block remained with active parcels and required reshape of its borders.
    else:
        AddMessage(f'\n ⭕ Reshaping sender block borders: \n')

        ENV.addOutputsToMap = False
        home_gdb: str = ArcGISProject("current").defaultGeodatabase

        sender_block_guid: str = get_BlockGUID('ProcessName', ProcessName)
        sender_block_name: str = get_BlockName(sender_block_guid)

        #   Get the retiring parcels of the process as a unified text to use in a query
        AddMessage(f"{timestamp()} | 💡 The sender block {sender_block_name} will be reshaped")
        InProcessParcels2D: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessParcels2D"
        query: str = f"CPBUniqueID = '{get_ProcessGUID(ProcessName)}' And ParcelRole = 1"
        retired_parcel_of_process: Scur = SearchCursor(InProcessParcels2D, ['ParcelNumber', 'BlockNumber', 'SubBlockNumber'], query)
        retired_parcel_as_text: str = ",".join([f"'{i[0]}/{i[1]}/{i[2]}'" for i in retired_parcel_of_process])

        #   Query the for active parcels of the block, excluding the retiring parcels pf the process
        Parcels2D: str = fr"{CNFG.ParcelFabricDataset}{CNFG.OwnerName}Parcels2D"
        query: str = f"""BlockUniqueID = '{sender_block_guid}' And RetiredByRecord Is Null And Name Not In ({retired_parcel_as_text})"""
        remaining_active_parcels: Layer = MakeLayer(Parcels2D, 'remaining_active_parcels', query).getOutput(0)

        #   Query the new parcels of the sender block (they were added earlier in load_new_parcels but are not yet implemented on the map (known bug)
        query: str = f"CPBUniqueID = '{get_ProcessGUID(ProcessName)}' And ParcelRole = 2 And BlockUniqueId = '{sender_block_guid}'"
        new_parcels: Layer = MakeLayer(InProcessParcels2D, 'new_active_parcels', query).getOutput(0)
        merged: Result = Merge([remaining_active_parcels, new_parcels], fr'{home_gdb}\merged_parcels_of_{sender_block_name.replace("/", "_")}')

        #   Compute the updated geometry
        dissolve: Result = Dissolve(merged.getOutput(0), fr'{home_gdb}\sender_block_{sender_block_name.replace("/", "_")}_geometry')
        updated_shape: Polygon = SearchCursor(dissolve.getOutput(0), 'Shape@').next()[0]

        #   Update the block attributes
        block_to_update: Ucur = UpdateCursor(get_layer('גושים'), 'Shape@', f"GlobalID = '{sender_block_guid}' And RetiredByRecord Is Null")
        for row in block_to_update:
            row[0]: Polygon = updated_shape
            block_to_update.updateRow(row)

        del retired_parcel_of_process, remaining_active_parcels, dissolve, updated_shape, block_to_update
        AddMessage(f"{timestamp()} | ✔️ Block {sender_block_name} borders reshaped")

    del home_gdb, sender_block_guid, sender_block_name


def reshape_or_construct_absorbing_blocks(ProcessName: str) -> None:
    """

    """
    AddMessage(f'\n ⭕  Reshaping or constructing absorbing blocks borders: \n')

    ENV.addOutputsToMap = False
    home_gdb: str = ArcGISProject("current").defaultGeodatabase

    refresh_map_view()
    RefreshLayer(get_layer('גושים'))

    absorbing_blocks_guids: list[str] = get_AbsorbingBlockGUIDs()
    total_absorbing: int = len(absorbing_blocks_guids)
    record_guid: str = get_RecordGUID(ProcessName, 'SHELF')
    process_guid: str = get_ProcessGUID(ProcessName)
    InProcessParcels2D: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessParcels2D"


    for idx, guid in enumerate(absorbing_blocks_guids, start=1):
        block_name: str = get_BlockName(guid)
        block_status: int = get_BlockStatus('GlobalID', guid)
        query_new_parcels_of_the_block: str = f"CPBUniqueID = '{process_guid}' And ParcelRole = 2 And BlockUniqueID = '{guid}'"

        # (2.A) The absorbing block is created by the process (טרום תצ''ר).
        #       In this scenario the block already exists in the Blocks table with empty geometry (by earlier CMS\Rakefet creation).
        if block_status == 13:
            AddMessage(f"{timestamp()} | {idx}/{total_absorbing} | 💡 The absorbing block {block_name} borders will be constructed")

            # Get the relevant transferred parcels geometries that will create the new block
            parcels_of_new_block: Layer = MakeLayer(InProcessParcels2D, 'parcels_of_new_block', query_new_parcels_of_the_block).getOutput(0)

            #  Get outer geometry and modify attributes
            dissolve: Result = Dissolve(parcels_of_new_block, fr'{home_gdb}\new_block_{block_name.replace("/", "_")}_geometry')
            new_shape: Polygon = SearchCursor(dissolve.getOutput(0), 'Shape@').next()[0]

            del parcels_of_new_block, dissolve

            # NOTE:
            #  When accessing the active blocks layer directly with a cursor, the cursor fails to locate the relevant block for unknown reasons.
            #  To workaround this, I created an in-memory layer that points to the same data source as the active blocks layer (including the version information).
            #  When the cursor is executed on this in-memory layer, it successfully returns results instead of being empty cursor.
            #  This workaround was verified and worked for process 226/2019.
            block_to_create: Layer = MakeLayer(get_layer('גושים').dataSource, "block_to_create", f"GlobalID = '{guid}'")[0]
            block_to_create: Ucur = UpdateCursor(block_to_create, ['BlockStatus', 'CreatedByRecord', 'Shape@'])
            for row in block_to_create:
                row[0]: int = 12  # נוצר בתצ"ר
                row[1]: str = record_guid
                row[2]: Polygon = new_shape
                block_to_create.updateRow(row)
                AddMessage(f"{timestamp()} | ✔️ Block {block_name} borders constructed successfully")
            del new_shape, block_to_create

        # (2.B) The absorbing block is already exists (and active).
        else:
            AddMessage(f"{timestamp()} | {idx}/{total_absorbing} | 💡 The absorbing block {block_name} borders will be reshaped")
            # Get the relevant parcels geometries that are transferred to the existing block
            transferred_parcels: Layer = MakeLayer(InProcessParcels2D, 'transferred_parcels', query_new_parcels_of_the_block).getOutput(0)

            # Get the current active parcels geometries of the existing block
            Parcels2D: str = fr"{CNFG.ParcelFabricDataset}{CNFG.OwnerName}Parcels2D"
            query: str = f"BlockUniqueID = '{guid}' And RetiredByRecord Is Null"
            current_parcels: Layer = MakeLayer(Parcels2D, 'current_parcels', query).getOutput(0)

            #   Compute the updated geometry
            merged: Result = Merge([current_parcels, transferred_parcels], fr'{home_gdb}\merged_parcels_of_{block_name.replace("/", "_")}')
            dissolved: Result = Dissolve(merged.getOutput(0), fr'{home_gdb}\Block_{block_name.replace("/", "_")}_dissolved')
            updated_shape: Polygon = SearchCursor(dissolved.getOutput(0), 'Shape@').next()[0]

            #   Update the block shape geometry
            block_to_update: Ucur = UpdateCursor(get_layer('גושים'), 'Shape@', f"GlobalID = '{guid}'")
            for row in block_to_update:
                row[0]: Polygon = updated_shape
                block_to_update.updateRow(row)

            AddMessage(f"{timestamp()} | ✔️ Block {block_name} borders reshaped successfully")
            del transferred_parcels, Parcels2D, query, current_parcels, merged, dissolved, updated_shape, block_to_update

        del block_name, block_status, query_new_parcels_of_the_block

    del absorbing_blocks_guids, total_absorbing, record_guid, process_guid
    refresh_map_view()
    RefreshLayer(get_layer('גושים'))


def update_record_status(ProcessName: str, new_status: int) -> None:
    """
    Updates the status of a record to the specified new status.

    Parameters:
        ProcessName (str): The name of the record to update.
        new_status (int): The new status value to assign to the record.
    """

    refresh_map_view()
    new_status_text: str = get_DomainValue("ProcessStatus", new_status)

    editor: Editor = start_editing(ENV.workspace)
    Ucursor: Ucur = UpdateCursor(get_layer('גבולות רישומים'), 'Status', f"Name = '{ProcessName}'")
    for row in Ucursor:
        row[0]: int = new_status
        Ucursor.updateRow(row)

    stop_editing(editor)
    del Ucursor, editor
    AddMessage(f'{timestamp()} | ⚡ Record {ProcessName} status updated to {new_status_text}')

    # Save the record Global ID in a text file
    new_guid: str = SearchCursor(get_layer('גבולות רישומים'), 'GlobalID', f"Name = '{ProcessName}'").next()[0]
    text_file: str = fr"{CNFG.Library}{ProcessName.replace('/', '_')}/RecordGUID.txt"
    delete_file(text_file)
    with open(text_file, "w") as f:
        f.write(new_guid)


def set_as_recorded(ProcessName: str) -> None:
    """
    Set the 'Recorded' field of the specified in-process layers to 1 (Yes).

    Parameters:
        ProcessName (str): The name of the process that it's data will set as Recorded.
    """

    process_type: int = get_ProcessType(ProcessName)

    if process_type == 2:  # תמ"ר
        process_layers: list[str] = ['InProcessParcels3D', 'InProcessSubstractions', 'InProcessBorderPoints3D']
    else:
        process_layers: list[str] = ['InProcessBorderPoints', 'InProcessFronts', 'InProcessParcels2D']

    for name in process_layers:
        data: Ucur = UpdateCursor(fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}{name}", 'Recorded', f"CPBUniqueID = '{get_ProcessGUID(ProcessName)}'")
        for value in data:
            value[0]: int = 1  # כן
            data.updateRow(value)

    AddMessage(f"{timestamp()} | ✔️ In-process data set as recorded \n ")


def build_record(ProcessName: str) -> None:
    """ Build a fabric for the record """

    AddMessage(f'\n ⭕ Building active record \n')

    try:
        BuildParcelFabric(get_layer('רישומים'), extent= "MAXOF", record_name= ProcessName)
        AddMessage(f"{timestamp()} | ✔️ Record {ProcessName} Built successfully \n ")
        activate_record(ProcessName)  # Temporary action due to a bug, will be removed after ArcGIS Pro 3.6
    except Exception as e:
        AddMessage(f"{timestamp()} | ⚠️ Record {ProcessName} couldn't be built: \n {e}")
