from os import startfile
from Utils.Configs import CNFG
from Utils.Helpers import create_shelf, get_ProcessType, get_RecordGUID, get_BlockGUID, start_editing, stop_editing, zoom_to_aoi,  \
    filter_to_aoi, get_FinalParcel, reopen_map, start_editing, stop_editing, cursor_length, \
    timestamp, activate_record, get_DomainValue, get_layer, set_priority, rewrite_record_data, drop_layer,drop_dbtable, load_to_records
from Utils.UpdateAttributes import update_record_status
from Utils.NewCadasterHelpers import append_process_to_records, append_settled_parcels, append_new_fronts, append_new_border_points,\
    count_features_in_group, filter_process_layers_group,update_blocks_geometry_by_active_parcels,append_first_registration_parcels, \
    insert_process_to_records, insert_settled_parcels, insert_new_fronts, insert_new_border_points, insert_first_registration_parcels,is_tax_process,is_guid_txt_file_exists, get_RecordGUID_NewCadaster
from Utils.Reports import compute_matching_points_report
from Utils.ValidationsNewCadaster import new_cadaster_validation_set, layer_exists, check_for_existing_records_data
from Utils.VersionManagement import open_version
from StartTaskRetireAndCreateCadaster import load_new_parcels
from RetireSelectedUnsettledFeatures import RetireSelectedFeatures
from arcpy import AddMessage, AddError, AddWarning,GetParameterAsText, env as ENV
from arcpy.management import SelectLayerByLocation as SelectByLocation, SelectLayerByAttribute as SelectByAttribute, GetCount
from arcpy.da import SearchCursor, UpdateCursor
from arcpy.mp import ArcGISProject


ENV.preserveGlobalIds = False


def add_or_update_record(processName:str, recordExists:bool) -> None:
    '''
    Adds a new record or updates an existing one in the CadasterRecordsBorder table.
    '''
    if recordExists:
        if get_ProcessType(processName) == 10: #(רישום ראשון)
            update_record_status(processName, new_status=5) 
        else:
            rewrite_record_data(processName)
    else:
        load_to_records(processName)
        #num_of_appended_features = append_process_to_records(processName)
        #if num_of_appended_features==0:
        #    AddMessage(f"{timestamp()} | ⚠️ Couldn't load the process {processName} into Records")
        #else:
        #    AddMessage(f'{timestamp()} | ⚡ The process {processName} was loaded into Records')

def retire_within_tax_features(processName:str) -> None:
    ''' 
    Retiring all tax features which are completely within the given process border

    '''
    AddMessage('\n ⭕ Looking for unsettled features to retire \n')
    #TODO check that the process parcels are not tax

    Process_border_layer = get_layer('גבול תכנית')


    if is_tax_process(processName):
        AddMessage(f"{timestamp()} | The process {processName} contains tax parcels, so no retirement attempt will be made")
    else:
        if layer_exists('חלקות לא מוסדרות'):
            RetireSelectedFeatures(processName)
        else:
            AddMessage(f"{timestamp()} | No unsettled parcels layer found, so no retirement attempt will be made")

            





def update_settled_block(processName:str) -> None:
    ''' 
    Updating current block's data (Shape,LastSetteledParcel,CreatedByRecord,BlockStatus,LandType)

    '''
    

    Process_border_layer = get_layer('גבול תכנית')
    Block_layer = get_layer('גוש הסדר')
    Parcels_layer = get_layer('חלקות ביסוס')

    RecordGUID = get_RecordGUID_NewCadaster(processName)

    editor = start_editing(CNFG.ParcelFabricDatabase)
    
    AddMessage(f'{timestamp()} | ♻️ Updating attributes for block {processName}:') 
   
    # Get the single feature from Process_border_layer
    with SearchCursor(Process_border_layer, field_names="SHAPE@") as cursor:
        process_geometry = cursor.next()[0]
 
    # Find the maximum value in the ParcelNumber field
    max_parcel_number = None
    with SearchCursor(Parcels_layer, ["ParcelNumber"]) as cursor:
        parcel_numbers = [row[0] for row in cursor]

    if parcel_numbers:
        max_parcel_number = max(parcel_numbers)


    is_updated = False
    # Update the CreatedByRecord, LandType, and BlockStatus fields in the single feature of the Block_layer
    with UpdateCursor(Block_layer, ["SHAPE@","CreatedByRecord", "LandType", "BlockStatus", "LastSetteledParcel"]) as cursor:
        row = next(cursor, None)  # Safely get the first row or None
        if row:
            row[0] = process_geometry
            row[1] = RecordGUID
            row[2] = 1
            row[3] = 11
            row[4] = max_parcel_number
            cursor.updateRow(row)
            is_updated = True


    if is_updated:
        LandTypeDomainValue = get_DomainValue('LandType', 1)
        BlockStatusDomainValue = get_DomainValue('BlockStatus', 11)

        AddMessage(f'                Geometry was updated')
        AddMessage(f'                Created By Record = {RecordGUID}')
        AddMessage(f'                Land Type = {LandTypeDomainValue}')
        AddMessage(f'                Block Status = {BlockStatusDomainValue}')
        AddMessage(f'                Last Settled Parcel = {max_parcel_number}')
    else:
        AddWarning(f'                Was unable to update the block\'s attributes')

    stop_editing(editor)




