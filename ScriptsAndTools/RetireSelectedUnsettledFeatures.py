from Utils.Configs import CNFG
from Utils.Helpers import get_RecordGUID, start_editing, stop_editing, timestamp, reopen_map,get_layer, get_ActiveRecord, Type2CancelType,get_ProcessType
from Utils.NewCadasterHelpers import get_ProcessName, update_blocks_geometry_by_active_parcels, is_tax_process, is_settled_block_by_process, \
    get_RecordGUID_NewCadaster,get_parcel_parameters_by_guid,get_block_parameters_by_guid, clear_map_selections
from Utils.ValidationsNewCadaster import layer_exists
from arcpy.mp import ArcGISProject
from arcpy import AddMessage, AddError, GetParameterAsText, AddWarning
from arcpy.da import SearchCursor, UpdateCursor
from arcpy.management import SelectLayerByAttribute, SelectLayerByLocation, Dissolve, GetCount, CalculateField
from typing import Literal
from collections import Counter

def get_number_of_selections(LayerName:str) -> int:
    """
    Get the number of selections in a layer.

    Parameters:
    LayerName (str): The name of the layer.

    Returns:
    int: The number of selections in the layer.
    """

    layer = get_layer(LayerName)
    selection_set = layer.getSelectionSet()

    if selection_set:
        return len(selection_set)
    else:
        return 0


