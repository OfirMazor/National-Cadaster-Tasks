from pandas import DataFrame
from Utils.Configs import CNFG
from Utils.TypeHints import Validation, Layer, Scur, df, series, Map, MapType, TaskType
from Utils.Helpers import get_active_user, get_ProcessGUID, get_ProcessType, timestamp, get_DomainValue, get_layer, \
                          process_is_transferring, cursor_length, process_only_creates, AddTabularMessage
from arcpy import AddMessage, AddError
from arcpy.da import SearchCursor
from arcpy.mp import ArcGISProject
from arcpy.management import GetCount


def user_is_signed_in() -> Validation:
    """Validates user is signed in to the organization portal"""

    user_name: str|None = get_active_user()
    if user_name:
        AddMessage(f'{timestamp()} | ✅ User is signed-in to portal')
        return 'Valid'
    else:
        AddError(f'{timestamp()} | ❌ User is not signed-in to portal')
        return 'Invalid'


def compare_counts(layer_1: Layer, layer_2: Layer) -> bool:
    """
    Compares the feature counts between two arcpy layers. Returns True if the feature counts are equal, False & error otherwise.

    Parameters:
        layer_1 (Layer): First layer.
        layer_2 (Layer): Second layer.
    """
    
    count_1: int = int(GetCount(layer_1).getOutput(0))
    count_2: int = int(GetCount(layer_2).getOutput(0))

    if count_1 != count_2:
        AddMessage(f'    The total selected features from layer {layer_1.name}: {count_1}. \n    The total selected features from layer  {layer_2.name}: {count_2} \n ')
        return False
    else:
        return True


def process_in_records(ProcessName: str) -> bool:
    """
    Checks if a record with the specified `ProcessName` exists in the Parcel Fabric Records table.

    Parameters:
        ProcessName (str): The name of the process to search for.

    Returns:
        bool: True if a record with the given `ProcessName` exists as a record, False otherwise.
    """

    search: Scur = SearchCursor(get_layer('גבולות רישומים'), 'Name', f""" Name = '{ProcessName}' """)
    count: int = cursor_length(search)

    if count == 0:
        return False
    else:
        return True


def creating_record_is_duplicated(ProcessName: str) -> bool | None:
    """
    Checks if a record with the specified `ProcessName` exists in the Parcel Fabric Records table.

    Parameters:
        ProcessName (str): The name of the process to search for.

    Returns:
        str: True if a record with the given `ProcessName` exists, False otherwise.
    """

    query: str = f""" Name = '{ProcessName}' AND RecordType IN (1,11) """
    Records_layer: Layer = get_layer('גבולות רישומים')
    
    query: list[str] = [row[0] for row in SearchCursor(Records_layer, 'Name', query)]
    count: int = len(query)
    del query, Records_layer
    
    if count == 0:
        return False
    if count == 1:
        return True
    else:
        AddError(f'{timestamp()} | ❌ Found {count} records with the name {ProcessName}')
        return None
        

def process_exist(ProcessName: str) -> Validation:
    """
    Checks if a cadastral process with the specified `ProcessName` exists in the CadasterProcessBorders table.

    Parameters:
        ProcessName (str): The name of the process to search for.

    Returns:
        str: 'Valid' if a process with the given `ProcessName` exists, 'Invalid' otherwise.
    """
    
    CadasterProcessBorders: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}CadasterProcessBorders"
    query: list[str] = [row[0] for row in SearchCursor(CadasterProcessBorders, 'ProcessName', f"ProcessName = '{ProcessName}'")]
    count: int = len(query)
    del query, CadasterProcessBorders
    
    if count == 0:
        AddError(f'{timestamp()} | ❌ Process name {ProcessName} is not exist')
        return 'Invalid'
    elif count == 1:
        AddMessage(f'{timestamp()} | ✅ Process name {ProcessName} found')
        return 'Valid'
    else:
        AddError(f'{timestamp()} | ❌ Process exists {count} times')
        return 'Invalid'


