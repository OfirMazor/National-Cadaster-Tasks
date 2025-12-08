from Utils.Configs import CNFG
from Utils.Helpers import get_ProcessGUID, get_ProcessType, get_RecordGUID, start_editing, stop_editing, timestamp, get_DomainValue, get_layer,rewrite_record_data,reopen_map
from Utils.Validations import user_is_signed_in, process_exist
from arcpy.da import SearchCursor, UpdateCursor
from arcpy import AddMessage, AddError,GetPortalInfo, GetActivePortalURL,RefreshLayer
from arcpy.da import SearchCursor
from arcpy.mp import ArcGISProject
from arcpy.management import GetCount






def check_for_existing_records_data(ProcessName:str, TaskType:str = 'CreateNewCadaster' or 'ImproveNewCadaster') -> bool:
    '''Checks if the specified process name already exists in the CadasterRecordsBorder table. 
    If yes, it deletes the existing record and all the features that connected to it

    Parameters:
    - ProcessName (str): The name of the process to check for existing records data
    - TaskType (str): The Task's type, CreateNewCadaster or ImproveNewCadaster

    Returns:
    - - str: 'Valid' if the current process type is valid, 'Invalid' otherwise.

    '''
    
    record_exist_check  = new_cadaster_record_is_duplicated(ProcessName)

    if record_exist_check == 'Invalid':
       delete_records_related_data(ProcessName, TaskType)
       return True
    return False





def validate_new_cadastre_process_type(ProcessName:str, TaskType:str = 'CreateNewCadaster' or 'ImproveNewCadaster') -> str:
    '''
    Validates the process type of a specified process before loading into records.
    This function queries the 'CadasterProcessBorders' table in the Parcel Fabric Database
    for the specified 'ProcessName' and checks if the current process type is 9 or 15 (according to TaskType parameter)
    If the process type is valid, the function returns 'Valid'; otherwise, it raises an arcpy error
    and returns 'Invalid'.
    
    Parameters:
    - ProcessName (str): The name of the process to be validated.
    - TaskType (str): The Task's type, CreateNewCadaster or ImproveNewCadaster

    Returns:
    - - str: 'Valid' if the current process type is valid, 'Invalid' otherwise.
    '''

    fields = ['ProcessName', 'ProcessType']
    query = f''' ProcessName = '{ProcessName}' '''

    if TaskType == 'CreateNewCadaster':
        expected_process_type_codes = [9,10]
    elif TaskType == 'ImproveNewCadaster':
        expected_process_type_codes = [15]
    else:
        AddError(f'{timestamp()} | ❌ The used TaskType parameter is illegal')
    
    expected_process_type_domain_values = []
    for code in expected_process_type_codes:
        expected_process_type_domain_values.append(get_DomainValue('ProcessType', code))
    expected_process_type_domain_values_str = ', '.join(expected_process_type_domain_values)

    #current_process_type_code = [row[1] for row in SearchCursor(f'{CNFG.ParcelFabricDataset}{CNFG.OwnerName}CadasterProcessBorders', fields, where_clause = query)][0]
    current_process_type_code = get_ProcessType(ProcessName)
    current_process_type_domain_value = get_DomainValue('ProcessType',current_process_type_code)

    if current_process_type_code in expected_process_type_codes:
        AddMessage(f'{timestamp()} | ✅ Process type is valid')
        return 'Valid'
    else:
        if TaskType == 'CreateNewCadaster':
            AddError(f'{timestamp()} | ❌ Process type is {current_process_type_domain_value} but must be one of {expected_process_type_domain_values_str} before loading into records')
        else:
            AddError(f'{timestamp()} | ❌ Process type is {current_process_type_domain_value} but must be {expected_process_type_domain_values_str} before loading into records')
        return 'Invalid'


