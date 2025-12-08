from Utils.Configs import CNFG
from Utils.Helpers import get_RecordGUID, start_editing, stop_editing, timestamp, reopen_map,get_layer, get_ActiveRecord
from Utils.NewCadasterHelpers import get_ProcessName, update_blocks_geometry_by_active_parcels, is_tax_process, is_settled_block_by_process, get_RecordGUID_NewCadaster
from Utils.ValidationsNewCadaster import layer_exists
from arcpy.mp import ArcGISProject
from arcpy import AddMessage, AddError, GetParameterAsText
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
                num_of_selected_parcels = get_number_of_selections('חלקות לא מוסדרות')

                if num_of_selected_parcels > 0:
                    AddMessage(f'{timestamp()} | {num_of_selected_parcels} parcels were selected for retirement')
                    parcels_for_retirement = get_layer('חלקות לא מוסדרות')
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
                num_of_selected_blocks = get_number_of_selections('גושים לא מוסדרים')

                if num_of_selected_blocks > 0:

                    AddMessage(f'{timestamp()} | {num_of_selected_blocks} blocks were selected for retirement')
                    blocks_for_retirement = get_layer('גושים לא מוסדרים')
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
                dissolved_parcels = Dissolve(in_features=parcels_for_retirement,dissolve_field=None,statistics_fields=None,multi_part="MULTI_PART",unsplit_lines="UNSPLIT_LINES",concatenation_separator="")
                fronts = get_layer('חזיתות')
                border_points = get_layer('נקודות גבול')

                fronts_for_retirement = SelectLayerByLocation(in_layer=fronts,overlap_type="SHARE_A_LINE_SEGMENT_WITH",select_features=parcels_for_retirement,
                                            search_distance=None,selection_type="NEW_SELECTION",invert_spatial_relationship="NOT_INVERT")
                fronts_for_retirement = SelectLayerByLocation(in_layer=fronts_for_retirement,overlap_type="SHARE_A_LINE_SEGMENT_WITH",select_features=dissolved_parcels,
                                            search_distance=None,selection_type="REMOVE_FROM_SELECTION",invert_spatial_relationship="NOT_INVERT")          
                fronts_for_retirement = SelectLayerByAttribute(in_layer_or_view=fronts_for_retirement,selection_type="REMOVE_FROM_SELECTION",
                                            where_clause=f"CreatedByRecord = '{Record_GUID}'",invert_where_clause=None)

                points_for_retirement = SelectLayerByLocation(in_layer=border_points, overlap_type="BOUNDARY_TOUCHES", select_features=parcels_for_retirement,
                                            search_distance=None, selection_type="NEW_SELECTION", invert_spatial_relationship="NOT_INVERT")
                points_for_retirement = SelectLayerByLocation(in_layer=points_for_retirement, overlap_type="BOUNDARY_TOUCHES", select_features=dissolved_parcels,
                                            search_distance=None, selection_type="REMOVE_FROM_SELECTION", invert_spatial_relationship="NOT_INVERT")
                points_for_retirement = SelectLayerByAttribute(in_layer_or_view=fronts_for_retirement,selection_type="REMOVE_FROM_SELECTION",
                                            where_clause=f"CreatedByRecord = '{Record_GUID}'",invert_where_clause=None)

                num_of_parcels = len(parcel_ids_for_retirement)
                num_of_blocks = len(block_ids_for_retirement)

                editor = start_editing(CNFG.ParcelFabricDatabase)


                if num_of_parcels > 0:
                    AddMessage(f'{timestamp()} | {num_of_parcels} non-settled parcels will be retired by the process {ProcessName}:') 
                    with UpdateCursor(parcels_for_retirement, ["GlobalID","Name", "RetiredByRecord","CancelProcessType"],where_clause=f"GlobalID IN ({parcel_ids_for_retirement_str})") as cursor:
                        for row in cursor:
                            AddMessage(f'                 {row[0]}  {row[1]}')
                            row[2] = Record_GUID
                            row[3] = 5
                            cursor.updateRow(row)
                else:
                    AddMessage(f'{timestamp()} | No parcels were found for retirement.')



                if num_of_blocks > 0:
                    AddMessage(f'{timestamp()} | {num_of_blocks} non-settled blocks will be retired by the process {ProcessName}:')
                    with UpdateCursor(blocks_for_retirement, ["GlobalID","BlockNumber", "SubBlockNumber", "RetiredByRecord"],where_clause=f"GlobalID IN ({block_ids_for_retirement_str})") as cursor:
                        for row in cursor:
                            AddMessage(f'                 {row[0]}  {row[1]}/{row[2]}')
                            row[3] = Record_GUID
                            cursor.updateRow(row)
                else:
                    AddMessage(f'{timestamp()} | No blocks were found for retirement.')


                if block_ids_for_geometry_update:
                    for block_id in block_ids_for_geometry_update:
                        AddMessage(f'{timestamp()} | Updating geometry for block {block_id}')
                        update_blocks_geometry_by_active_parcels(block_id)

                stop_editing(editor)
                


                CalculateField(
                    in_table=fronts_for_retirement,
                    field="RetiredByRecord",
                    expression=f"'{Record_GUID}'",
                    expression_type="SQL",
                    code_block="",
                    field_type="TEXT",
                    enforce_domains="NO_ENFORCE_DOMAINS"
                )


                AddMessage(f'{timestamp()} | ✴️ {get_number_of_selections("חזיתות")} fronts were retired by the process {ProcessName}')

                CalculateField(
                    in_table=points_for_retirement,
                    field="RetiredByRecord",
                    expression=f"'{Record_GUID}'",
                    expression_type="SQL",
                    code_block="",
                    field_type="TEXT",
                    enforce_domains="NO_ENFORCE_DOMAINS"
                )


                AddMessage(f'{timestamp()} | ✴️ {get_number_of_selections("נקודות גבול")} points were retired by the process {ProcessName}')


                del [dissolved_parcels]
            else:
                AddMessage(f"   No selection was made or there is nothing to retire")


    

   