def validate_status(ProcessName: str, desire_status: int | list[int]) -> Validation:
    """
    Validate if the current process status is equal to desired status
    """

    status_text: list = []
    if isinstance(desire_status, list):
        for S in desire_status:
            status_text.append(get_DomainValue('ProcessStatus', S))

    elif isinstance(desire_status, int):
        status_text.append(get_DomainValue('ProcessStatus', desire_status))

    current_status: int = SearchCursor(get_layer('גבולות תהליכי קדסטר'), 'Status', f"ProcessName = '{ProcessName}'").next()[0]

    if current_status in desire_status:
        AddMessage(f'{timestamp()} | ✅ Process status is valid')
        return 'Valid'
    else:
        AddError(f'{timestamp()} | ❌ Process status is {get_DomainValue("ProcessStatus", current_status)} but must be one of {status_text}')
        return 'Invalid'


def validate_stated_areas(ProcessName: str) -> Validation:
    """
    Validates that the 'Legal Area' of parcels in the current process matches the 'Stated Area' recorded in the active parcel.
    This function iterates through parcels involved in the specified process (specifically Parcel Roles 1 and 3).
    It compares the incoming legal area against the existing stated area to ensure data integrity before finalization.

    The validation logic includes:
    1.  Exemption: Skips validation if the Process Type is 6 (Amendment 97b).
    2.  ID Resolution: -   For Parcel Type 2: Uses the parcel number directly.
                       -   For Parcel Type 1 (Temporary): Queries the 'SequenceActions' table to find the corresponding final parcel number.
    3.  Comparison:
        -   Retrieves `LegalArea` from `InProcessParcels2D`.
        -   Retrieves `StatedArea` from the live `Parcels2D` layer.
        -   Rounds both values to 3 decimal places before comparing.

    Parameters:
        ProcessName (str): The name of the process with the parcels to validate.

    Returns:
        Validation: A string status indicating the result:
            - 'Valid': All areas match, or the process type is exempt.
            - 'Invalid': Mismatches or Null values were found in the area checks.
    """
    Unmatched: int = 0

    if get_ProcessType(ProcessName) != 6:  # 6 is Amendment 97b

        Parcels2D_path: str = fr"{CNFG.ParcelFabricDataset}{CNFG.OwnerName}Parcels2D"

        SequenceActions: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}SequenceActions"

        process_guid: str = get_ProcessGUID(ProcessName, 'SDE')

        InProcessParcels2D_path: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessParcels2D"
        fields: list[str] = ['ParcelNumber', 'BlockNumber', 'SubBlockNumber', 'ParcelType', 'LegalArea']
        in_process_parcels_data: Scur = SearchCursor(InProcessParcels2D_path, fields, f"ParcelRole IN (1,3) AND CPBUniqueID = '{process_guid}'")

        for incoming_parcel in in_process_parcels_data:

            parcel_number: int = incoming_parcel[0]
            block_name: str = f"{incoming_parcel[1]}/{incoming_parcel[2]}"
            parcel_type: int = incoming_parcel[3]

            if parcel_type == 2:
                parcel_name: str = f"{parcel_number}/{block_name}"
            elif parcel_type == 1:
                query: str = f"FromParcelTemp = {parcel_number} AND CPBUniqueID = '{process_guid}'"
                final_parcel_number: int = SearchCursor(SequenceActions, "FromParcelFinal", query).next()[0]

                if final_parcel_number:
                    parcel_name: str = f"{final_parcel_number}/{block_name}"
                else:
                    parcel_name: None = None
                    AddMessage(f"{timestamp()} | ⚠️ Areas check: Skipping temporary parcel {parcel_number} - the parcel doesn't have final number yet")
            else:
                parcel_name: None = None
                AddError(f'{timestamp()} | Parcel type {parcel_type} is not allowed')

            if parcel_name:
                legal_area: float = round(incoming_parcel[4], 3)

                active_parcel: Scur = SearchCursor(Parcels2D_path, 'StatedArea', f"Name = '{parcel_name}' AND RetiredByRecord IS NULL")
                if cursor_length(active_parcel) == 0:
                    AddError(f'{timestamp()} | ❌ Areas check: parcel {parcel_name.split("/")[0]} at block {block_name} does not exist or not active')
                    stated_area = None
                else:
                    stated_area = round(active_parcel.next()[0], 3)

                if stated_area is None:
                    Unmatched += 1
                    AddError(f'{timestamp()} | ❌ Areas check: Stated area of parcel {parcel_number} at block {block_name}: is Null')

                if legal_area is None:
                    Unmatched += 1
                    AddError(f'{timestamp()} | ❌ Areas check: Legal area of parcel {parcel_number} at block {block_name}: is Null')

                if stated_area != legal_area:
                    Unmatched += 1
                    AddError(f'{timestamp()} | ❌ Areas check: Unmatched areas for parcel {parcel_number} at block {block_name}: \n\
                                                   - Current area: {stated_area} square meters \n\
                                                   - Process area: {legal_area} square meters \n ')

        del process_guid, in_process_parcels_data


    if Unmatched > 0:
        return 'Invalid'
    else:
        AddMessage(f'{timestamp()} | ✅ Parcels stated areas are matched')
        return 'Valid'