def load_data_to_sequence_layers(ProcessName:str, TaskType:str = 'CreateNewCadaster' or 'ImproveNewCadaster') -> None:
    ''' 
    
        
    Parameters:
        ProcessName (str): The name of the process
        TaskType (str): The Task's type, CreateNewCadaster or ImproveNewCadaster
        
    '''


    if TaskType == 'CreateNewCadaster':
        RecordGUID = get_RecordGUID_NewCadaster(ProcessName)

        new_points_dq = None
        new_fronts_dq = None

        if layer_exists('נקודות חדשות'):
            new_points_layer = get_layer('נקודות חדשות')
            new_points_dq = new_points_layer.definitionQuery
            del new_points_layer

        if layer_exists('חזיתות חדשות'):
            new_fronts_layer = get_layer('חזיתות חדשות')
            new_fronts_dq = new_fronts_layer.definitionQuery
            del new_fronts_layer

        if get_ProcessType(ProcessName) == 9:
            AddMessage(f'{timestamp()} | Loading settled parcels...')
            num_of_appended_features = append_settled_parcels(ProcessName)
        else:
            AddMessage(f'{timestamp()} | Loading first registration parcels...')
            num_of_appended_features = insert_first_registration_parcels(ProcessName)
            #load_new_parcels(ProcessName)

        if not num_of_appended_features:
            AddMessage(f"{timestamp()} | ⚠️ Couldn't load the parcels from process {ProcessName} into record parcels layer")
        else:
            AddMessage(f'{timestamp()} | ⚡ Loaded {num_of_appended_features} parcels for record {ProcessName}')
            LandTypeDomainValue = get_DomainValue('LandType', 1)
            AddMessage(f'{timestamp()} | ♻️ The following fields were updated for the loaded parcels:') 
            AddMessage(f'                Created By Record = {RecordGUID}') 
            AddMessage(f'                Land Type = {LandTypeDomainValue}') 
        
        if new_points_dq is not None:
            AddMessage(f'{timestamp()} | Loading new points...')
            num_of_appended_features = insert_new_border_points(ProcessName, new_points_dq)
            if not num_of_appended_features:
                AddMessage(f"{timestamp()} | ⚠️ Couldn't load the points from process {ProcessName} into record parcels layer")
            else:
                AddMessage(fr'{timestamp()} | ⚡ loaded {num_of_appended_features} new points for record {ProcessName}')


        if new_fronts_dq is not None:
            AddMessage(f'{timestamp()} | Loading new fronts...')
            num_of_appended_features = insert_new_fronts(ProcessName, new_fronts_dq)
            if not num_of_appended_features:
                AddMessage(f"{timestamp()} | ⚠️ Couldn't load the fronts from process {ProcessName} into record parcels layer")
            else:
                AddMessage(fr'{timestamp()} | ⚡ loaded {num_of_appended_features} new fronts for record {ProcessName}')