def RetireSelectedFeatures_old(ProcessName:str, used_layer: Literal['PARCELS','BLOCKS'] = 'PARCELS') -> None:
    """
    Retires selected non-settled features and its related fronts and points, the RetiredByProcess field is set to the record with the name ProcessName
    Parameters:
    ProcessName (str): The name of the retiring record.

    Returns:
    None
    """
    

    Record_GUID = get_RecordGUID(ProcessName,'MAP')
    
    Block_GlobalIDs = [] 
    if layer_exists('גושים לא מוסדרים'):
        non_settled_blocks_selections = get_number_of_selections('גושים לא מוסדרים')
        if non_settled_blocks_selections > 0:
            Non_Settled_Blocks_layer = get_layer('גושים לא מוסדרים')
            
            editor = start_editing(CNFG.ParcelFabricDatabase)
            with UpdateCursor(Non_Settled_Blocks_layer, ["GlobalID", "RetiredByRecord"]) as cursor:
                for row in cursor:
                    Block_GlobalIDs.append(row[0])
                    row[1] = Record_GUID
                    cursor.updateRow(row)
            stop_editing(editor)
            
            AddMessage(f'{timestamp()} | ✴️ {non_settled_blocks_selections} non-settled blocks were retired by the process {ProcessName}') 
        else:
            AddMessage(f'{timestamp()} | ✴️ No non-settled blocks selected for retirenment') 
    else:
        AddMessage(f'{timestamp()} | ✴️ No non-settled blocks layer exists') 

    Parcel_GlobalIDs = [] 
    if layer_exists('חלקות לא מוסדרות'):
        Non_Settled_Parcels_layer = get_layer('חלקות לא מוסדרות') 

        if Block_GlobalIDs:
            if len(Block_GlobalIDs) == 1:
                query = f"""BlockUniqueID = '{Block_GlobalIDs[0]}'"""
            else:
                query = f"BlockUniqueID IN {tuple(Block_GlobalIDs)}"
            Non_Settled_Parcels_layer = SelectLayerByAttribute(Non_Settled_Parcels_layer, selection_type="ADD_TO_SELECTION", where_clause=query)
        non_settled_parcels_selections = get_number_of_selections('חלקות לא מוסדרות')
        if non_settled_parcels_selections > 0:

            editor = start_editing(CNFG.ParcelFabricDatabase)
            with UpdateCursor(Non_Settled_Parcels_layer, ["GlobalID","RetiredByRecord","CancelProcessType"]) as cursor:
                for row in cursor:
                    Parcel_GlobalIDs.append(row[0])
                    row[1] = Record_GUID
                    row[2] = 5
                    cursor.updateRow(row)
            stop_editing(editor)
            AddMessage(f'{timestamp()} | ✴️ {non_settled_parcels_selections} non-settled parcels were retired by the process {ProcessName}') 
        else:
            AddMessage(f'{timestamp()} | ✴️ No non-settled parcels selected for retirenment') 
    else:
        AddMessage(f'{timestamp()} | ✴️ No non-settled parcels layer exists') 

    if Parcel_GlobalIDs:
            if len(Parcel_GlobalIDs) > 1:
                query = f"GlobalID IN {tuple(Parcel_GlobalIDs)}"
                
                All_Parcels_layer = get_layer('חלקות מבוטלות')
                Retired_Parcels_layer = SelectLayerByAttribute(All_Parcels_layer, selection_type="NEW_SELECTION", where_clause=query)
                

                Dissolved_parcels = Dissolve(in_features=Retired_Parcels_layer,dissolve_field=None,statistics_fields=None,multi_part="MULTI_PART",unsplit_lines="DISSOLVE_LINES",concatenation_separator="")


                Fronts = get_layer('חזיתות')
                BorderPoints = get_layer('נקודות גבול')
               
                Fronts_for_retirement = SelectLayerByLocation(in_layer=Fronts,overlap_type="WITHIN",select_features=Dissolved_parcels,
                                        search_distance=None,selection_type="NEW_SELECTION",invert_spatial_relationship="NOT_INVERT")
                
                
                Fronts_for_retirement = SelectLayerByLocation(in_layer=Fronts_for_retirement,overlap_type="SHARE_A_LINE_SEGMENT_WITH",select_features=Dissolved_parcels,
                                        search_distance=None,selection_type="REMOVE_FROM_SELECTION",invert_spatial_relationship="NOT_INVERT")
                
                
                
                Fronts_for_retirement = SelectLayerByAttribute(in_layer_or_view=Fronts_for_retirement,selection_type="REMOVE_FROM_SELECTION",
                                        where_clause=f"CreatedByRecord = '{Record_GUID}'",invert_where_clause=None)
                
                

                Points_for_retirement = SelectLayerByLocation(in_layer=BorderPoints,overlap_type="COMPLETELY_WITHIN",select_features=Dissolved_parcels,
                                        search_distance=None,selection_type="NEW_SELECTION",invert_spatial_relationship="NOT_INVERT")
                
                
                
                Points_for_retirement = SelectLayerByAttribute(in_layer_or_view=BorderPoints,selection_type="REMOVE_FROM_SELECTION",
                                        where_clause=f"CreatedByRecord = '{Record_GUID}'",invert_where_clause=None)
                
                
                

                count = int(GetCount(Fronts_for_retirement)[0])

                CalculateField(
                    in_table=Fronts_for_retirement,
                    field="RetiredByRecord",
                    expression=f"'{Record_GUID}'",
                    expression_type="SQL",
                    code_block="",
                    field_type="TEXT",
                    enforce_domains="NO_ENFORCE_DOMAINS"
                )

                
                AddMessage(f'{timestamp()} | ✴️ {count} fronts were retired by the process {ProcessName}')
                

                count = int(GetCount(Points_for_retirement)[0])
                CalculateField(
                    in_table=Points_for_retirement,
                    field="RetiredByRecord",
                    expression=f"'{Record_GUID}'",
                    expression_type="SQL",
                    code_block="",
                    field_type="TEXT",
                    enforce_domains="NO_ENFORCE_DOMAINS"
                )
                AddMessage(f'{timestamp()} | ✴️ {count} points were retired by the process {ProcessName}')

                
                

                del [Dissolved_parcels]      

    for guid in blocks_guids:
        update_blocks_geometry_by_active_parcels(guid)
    
    
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