def features_exist(layer: Layer) -> None:
    """
    Validate layer is not empty.

    Parameters:
        layer: The layer object
    """
    
    count: int = int(GetCount(layer).getOutput(0))
    if count < 1:
        AddError(f'{timestamp()} | ❌ Layer {layer.name} is empty, verify the process data content before starting the task')
    else:
        AddMessage(f'{timestamp()} | 💡 {layer.name} contains {count} features')


def final_parcels_obtained(ProcessName: str) -> Validation:
    """
    Checks if all temporary parcels in a given process have final parcel numbers assigned.

    Parameters:
        ProcessName (str): The name of the process to be checked.

    Returns:
        str: Valid if all temporary parcels have final parcel numbers assigned, Invalid otherwise.
        """

    count: int = 0
    SequenceActions: str = fr'{CNFG.ParcelFabricDatabase}\{CNFG.OwnerName}.SequenceActions'
    CPBUniqueID: str = get_ProcessGUID(ProcessName, 'MAP')

    Search: Scur = SearchCursor(SequenceActions, ['ToParcelTemp', 'ToParcelFinal'], f"CPBUniqueID = '{CPBUniqueID}'")
    if cursor_length(Search) > 0:
        for row in Search:
            if row[1] in [None, 0, '']:
                count += 1
                AddError(f'{timestamp()} | ❌ Temporary parcel {row[0]} is missing final number')

        del SequenceActions, CPBUniqueID

    else:
        AddError(f'{timestamp()} | ❌ Process {ProcessName} actions are not in sequence action table')

    del Search

    if count > 0:
        AddMessage(f'{timestamp()} | ❌ Final parcel numbers are missing')
        return 'Invalid'
    else:
        AddMessage(f'{timestamp()} | ✅ Final parcel numbers are available')
        return 'Valid'


def final_substractions_obtained(ProcessName: str) -> Validation:
    """
    Checks if all temporary substractions in a given process have final substraction numbers assigned.

    Parameters:
        ProcessName (str): The name of the process to be checked.

    Returns:
        Validation: 'Valid' if all temporary substractions have final substraction numbers assigned, 'Invalid' otherwise.
    """

    count: int = 0
    InProSubstractions: str = fr'{CNFG.ParcelFabricDatabase}\{CNFG.OwnerName}.InProcessSubstractions'
    CPBUniqueID: str = get_ProcessGUID(ProcessName, 'MAP')

    Search: Scur = SearchCursor(InProSubstractions, ['TemporarySubstractionNumber', 'FinalSubstractionNumber'], f"CPBUniqueID = '{CPBUniqueID}'")
    for row in Search:
        if row[1] in [None, 0, '']:
            count += 1
            AddError(f'{timestamp()} | ❌ Temporary substraction {row[0]} is missing final number')

    del Search, CPBUniqueID

    if count > 0:
        AddMessage(f'{timestamp()} | ❌ Final substraction numbers are missing')
        return 'Invalid'
    else:
        AddMessage(f'{timestamp()} | ✅ Final substraction numbers are available')
        return 'Valid'