def validate_new_cadaster_status(ProcessName:str, TaskType:str = 'CreateNewCadaster' or 'ImproveNewCadaster') -> str:
    '''
    Validates the status of a specified process before loading into records.
    This function queries the 'CadasterProcessBorders' table in the Parcel Fabric Database
    for the specified 'ProcessName' and checks if the current status is 103 or 13 (according to TaskType parameter)
    If the status is valid, the function returns 'Valid'; otherwise, it raises an arcpy error
    and returns 'Invalid'.
    
    Parameters:
    - ProcessName (str): The name of the process to be validated.
    - TaskType (str): The Task's type, CreateNewCadaster or ImproveNewCadaster

    Returns:
    - - str: 'Valid' if the current status is 103, 'Invalid' otherwise.
    '''

    fields = ['ProcessName', 'Status']
    query = f''' ProcessName = '{ProcessName}' '''

    if TaskType == 'CreateNewCadaster':
        current_process_type_code = get_ProcessType(ProcessName)
        if current_process_type_code == 9:
            expected_status_code = 103
        else: # current_process_type_code==10
            expected_status_code = 5
    elif TaskType == 'ImproveNewCadaster':
        expected_status_code = 13
    else:
        AddError(f'{timestamp()} | ❌ The used TaskType parameter is illegal')

    expected_status_domain_value = get_DomainValue('ProcessStatus',expected_status_code)
    
    #current_status_code = [row[1] for row in SearchCursor(CNFG.ParcelFabricDatabase + "CadasterProcessBorders", fields, where_clause = query)][0]
    current_status_code = [row[1] for row in SearchCursor(f'{CNFG.ParcelFabricDataset}{CNFG.OwnerName}CadasterProcessBorders', fields, where_clause = query)][0]
    current_status_domain_value = get_DomainValue('ProcessStatus',current_status_code)

    if current_status_code == expected_status_code:
        AddMessage(f'{timestamp()} | ✅ Process status is valid')
        return 'Valid'
    else:
        AddError(f'{timestamp()} | ❌ Process status is {current_status_domain_value} but must be {expected_status_domain_value} before loading into records')
        return 'Invalid'

def block_exist(ProcessName:str) -> str:
    '''
    Checks if a cadstral block with the specified `ProcessName` (as Name) exists in the Blocks table.

    Parameters:
        ProcessName (str): The name of the block to search for.

    Returns:
        str: 'Valid' if a block with the given `ProcessName` (as Name) exists, 'Invalid' otherwise.
    ''' 
    
    #query = [row[0] for row in SearchCursor(CNFG.ParcelFabricDataset + 'Blocks', 'Name', f""" Name = '{ProcessName}' AND IsTax=0 """)]
    query = [row[0] for row in SearchCursor(f'{CNFG.ParcelFabricDataset}{CNFG.OwnerName}Blocks', 'Name', f""" Name = '{ProcessName}' AND IsTax=0 """)]

    count = len(query)
    del query
    
    if count == 0:
        AddError(f'{timestamp()} | ❌ Block {ProcessName} does not exist in the Blocks table among the non-tax blocks')
        return 'Invalid'
    elif count == 1:
        AddMessage(f'{timestamp()} | ✅ Block {ProcessName} found')
        return 'Valid'
    else:
        AddError(f'{timestamp()} | ❌ Debug: Count of query in block_exist function: {count}')
        return 'Invalid'
    
def new_cadaster_validation_set(ProcessName:str, TaskType:str = 'CreateNewCadaster' or 'ImproveNewCadaster') -> bool:
    '''
    Group the tests function and return True if all tests are valid.
    
    Parameters:
        ProcessName (str): The name of the process/record to validate.
        TaskType (str): The Task's type, CreateNewCadaster or ImproveNewCadaster
    
    Returns:
        bool:True if all tests are valid, False otherwise.
    '''

    AddMessage(f'\n ⭕ Validating: \n')
    
    user_is_signed_in()
    process_exist_check = process_exist(ProcessName)

    if process_exist_check=='Valid':
        process_type_check = validate_new_cadastre_process_type(ProcessName, TaskType)
        status_check      = validate_new_cadaster_status(ProcessName, TaskType)
    else:
        process_type_check = 'Invalid'
        status_check = 'Invalid'
        AddError(f'{timestamp()} | ❌ Process doesn\'t exist, can\'t perform process type and status checks')

    if TaskType == 'CreateNewCadaster':    
        block_exist_check  = block_exist(ProcessName)

        if 'Invalid' in [status_check, process_type_check,process_exist_check,block_exist_check]:
            AddError(f'{timestamp()} | ❌ Validation check failed: \n Status Check: {status_check}, Process Type Check: {process_type_check}, Process Exist Check: {process_exist_check},  Block Exist Check: {block_exist_check}')
            return False
        else:
            return True
    else:

        if 'Invalid' in [status_check, process_type_check,process_exist_check]:
            AddError(f'{timestamp()} | ❌ Validation check failed: \n Status Check: {status_check}, Process Type Check: {process_type_check}, Process Exist Check: {process_exist_check}')
            return False
        else:
            return True

def new_cadaster_record_is_duplicated(ProcessName:str) -> str:
    '''
    Checks if a record with the specified `ProcessName` exists in the Parcel Fabric Records table.

    Parameters:
        ProcessName (str): The name of the process to search for.

    Returns:
        str: Invalid if a record with the given `ProcessName` exists, 'Valid' otherwise.
    '''
    Records_layer = get_layer('גבולות רישומים')
    
    query = [row[0] for row in SearchCursor(Records_layer, 'Name', f""" Name = '{ProcessName}' """)]
    count = len(query)
    del [query, Records_layer]
    
    if count == 0:
        AddMessage(f'{timestamp()} | ✅ Record is not duplicated')
        return 'Valid'
    elif count > 0:
        AddMessage(f'{timestamp()} | 🗑️ Record name {ProcessName} already exist in Records table:')
        return 'Invalid'
    else:
        AddError(f'{timestamp()} | ❌ Debug: Count of query in new_cadaster_record_is_duplicated function: {count}')
        return 'Invalid'