def RetireSelectedFeatures(ProcessName:str, used_layer: Literal['PARCELS','BLOCKS'] = 'PARCELS') -> None:
    """
    Retires selected non-settled features and its related fronts and points, the RetiredByProcess field is set to the record with the name ProcessName
    Parameters:
    ProcessName (str): The name of the retiring record.

    Returns:
    None
    """

    if is_tax_process(ProcessName):
        AddMessage(f'{timestamp()} | The process {ProcessName} is a tax process, retirement of features is not allowed.')

    Record_GUID = get_RecordGUID_NewCadaster(ProcessName)

    if not Record_GUID:
        AddMessage(f'{timestamp()} | ⚠️ No Record GUID found for process {ProcessName}, skipping retirement.')
    else:
        if layer_exists('גושים לא מוסדרים') and layer_exists('חלקות לא מוסדרות'):
            block_ids_for_geometry_update = []
            block_ids_for_retirement = []
            parcel_ids_for_retirement = []
            used_block_ids_in_parcels_layer = []
            num_of_selected_parcels = 0
            num_of_selected_blocks = 0
            if used_layer == "PARCELS":
                parcels_for_retirement = get_layer('חלקות לא מוסדרות')
                # ensuring only non-settled parcels are selected for retirement, excluding those created by the current record
                # to prevent user from removing definition query from the layer and retiring settled parcels by mistake
                SelectLayerByAttribute(parcels_for_retirement,selection_type="SUBSET_SELECTION",where_clause=f"LandType = 2 AND CreatedByRecord <> '{Record_GUID}'")
                num_of_selected_parcels = get_number_of_selections('חלקות לא מוסדרות')

                if num_of_selected_parcels > 0:
                    AddMessage(f'{timestamp()} | {num_of_selected_parcels} unsettled parcels were selected for retirement')
                    if not is_settled_block_by_process(ProcessName):
                        SelectLayerByAttribute(parcels_for_retirement,selection_type="SUBSET_SELECTION",where_clause="IsTax = 1")
                        new_num_of_selected_parcels = get_number_of_selections('חלקות לא מוסדרות')
                        if new_num_of_selected_parcels != num_of_selected_parcels:
                            AddMessage(f'{timestamp()} | The process {ProcessName} contains unsettled non-tax parcels and can retire only tax features:')
                            AddMessage(f'{timestamp()} | {num_of_selected_parcels-new_num_of_selected_parcels} parcels were removed from the selection')
                            if new_num_of_selected_parcels == 0:
                                AddMessage(f'{timestamp()} | No selected parcels remained for retirement, skipping retirement process.')
                                return

                    parcel_ids_for_retirement = [row[0] for row in SearchCursor(parcels_for_retirement, 'GlobalID')]
                    parcel_ids_for_retirement_str = ",".join(f"'{uniqueID}'" for uniqueID in parcel_ids_for_retirement)
                    used_block_ids_in_parcels_layer = [row[0] for row in SearchCursor(parcels_for_retirement, 'BlockUniqueID')]
                    hist = dict(Counter(used_block_ids_in_parcels_layer))

                    for block_id in hist.keys():
                        temp_parcels_layer = SelectLayerByAttribute(parcels_for_retirement, "NEW_SELECTION", f"BlockUniqueID = '{block_id}'")
                        count = get_number_of_selections('חלקות לא מוסדרות')
                        if get_number_of_selections('חלקות לא מוסדרות') == hist[block_id]:
                            block_ids_for_retirement.append(block_id)
                        else:
                            block_ids_for_geometry_update.append(block_id)

                    block_ids_for_retirement_str = ",".join(f"'{uniqueID}'" for uniqueID in block_ids_for_retirement) 
                    parcels_for_retirement = SelectLayerByAttribute(parcels_for_retirement, "NEW_SELECTION", f"GlobalID IN ({parcel_ids_for_retirement_str})")

            else: # BLOCKS
                blocks_for_retirement = get_layer('גושים לא מוסדרים')
                # ensuring only non-settled blocks are selected for retirement, excluding those created by the current record
                # to prevent user from removing definition query from the layer and retiring settled blocks by mistake
                SelectLayerByAttribute(blocks_for_retirement,selection_type="SUBSET_SELECTION",where_clause=f"LandType = 2 AND CreatedByRecord <> '{Record_GUID}'")
                num_of_selected_blocks = get_number_of_selections('גושים לא מוסדרים')

                if num_of_selected_blocks > 0:
                    
                    AddMessage(f'{timestamp()} | {num_of_selected_blocks} unsettled blocks were selected for retirement')
                    if not is_settled_block_by_process(ProcessName):
                        SelectLayerByAttribute(blocks_for_retirement,selection_type="SUBSET_SELECTION",where_clause="IsTax = 1")
                        new_num_of_selected_blocks = get_number_of_selections('גושים לא מוסדרים')
                        if new_num_of_selected_blocks != num_of_selected_blocks:
                            AddMessage(f'{timestamp()} | The process {ProcessName} contains unsettled non-tax parcels and can retire only tax features:')
                            AddMessage(f'{timestamp()} | {num_of_selected_blocks-new_num_of_selected_blocks} blocks were removed from the selection')
                            if new_num_of_selected_blocks == 0:
                                AddMessage(f'{timestamp()} | No selected blocks remained for retirement, skipping retirement process.')
                                return


                    non_settled_parcels = get_layer('חלקות לא מוסדרות')

                    block_ids_for_retirement = [row[0] for row in SearchCursor(blocks_for_retirement, 'GlobalID')]
                    block_ids_for_retirement_str = ",".join(f"'{uniqueID}'" for uniqueID in block_ids_for_retirement)
                    parcels_for_retirement = SelectLayerByAttribute(non_settled_parcels, "NEW_SELECTION", f"BlockUniqueID IN ({block_ids_for_retirement_str})")
                    parcel_ids_for_retirement = [row[0] for row in SearchCursor(parcels_for_retirement, 'GlobalID')]
                    parcel_ids_for_retirement_str = ",".join(f"'{uniqueID}'" for uniqueID in parcel_ids_for_retirement)


            if num_of_selected_parcels > 0 or num_of_selected_blocks > 0:
                #dissolved_parcels = Dissolve(in_features=parcels_for_retirement,dissolve_field=None,statistics_fields=None,multi_part="MULTI_PART",unsplit_lines="UNSPLIT_LINES",concatenation_separator="")
                fronts = get_layer('חזיתות')
                border_points = get_layer('נקודות גבול')

                fronts_for_retirement = SelectLayerByLocation(in_layer=fronts,overlap_type="SHARE_A_LINE_SEGMENT_WITH",select_features=parcels_for_retirement,
                                            search_distance=None,selection_type="NEW_SELECTION",invert_spatial_relationship="NOT_INVERT")
                #fronts_for_retirement = SelectLayerByLocation(in_layer=fronts_for_retirement,overlap_type="SHARE_A_LINE_SEGMENT_WITH",select_features=dissolved_parcels,
                #                            search_distance=None,selection_type="REMOVE_FROM_SELECTION",invert_spatial_relationship="NOT_INVERT")          
                fronts_for_retirement = SelectLayerByAttribute(in_layer_or_view=fronts_for_retirement,selection_type="REMOVE_FROM_SELECTION",
                                            where_clause=f"CreatedByRecord = '{Record_GUID}'",invert_where_clause=None)

                points_for_retirement = SelectLayerByLocation(in_layer=border_points, overlap_type="BOUNDARY_TOUCHES", select_features=parcels_for_retirement,
                                            search_distance=None, selection_type="NEW_SELECTION", invert_spatial_relationship="NOT_INVERT")
                #points_for_retirement = SelectLayerByLocation(in_layer=points_for_retirement, overlap_type="BOUNDARY_TOUCHES", select_features=dissolved_parcels,
                #                            search_distance=None, selection_type="REMOVE_FROM_SELECTION", invert_spatial_relationship="NOT_INVERT")
                points_for_retirement = SelectLayerByAttribute(in_layer_or_view=points_for_retirement,selection_type="REMOVE_FROM_SELECTION",
                                            where_clause=f"CreatedByRecord = '{Record_GUID}'",invert_where_clause=None)

                num_of_parcels = len(parcel_ids_for_retirement)
                num_of_blocks = len(block_ids_for_retirement)



                reopen_map()
                if num_of_parcels > 0:
                    parcels_list = []
                    cancel_type = Type2CancelType(get_ProcessType(ProcessName))
                    editor = start_editing(CNFG.ParcelFabricDatabase)
                    with UpdateCursor(parcels_for_retirement, ["GlobalID","RetiredByRecord","CancelProcessType","ParcelNumber","BlockNumber","SubBlockNumber","IsTax"],where_clause=f"GlobalID IN ({parcel_ids_for_retirement_str})") as cursor:
                        for row in cursor: 
                            #parcel_parameters = get_parcel_parameters_by_guid(row[0])
                            parcel_parameters = (row[3],row[4],row[5],row[6])  #ParcelNumber, BlockNumber, SubBlockNumber, IsTax
                            

                            parcels_list.append(parcel_parameters)
                            row[1] = Record_GUID
                            row[2] = cancel_type
                            cursor.updateRow(row)
                    stop_editing(editor)

                    parcels_list.sort(key=lambda x: (x[1], x[2], x[0]))
                    AddMessage(f'{timestamp()} | {num_of_parcels} non-settled parcels were retired by the process {ProcessName}:')
                    for parcel, block,sub_block,is_tax in parcels_list:
                        tax_addition = ("", " (Tax)")[is_tax]
                        AddMessage(f"            {parcel}/{block}/{sub_block}{tax_addition}")
                    del parcels_list
                else:
                    AddMessage(f'{timestamp()} | No parcels were found for retirement.')

                reopen_map()

                if num_of_blocks > 0:
                    blocks_list = []
                    editor = start_editing(CNFG.ParcelFabricDatabase)
                    with UpdateCursor(blocks_for_retirement, ["GlobalID","RetiredByRecord","BlockNumber","SubBlockNumber","IsTax"],where_clause=f"GlobalID IN ({block_ids_for_retirement_str})") as cursor:
                        for row in cursor:
                            block_parameters = (row[2],row[3],row[4])  #BlockNumber, SubBlockNumber, IsTax
                            blocks_list.append(block_parameters)
                            row[1] = Record_GUID
                            cursor.updateRow(row)
                    stop_editing(editor)
                            
                    blocks_list.sort(key=lambda x: (x[0], x[1]))
                    AddMessage(f'{timestamp()} | {num_of_blocks} non-settled blocks were retired by the process {ProcessName}:')
                    for block,sub_block,is_tax in blocks_list:
                        tax_addition = ("", " (Tax)")[is_tax]
                        AddMessage(f"            {block}/{sub_block}{tax_addition}")

                    del blocks_list
                else:
                    AddMessage(f'{timestamp()} | No blocks were found for retirement.')
                

                if block_ids_for_geometry_update:
                    for block_id in block_ids_for_geometry_update:
                        
                        update_status = update_blocks_geometry_by_active_parcels(block_id,Record_GUID)
                        block_parameters = get_block_parameters_by_guid(block_id)
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

                non_settled_parcels = get_layer('חלקות לא מוסדרות')
                SelectLayerByAttribute(non_settled_parcels,selection_type="CLEAR_SELECTION")
                non_settled_parcels = SelectLayerByAttribute(in_layer_or_view=non_settled_parcels,selection_type="NEW_SELECTION",
                                            where_clause=f"GlobalID NOT IN ({parcel_ids_for_retirement_str})",invert_where_clause=None)
                fronts_for_retirement = SelectLayerByLocation(in_layer=fronts_for_retirement,overlap_type="SHARE_A_LINE_SEGMENT_WITH",select_features=non_settled_parcels,
                                            search_distance=None,selection_type="REMOVE_FROM_SELECTION",invert_spatial_relationship="NOT_INVERT")
                points_for_retirement = SelectLayerByLocation(in_layer=points_for_retirement, overlap_type="BOUNDARY_TOUCHES", select_features=non_settled_parcels,
                                            search_distance=None, selection_type="REMOVE_FROM_SELECTION", invert_spatial_relationship="NOT_INVERT")
                
                '''
                

                num_of_fronts = 0
                num_of_points = 0

                with UpdateCursor(fronts_for_retirement, ["RetiredByRecord","GlobalID"]) as cursor:
                    for row in cursor:
                        row[0] = Record_GUID
                        cursor.updateRow(row)
                        num_of_fronts += 1
                        AddMessage(f'{timestamp()} | ✴️ Retired front {row[1]} by the process {ProcessName}')

                with UpdateCursor(points_for_retirement, ["RetiredByRecord","GlobalID"]) as cursor:
                    for row in cursor:
                        row[0] = Record_GUID
                        cursor.updateRow(row)
                        num_of_points += 1
                        AddMessage(f'{timestamp()} | ✴️ Retired point {row[1]} by the process {ProcessName}')

                AddMessage(f'{timestamp()} | ✴️ {num_of_fronts} fronts were retired by the process {ProcessName}')

                AddMessage(f'{timestamp()} | ✴️ {num_of_points} points were retired by the process {ProcessName}')
                '''
              
                editor = start_editing(CNFG.ParcelFabricDatabase)
                # using calculate field for better performance
                CalculateField(
                    in_table=fronts_for_retirement,
                    field="RetiredByRecord",
                    expression=f"'{Record_GUID}'",
                    expression_type="SQL",
                    code_block="",
                    field_type="TEXT",
                    enforce_domains="NO_ENFORCE_DOMAINS"
                )
                



                
                CalculateField(
                    in_table=points_for_retirement,
                    field="RetiredByRecord",
                    expression=f"'{Record_GUID}'",
                    expression_type="SQL",
                    code_block="",
                    field_type="TEXT",
                    enforce_domains="NO_ENFORCE_DOMAINS"
                )
                
                stop_editing(editor)
                AddMessage(f'{timestamp()} | ✴️ {get_number_of_selections("חזיתות")} fronts were retired by the process {ProcessName}')
                AddMessage(f'{timestamp()} | ✴️ {get_number_of_selections("נקודות גבול")} points were retired by the process {ProcessName}')


                #del [dissolved_parcels]
            else:
                AddMessage(f"   No selection was made or there is nothing to retire")
        else:
            if not layer_exists('גושים לא מוסדרים') and not layer_exists('חלקות לא מוסדרות'):
                AddMessage(f'{timestamp()} | No layers were found with unsettled features, no changes were made.')
            else:
                AddWarning(f'{timestamp()} | One of the layers with unsettled features is missing, no changes were made. Check data integrity.')
        

        clear_map_selections()



   
  
    
if __name__ == "__main__":

    used_layer = GetParameterAsText(0)

    ProcessName: str|None = get_ActiveRecord()
    if not ProcessName:
        ProcessName: str|None = get_ProcessName()

    if used_layer == "גושים לא מוסדרים":
        used_layer = "BLOCKS"
    else:
        used_layer = "PARCELS"


    RetireSelectedFeatures(ProcessName, used_layer)
    reopen_map()