def absorbing_block_exist(ProcessName: str, map_name: MapType = 'Active map') -> Validation:
    """
    Checks if the absorbing blocks exists for a given process in the current map.

    Parameters:
        ProcessName (str): The name of the process to check for an absorbing block.
        map_name (MapType): The name of the map object to use. Default is the currently active map view.

    Returns:
        str: Valid if all absorbing blocks exist in Blocks table, Invalid otherwise.
    """
    if process_is_transferring(ProcessName, source='SDE'):
        current_map: Map = ArcGISProject('current').activeMap if map_name == 'Active map' else ArcGISProject('current').listMaps(map_name)[0]
        current_map.clearSelection()

        table: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}SequenceActions".replace("/", "\\")
        query: str = f""" CPBUniqueID = '{get_ProcessGUID(ProcessName, source='MAP')}' AND ActionType = 3 """
        absorbing_blocks: Scur = SearchCursor(table, ['ToBlockNumber', 'ToSubBlockNumber'], query)
        absorbing_blocks: set[str] = {f'{row[0]}/{row[1]}' if row[1] is not None else f'{row[0]}/0' for row in absorbing_blocks}

        table: str = fr"{CNFG.ParcelFabricDataset}{CNFG.OwnerName}Blocks".replace("/", "\\")
        errors: int = 0
        for name in absorbing_blocks:
            block: Scur = SearchCursor(table, 'Name', f""" Name = '{name}' """)
            block: int = cursor_length(block)
            if block != 1:
                errors += 1
                AddMessage(f'{timestamp()} | ❌ Absorbing block {name} is not exist or not active')


        if errors == 0:
            AddMessage(f"{timestamp()} | ✅ Absorbing blocks {', '.join(sorted(absorbing_blocks))} are available")
            return 'Valid'
        elif errors > 0:
            return 'Invalid'
        else:
            return 'Invalid'

    else:
        return 'Valid'


def validate_substantiated_Parcels2D(ProcessName: str) -> Validation:
    """
    Validates that 2D parcel numbers referenced in a new subtraction process are final numbers
    and exist as active parcels in the Parcels2D layer.

    Parameters:
        ProcessName (str): The name of the process contains the in-process substractions.
    """

    Parcels2D: str = fr"{CNFG.ParcelFabricDataset}{CNFG.OwnerName}.Parcels2D"

    InProSubstractions: str = fr'{CNFG.ParcelFabricDatabase}\{CNFG.OwnerName}.InProcessSubstractions'
    fields: list[str] = ['Parcel2DNumber', 'BlockNumber', 'SubBlockNumber', 'TemporarySubstractionNumber', 'Parcel2DType']
    query: str = f" CPBUniqueID = '{get_ProcessGUID(ProcessName, 'MAP')}' "
    search: Scur = SearchCursor(InProSubstractions, fields, query)
    Parcels2D_dict: dict[int, list[str, int]] = {row[3]: [f'{row[0]}/{row[1]}/{row[2]}', row[4]] for row in search}  # -> {TemporarySubstractionNumber : [Parcel2DName, Parcel2DType]}
    del InProSubstractions, search, fields, query

    errors: int = 0
    for key, value in Parcels2D_dict.items():
        if value[1] == 1:  # ארעית
            AddMessage(f'{timestamp()} | ❌ The referenced 2D parcel {value[0].split("/")[0]} of substraction {key} is temporary but must be final')
            errors += 1

        elif value[1] == 2:  # סופית
            search: Scur = SearchCursor(Parcels2D, 'Name', f"Name = '{value[0]}'")
            if cursor_length(search) != 1:
                errors += 1
                AddMessage(f'{timestamp()} | ❌ Substraction {key} references 2D parcel {value[0]} which either not exist or is inactive')
        else:
            AddMessage(f'{timestamp()} | ❌ Referenced 2D parcel type is invalid (got {value[1]} but must be 1 or 2)')

    if errors > 0:
        AddMessage(f'{timestamp()} | ❌ Invalid 2D parcels reference in the new substractions')
        return 'Invalid'
    else:
        AddMessage(f'{timestamp()} | ✅ New substractions referencing to valid 2D parcels')
        return 'Valid'