def features_created_by_record_exist(ProcessName:str,feature_class_name:str) -> str:
    '''
    Checks if features created by the record with the specified `ProcessName` exist in the Parcel Fabric table.

    Parameters:
        ProcessName (str): The name of the process to search for.
        feature_class_name (str): The name of the feature class to search for.

    Returns:
        str: Invalid if features created by the given `ProcessName` exist, 'Valid' otherwise.
    '''  

    record_GUID = get_RecordGUID(ProcessName)

    query = [row[0] for row in SearchCursor(f'{CNFG.ParcelFabricDataset}{CNFG.OwnerName}{feature_class_name}', 'GlobalID', f""" CreatedByRecord = '{record_GUID}' """)]
    count = len(query)
    del query
    
    if count == 0:
        return 'Valid'
    elif count > 0:
        return 'Invalid'
    else:
        AddError(f'{timestamp()} | ❌ Debug: Count of query in features_created_by_record_exist function: {count} in {feature_class_name} table')
        return 'Invalid'
    

    
def features_retired_by_record_exist(ProcessName:str, feature_class_name:str) -> str:
    '''
    Checks if there are any features in the given feature class that were retired by given `ProcessName`

    Parameters:
        ProcessName (str): The name of the process to search for.
        feature_class_name (str): The name of the feature class to search for.

    Returns:
        str: Invalid if features retired by the given `ProcessName` exist, 'Valid' otherwise.
    '''  

    record_GUID = get_RecordGUID(ProcessName)

    query = [row[0] for row in SearchCursor(f'{CNFG.ParcelFabricDataset}{CNFG.OwnerName}{feature_class_name}', 'GlobalID', f""" RetiredByRecord = '{record_GUID}' """)]
    count = len(query)
    del query
    
    if count == 0:
        return 'Valid'
    elif count > 0:
        return 'Invalid'
    else:
        AddError(f'{timestamp()} | ❌ Debug: Count of query in features_retired_by_record_exist function: {count} in {feature_class_name} table')
        return 'Invalid'
    