def display_process_data(ProcessName:str, TaskType:str = 'CreateNewCadaster' or 'ImproveNewCadaster') -> None:
    '''
    Display in-process cadaster data in the current ArcGIS project based on the specified cadaster process name.
    This function searches for the specified cadaster process name in the CadasterProcessBorders table.
    If the process name is found and is unique, it adds relevant layers (parcels, process borders, fronts, points, tax blocks and tax parcels)
    to the current map in the ArcGIS project. The map view is then panned to the extent of the added layers.
    If the specified process name is not found or is duplicated, appropriate error messages are raised.

    Parameters:
    - ProcessName (str): The name of the cadaster process.
    - TaskType (str): The Task's type, CreateNewCadaster or ImproveNewCadaster

    Returns:
    None
    '''
    
    CurrentMap = ArcGISProject("CURRENT").activeMap

    AddMessage('\n ⭕ Loading data: \n')

    CurrentMap.addDataFromPath(fr'{CNFG.LayerFiles}NewCadasterLayers.lyrx')


    if TaskType == 'CreateNewCadaster':
        
        if get_ProcessType(ProcessName) == 9: #(הסדר)

            drop_dbtable('פעולות בתכנית')
        else: #current_process_type_code==10 (רישום ראשון)
            drop_layer('גוש הסדר')



    else: #TaskType == 'ImproveNewCadaster'
            drop_dbtable('פעולות בתכנית')
            drop_layer('גוש הסדר')
            drop_layer('חלקות ביסוס')
            drop_layer('נקודות חדשות')
            drop_layer('חזיתות חדשות')
    

    main_group_layer = get_layer('תכנית')
    main_group_layer.name = f'{ProcessName} תכנית'

    filter_process_layers_group(ProcessName, TaskType)

    if TaskType == 'CreateNewCadaster':
        if get_ProcessType(ProcessName) == 9: #(הסדר)
            required_layers_list = ['גוש הסדר','חלקות ביסוס', 'חזיתות ביסוס', 'נקודות ביסוס', 'גבול תכנית']
        else: #current_process_type_code==10 (רישום ראשון)
            required_layers_list = ['חלקות ביסוס', 'חזיתות ביסוס', 'נקודות ביסוס', 'גבול תכנית']
    else: #TaskType == 'ImproveNewCadaster' (תת"ג להסדר)
        required_layers_list = ['חזיתות ביסוס', 'נקודות ביסוס', 'גבול תכנית', 'גושים מוסדרים', 'חלקות מוסדרות']


    count_features_in_group(main_group_layer, required_layers_list)

    del [main_group_layer, required_layers_list ,CurrentMap]


  



    

def start_task_CreateNewCadaster(ProcessName:str, ComputeReport:str, TaskType:str = 'CreateNewCadaster' or 'ImproveNewCadaster', auto_retire_tax_features:str = 'false') -> None:

    '''
    Executing the main task function

    Parameters:
    - ProcessName (str): The name of the cadaster process.
    - TaskType (str): The Task's type, CreateNewCadaster or ImproveNewCadaster

    Returns:
    None
    '''
    set_priority()
    if new_cadaster_validation_set(ProcessName, TaskType) == True:

        shelf = create_shelf(ProcessName)
        open_version(ProcessName)
        startfile(r''+shelf)
        record_exists = check_for_existing_records_data(ProcessName, TaskType)
        add_or_update_record(ProcessName, record_exists)
        display_process_data(ProcessName, TaskType)
        load_data_to_sequence_layers(ProcessName, TaskType)
        activate_record(ProcessName)
        if TaskType == 'CreateNewCadaster':
            if get_ProcessType(ProcessName) == 9: #(הסדר)
                update_settled_block(ProcessName)
            else: # current_process_type_code==10 (רישום ראשון)
                block_guid = get_BlockGUID(ProcessName)
                update_blocks_geometry_by_active_parcels(block_guid)

        filter_to_aoi(ProcessName)
        zoom_to_aoi()

        if auto_retire_tax_features == 'true':
            retire_within_tax_features(ProcessName)
        
        if ComputeReport == 'true':
            compute_matching_points_report(ProcessName, 'CreateNewCadaster')
            startfile(fr'{shelf}/PointsDistanceReport-{ProcessName.replace("/","_")}.xlsx')

        

if __name__ == "__main__":

    ProcessName = GetParameterAsText(0)
    TaskType = GetParameterAsText(1)
    ComputeReport = GetParameterAsText(2)

    if TaskType == 'CreateNewCadaster':
        auto_retire_tax_features = GetParameterAsText(3)
    else:
        auto_retire_tax_features = None

    start_task_CreateNewCadaster(ProcessName, ComputeReport, TaskType, auto_retire_tax_features)