def validate_substantiated_Parcels3D(ProcessName: str) -> Validation:
    """
    Validates the consistency of 3D parcel data in a specific process 3D parcel.

    This function compares parcel data associated with the given process (`ProcessName`)
    against the active 3D parcel layer. It checks for mismatches in the attributes: StatedVolume,
    ProjectedArea, UpperLevel, and LowerLevel. If any discrepancies are found or if
    parcels in the process do not exist in the active layer, the validation is considered  invalid.

    Parameters:
        ProcessName (str): The name of the process whose 3D parcel data needs validation.

    Returns:
        Literal['Valid', 'Invalid']:
            - 'Valid' if all parcels in the process match the active layer's data or
             if the process is only for creating parcels.
            - 'Invalid' if any mismatches or errors are detected.
    """

    if not process_only_creates(ProcessName):
        errors: int = 0

        process_parcels: Scur = SearchCursor(fr'{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessParcels3D',
                                             ['ParcelNumber', 'BlockNumber', 'SubBlockNumber', 'StatedVolume', 'ProjectedArea', 'UpperLevel', 'LowerLevel'],
                                             f" CPBUniqueID = '{get_ProcessGUID(ProcessName, 'MAP')}' ")

        process_parcels: dict[str, list[float]] = {f'{row[0]}/{row[1]}/{row[2]}': [row[3], row[4], row[5], row[6]] for row in process_parcels}  # -> {Name: ['StatedVolume', 'ProjectedArea', 'UpperLevel', 'LowerLevel']}
        parcels_names: str = ", ".join(f"'{key}'" for key in process_parcels.keys())


        active_parcels: Scur = SearchCursor(fr'{CNFG.ParcelFabricDataset}\{CNFG.OwnerName}.Parcels3D',
                                            ['Name', 'StatedVolume', 'ProjectedArea', 'UpperLevel', 'LowerLevel'],
                                            f" Name IN ({parcels_names}) And RetiredByRecord Is Null")

        active_parcels: dict[str, list[float]] = {row[0]: [row[3], row[4], row[5], row[6]] for row in active_parcels}  # -> {Name: ['StatedVolume', 'ProjectedArea', 'UpperLevel', 'LowerLevel']}


        Volume_idx, Area_idx, UpperL_idx, LowerL_idx = 0, 1, 2, 3
        del parcels_names

        for name in process_parcels:
            process_data: list[float] = process_parcels[name]

            if name not in active_parcels:
                errors += 1
                AddMessage(f'{timestamp()} | ❌ Parcel {name.split("/")[0]} at block {name.split("/")[1]} was not found or not active')

            else:
                active_data: list[float] = active_parcels[name]
                a_volume, a_area, a_upper, a_lower = active_data[Volume_idx], active_data[Area_idx], active_data[UpperL_idx], active_data[LowerL_idx]
                p_volume, p_area, p_upper, p_lower = process_data[Volume_idx], process_data[Area_idx], process_data[UpperL_idx], process_data[LowerL_idx]

                if a_volume != p_volume:
                    errors += 1
                    AddError(f'{timestamp()} | ❌ Unmatched volumes for parcel {name.split("/")[0]} at block {name.split("/")[1]}/{name.split("/")[2]}: \n\
                                                    Current volume is {a_volume} cubic meters \n\
                                                    Process volume is {p_volume} cubic meters \n ')

                if a_area != p_area:
                    errors += 1
                    AddError(f'{timestamp()} | ❌ Unmatched project areas for parcel {name.split("/")[0]} at block {name.split("/")[1]}/{name.split("/")[2]}: \n\
                                                    Current projected area is {a_area} square meters \n\
                                                    Process projected area is {p_area} square meters \n ')

                if a_upper != p_upper:
                    errors += 1
                    AddError(f'{timestamp()} | ❌ Unmatched upper levels for parcel {name.split("/")[0]} at block {name.split("/")[1]}/{name.split("/")[2]}: \n\
                                                    Current upper level is {a_upper} meters \n\
                                                    Process upper level is {p_upper} meters \n ')
                if a_lower != p_lower:
                    errors += 1
                    AddError(f'{timestamp()} | ❌ Unmatched lower levels for parcel {name.split("/")[0]} at block {name.split("/")[1]}/{name.split("/")[2]}: \n\
                                                    Current lower level is {a_lower} meters \n\
                                                    Process lower level is {p_lower} meters \n ')

        if errors == 0:
            AddMessage(f'{timestamp()} | ✅ 3D Parcels attributes are matched')
            return 'Valid'
        else:
            AddError(f'{timestamp()} | ❌ Input attributes of 3D Parcels from the process is not matching the current attributes')
            return 'Invalid'
    else:
        return 'Valid'


