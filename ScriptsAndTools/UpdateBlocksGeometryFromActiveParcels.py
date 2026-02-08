from os import startfile
from Utils.Configs import CNFG
from Utils.Helpers import create_shelf, get_ProcessType, get_RecordGUID, get_BlockGUID, start_editing, stop_editing, zoom_to_aoi,  \
    filter_to_aoi, get_FinalParcel, reopen_map, start_editing, stop_editing, cursor_length, \
    timestamp, activate_record, get_DomainValue, get_layer, set_priority, rewrite_record_data, get_ActiveRecord
from Utils.UpdateAttributes import update_record_status
from Utils.NewCadasterHelpers import get_block_parameters_by_guid,update_blocks_geometry_by_active_parcels,get_RecordGUID_NewCadaster,append_process_to_records, append_settled_parcels, append_new_fronts, append_new_border_points,\
    count_features_in_group, filter_process_layers_group,append_first_registration_parcels, \
    insert_process_to_records, insert_settled_parcels, insert_new_fronts, insert_new_border_points, insert_first_registration_parcels

from Utils.Reports import compute_matching_points_report
from Utils.ValidationsNewCadaster import new_cadaster_validation_set, layer_exists, check_for_existing_records_data
from Utils.VersionManagement import open_version
from StartTaskRetireAndCreateCadaster import load_new_parcels
from RetireSelectedUnsettledFeatures import RetireSelectedFeatures
from arcpy import AddMessage, AddError, AddWarning,GetParameterAsText, GetParameter, env as ENV
from arcpy.management import SelectLayerByLocation as SelectByLocation, SelectLayerByAttribute as SelectByAttribute, GetCount, Dissolve, Delete
from arcpy.da import SearchCursor, UpdateCursor
from arcpy.mp import ArcGISProject


ENV.preserveGlobalIds = False

def update_blocks_geometry_from_active_parcels(Independent: bool, BlockNumber: int, SubBlockNumber: int, IsTax:bool, ProcessName: str|None) -> None:
    ''' 
    Updating the geometry of the block by the active parcels

    '''

    if IsTax:
        IsTax = 1
    else:
        IsTax = 0
    
    parcels_layer = get_layer('חלקות')
    blocks_layer = get_layer('גושים')
    blocks_to_update = []

    if not Independent:
        record_GUID = get_ActiveRecord('GUID')

        if not record_GUID:
            AddError('No active record found, please activate a record in the Manage Records panel or use independent mode with manual input')
            return
        records_layer = get_layer('גבולות רישומים')
        SelectByAttribute(records_layer,where_clause=f"GlobalID = '{record_GUID}'",selection_type='NEW_SELECTION')
    
        SelectByLocation(blocks_layer,overlap_type='INTERSECT',select_features=records_layer,search_distance='1 Meters', selection_type='NEW_SELECTION')
        
        record_name = get_ActiveRecord('Name')
        block_GUID = get_BlockGUID('ProcessName',record_name)
        # removing the settled block from the selection
        if get_ProcessType(record_name) == 9: 
            if block_GUID:
                SelectByAttribute(blocks_layer,where_clause=f"GlobalID = '{block_GUID}'",selection_type='REMOVE_FROM_SELECTION')
        num_of_blocks = int(GetCount(blocks_layer).getOutput(0))
        if num_of_blocks > 0:
            with SearchCursor(blocks_layer, field_names=["GlobalID"]) as cursor:
                for row in cursor:
                    blocks_to_update.append(row[0])
        SelectByAttribute(blocks_layer,selection_type='CLEAR_SELECTION')
        SelectByAttribute(records_layer,selection_type='CLEAR_SELECTION')


    else:
        if not ProcessName:
            AddError('Process name must be provided when Independent is True')
            return
        record_GUID = get_RecordGUID_NewCadaster(ProcessName)
        if not record_GUID:
            AddError(f'No record was found for process {ProcessName}')
            return
        SelectByAttribute(blocks_layer,where_clause=f"BlockNumber = {BlockNumber} AND SubBlockNumber = {SubBlockNumber} AND IsTax = {IsTax}",selection_type='NEW_SELECTION')
        num_of_blocks = int(GetCount(blocks_layer).getOutput(0))
        if num_of_blocks == 0:
            AddError(f'No block found with BlockNumber {BlockNumber}, SubBlockNumber {SubBlockNumber} and IsTax {IsTax}')
            return
        with SearchCursor(blocks_layer, field_names=["GlobalID"]) as cursor:
            for row in cursor:
                blocks_to_update.append(row[0])
        SelectByAttribute(blocks_layer,selection_type='CLEAR_SELECTION')


    if len(blocks_to_update) == 0:
        AddMessage('No blocks found for geometry update')
        return
    for block_guid in blocks_to_update:
        update_status = update_blocks_geometry_by_active_parcels(block_guid,record_GUID)
        block_parameters = get_block_parameters_by_guid(block_guid)
        tax_addition = ("", " (Tax)")[block_parameters[2]]
        block_name = f"{block_parameters[0]}/{block_parameters[1]}{tax_addition}"
        if update_status==1:
            AddMessage(f'{timestamp()} | Geometry updated for block {block_name}')
        elif update_status==2:
            AddMessage(f'{timestamp()} | No active parcels found for block {block_name}, the block was still active and hence retired by record {Record_GUID}')
        elif update_status==0:
            AddWarning(f'{timestamp()} | Block {block_name} was already retired while some of its parcels were active or doesn\'t exist, please review data integrity.')
        else:
            AddError(f'{timestamp()} | An error occurred while updating geometry for block {block_name}')

if __name__ == "__main__":

    Independent = GetParameter(0)
    BlockNumber = GetParameter(1)
    SubBlockNumber = GetParameter(2)
    IsTax = GetParameter(3)
    ProcessName = GetParameterAsText(4)

    update_blocks_geometry_from_active_parcels(Independent, BlockNumber, SubBlockNumber, IsTax, ProcessName)