def delete_records_related_data(ProcessName:str, TaskType:str = 'CreateNewCadaster' or 'ImproveNewCadaster') -> None:
    '''
    Recieves the process name and deletes it from CadasterRecordsBorders and all related data created by it in Parcels2D, Parcels2DFronts and BorderPoints
    Additionaly restores the features that were retired by current process and set them to active
    
    Parameters:
    - ProcessName (str): The name of the process for which the related data should be deleted
    - TaskType (str): The Task's type, CreateNewCadaster or ImproveNewCadaster

    Returns:
    - - str: 'Valid' if the current process type is valid, 'Invalid' otherwise.'''
    

    Records_layer = get_layer('גבולות רישומים') 
    RecordGuid = get_RecordGUID(ProcessName)
    

    if TaskType == 'CreateNewCadaster':
        Parcels_layer = get_layer('חלקות')
        Fronts_layer = get_layer('חזיתות')
        Points_layer = get_layer('נקודות גבול') 
        Retired_Parcels_layer = get_layer('חלקות מבוטלות')
        Retired_Fronts_layer = get_layer('חזיתות מבוטלות') 
        Retired_Points_layer = get_layer('נקודות גבול מבוטלות')
        Retired_Blocks_layer = get_layer('גושים מבוטלים') 


        # Open an edit session
        editor = start_editing(CNFG.ParcelFabricDatabase)
        
        if features_created_by_record_exist(ProcessName, 'Parcels2D')=='Invalid':
            with UpdateCursor(Parcels_layer, "GlobalID",f""" CreatedByRecord = '{RecordGuid}'""") as cursor:
                count = 0
                for row in cursor:
                    cursor.deleteRow()
                    count = count + 1
                AddMessage(f'                Deleted {count} existing parcels previously created by process {ProcessName}')    
    

        if features_created_by_record_exist(ProcessName, 'Parcels2DFronts')=='Invalid':
            with UpdateCursor(Fronts_layer, "GlobalID",f""" CreatedByRecord = '{RecordGuid}'""") as cursor:
                count = 0
                for row in cursor:
                    cursor.deleteRow()
                    count = count + 1
                AddMessage(f'                Deleted {count} existing fronts previously created by process {ProcessName}')

        if features_created_by_record_exist(ProcessName, 'BorderPoints')=='Invalid':
            with UpdateCursor(Points_layer, "GlobalID",f""" CreatedByRecord = '{RecordGuid}'""") as cursor:
                count = 0
                for row in cursor:
                    cursor.deleteRow()
                    count = count + 1
                AddMessage(f'                Deleted {count} existing points previously created by process {ProcessName}')

        if features_retired_by_record_exist(ProcessName,'BorderPoints')=='Invalid':
            with UpdateCursor(Retired_Points_layer, ["GlobalID","RetiredByRecord"],f""" RetiredByRecord = '{RecordGuid}'""") as cursor:
                count = 0
                for row in cursor:
                    row[1] = None
                    cursor.updateRow(row)
                    count = count + 1
                AddMessage(f'                Restored {count} points previously retired by process {ProcessName}')

        if features_retired_by_record_exist(ProcessName, 'Parcels2DFronts')=='Invalid':
            with UpdateCursor(Retired_Fronts_layer, ["GlobalID","RetiredByRecord"],f""" RetiredByRecord = '{RecordGuid}'""") as cursor:
                count = 0
                for row in cursor:
                    row[1] = None
                    cursor.updateRow(row)
                    count = count + 1
                AddMessage(f'                Restored {count} fronts previously retired by process {ProcessName}')

        if features_retired_by_record_exist(ProcessName, 'Parcels2D')=='Invalid':
            with UpdateCursor(Retired_Parcels_layer, ["GlobalID","RetiredByRecord","CancelProcessType"],f""" RetiredByRecord = '{RecordGuid}' """) as cursor:
                count = 0
                for row in cursor:
                    row[1] = None
                    row[2] = None
                    cursor.updateRow(row)
                    count = count + 1
                AddMessage(f'                Restored {count} parcels previously retired by process {ProcessName}')

        if features_retired_by_record_exist(ProcessName, 'Blocks')=='Invalid':
            with UpdateCursor(Retired_Blocks_layer, ["GlobalID","RetiredByRecord"],f""" RetiredByRecord = '{RecordGuid}' """) as cursor:
                count = 0
                for row in cursor:
                    row[1] = None
                    cursor.updateRow(row)
                    count = count + 1
                AddMessage(f'                Restored {count} blocks previously retired by process {ProcessName}')

        stop_editing(editor)

    #rewrite_record_data(ProcessName)
    '''
    editor = start_editing(CNFG.ParcelFabricDatabase)
    
    with UpdateCursor(Records_layer, "GlobalID",f""" GlobalID = '{RecordGuid}'""") as cursor:
        for row in cursor:
            cursor.deleteRow()
        AddMessage(f'                Deleted existing record with ProcessName {ProcessName}')

    stop_editing(editor)
    '''
    RefreshLayer(Records_layer)
    reopen_map()
def layer_exists_(layer_name: str) -> bool:
    '''
    Checks if a layer with the specified name exists in the current map.

    Parameters:
        layer_name (str): The name of the layer to check.

    Returns:
        bool: True if the layer exists, False otherwise.
    '''
    CurrentMap = ArcGISProject("CURRENT").activeMap
    layers = CurrentMap.listLayers()
    for layer in layers:
        if layer.name == layer_name:
            return True
    return False

def layer_exists(layer_name: str)-> bool:
    """
    Check if a layer with the given name exists in the current map.

    Parameters:
        layer_name (str): The name of the layer to check.

    Returns:
        bool: True if the layer exists, False otherwise.
    """
    # Get the current ArcGIS Pro project
    aprx = ArcGISProject("CURRENT")
    
    # Get the active map
    active_map = aprx.activeMap
    if active_map is None:
        raise ValueError("No active map found.")
    
    # Check for the layer in the active map
    for layer in active_map.listLayers():
        if layer.name == layer_name:
            return True
    
    return False




def creating_record_is_duplicated(ProcessName:str) -> bool:
    '''
    Checks if a record with the specified `ProcessName` exists in the Parcel Fabric Records table.

    Parameters:
        ProcessName (str): The name of the process to search for.

    Returns:
        str: True if a record with the given `ProcessName` exists, False otherwise.
    '''
    Records_layer = get_layer('גבולות רישומים')
    
    query = [row[0] for row in SearchCursor(Records_layer, 'Name', f""" Name = '{ProcessName}' """)]
    count = len(query)
    del [query, CurrentMap, Records_layer]
    
    if count == 0:
        return False
    if count == 1:
        return True
    else:
        AddError(f'{timestamp()} | ❌ Found {count} records with the name {ProcessName}')
        
 
 



   


  
def features_exist(layer) -> None:
    '''
    Validate layer is not empty.

    Parameters:
        layer: The layer object

    Returns:
        None.
    '''
    
    count = int(GetCount(layer).getOutput(0))
    if count < 1:
        AddError(f'{timestamp()} | ❌ Layer {layer.name} is empty, verify the process data content before starting the task')
    else:
        AddMessage(f'{timestamp()} | ✅ {layer.name} contains {count} features')