def validation_set(task: TaskType, ProcessName: str) -> bool:
    """
    Validates the prerequisites and data integrity for a specific cadaster task before beginning edits operations.
    This function performs a series of checks tailored to the provided task type.
    It generates a summary report and logs errors if validation fails.

    Parameters:
        task (TaskType): the type of the task to map the validations.
        ProcessName (str): The name of the process that contains the features to validate,
    Returns:
        True if all validation checks pass (all 'Results' are 'Valid'),
        False if any check fails or if an invalid task type is provided.
    """

    AddMessage(f'\n ⭕ Validating:')

    if task not in ['ImproveCurrentCadaster', 'RetireAndCreateCadaster', 'ImproveNewCadaster', 'CreateNewCadaster', 'RetireAndCreateCadaster3D', 'FreeEdit']:
        AddError(f"{timestamp()} | Task type is invalid")
        return False

    else:

        if task == 'ImproveCurrentCadaster':
            vals: df = DataFrame(data= {'Validation': ['Signed-in', 'Process Exist', 'Status Check', 'Areas Check'],
                                        'Results': [user_is_signed_in(),
                                                    process_exist(ProcessName),
                                                    validate_status(ProcessName, desire_status=[4, 6, 10, 13]),
                                                    validate_stated_areas(ProcessName)]})

        elif task == 'RetireAndCreateCadaster':
            vals: df = DataFrame(data= {'Validation': ['Signed-in', 'Process Exist', 'Status Check', 'Final Parcels Numbers Check', 'Absorbing Blocks Check', 'Areas Check'],
                                        'Results': [user_is_signed_in(),
                                                    process_exist(ProcessName),
                                                    validate_status(ProcessName, desire_status=[5]),
                                                    final_parcels_obtained(ProcessName),
                                                    absorbing_block_exist(ProcessName),
                                                    validate_stated_areas(ProcessName)]})

        elif task == 'ImproveNewCadaster':
            vals: df = DataFrame(data= {'Validation': 'Results',
                                        'Signed-in': user_is_signed_in()},
                                 index= [0])

        elif task == 'CreateNewCadaster':
            vals: df = DataFrame(data= {'Validation': 'Results',
                                        'Signed-in': user_is_signed_in()},
                                 index= [0])

        elif task == 'RetireAndCreateCadaster3D':
            vals: df = DataFrame(data= {'Validation': 'Results',
                                        'Signed-in': user_is_signed_in(),
                                        'Process Exist': process_exist(ProcessName),
                                        'Status Check': validate_status(ProcessName, desire_status=[5]),
                                        'Final Parcels Numbers Check': final_parcels_obtained(ProcessName),
                                        'Final Substractions Numbers Check': final_substractions_obtained(ProcessName),
                                        'Substantiated 2D Parcels Check': validate_substantiated_Parcels2D(ProcessName),
                                        'Substantiated 3D Parcels Check': validate_substantiated_Parcels3D(ProcessName),
                                        'Absorbing Blocks Check': absorbing_block_exist(ProcessName)},
                                 index= [0])

        if task == 'FreeEdit':
            vals: df = DataFrame(data= {'Validation': 'Results',
                                        'Signed-in': user_is_signed_in()},
                                 index= [0])

        # Summary report
        has_invalid: bool = (vals == 'Invalid').values.any()
        if has_invalid:
            vals: df = vals.replace({'Valid': '✅', 'Invalid': '❌'})
            AddTabularMessage(vals)
            return False

        else:
            return True
