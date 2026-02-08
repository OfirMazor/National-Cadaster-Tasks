from Utils.Configs import CNFG
from Utils.Helpers import get_ProcessGUID, get_RecordGUID, get_BlockGUID, start_editing, stop_editing, get_layer, reopen_map, Type2CreateType, timestamp,get_ProcessType,reopen_map
from arcpy.management import Append, DeleteIdentical, GetCount, SelectLayerByAttribute as SelectByAttribute, SelectLayerByLocation as SelectByLocation, CalculateField, Delete, Dissolve,SplitLine, CopyFeatures

from arcpy.da import SearchCursor, UpdateCursor, InsertCursor
from arcpy import AddMessage, AddWarning, AddError,env as ENV, Describe, Extent,RefreshLayer
from arcpy.mp import LayerFile, ArcGISProject
from arcpy.mp import ArcGISProject
from arcpy import Geometry
from Utils.TypeHints import *
from arcpy.conversion import ExportFeatures
import os

ENV.overwriteOutput = True


def is_process_border_valid(ProcessName:str) -> bool:
    '''
    Checks if the process border for the specified `ProcessName` is fully matching to the contour of the in process parcels,
    if not, creates a local copy with the correct geometry in the default gdb
    Parameters:
        ProcessName (str): The name of the process to search for.
    Returns:
        bool: True if the process border is valid, False otherwise.
    '''
    cadaster_process_borders = get_layer('גבולות תהליכי קדסטר')
    parcels_layer = get_layer('חלקות בתהליך')
    process_border = SelectByAttribute(cadaster_process_borders,where_clause=f""" ProcessName = '{ProcessName}' """,selection_type='NEW_SELECTION')
    process_guid = get_ProcessGUID(ProcessName)
    process_parcels = SelectByAttribute(parcels_layer,where_clause=f""" CPBUniqueID = '{process_guid}' """,selection_type='NEW_SELECTION')
    count = int(GetCount(process_parcels).getOutput(0))
    if count == 0:
        clear_map_selections()
        AddWarning(f'{timestamp()} | No parcels found for process {ProcessName}. No change to process border will be made.')
        return False
    
    dissolved_parcels = Dissolve(in_features=process_parcels, out_feature_class=r"memory\dissolved_parcels")

    with SearchCursor(dissolved_parcels, field_names="SHAPE@") as cursor:
        dissolved_parcels_geometry = cursor.next()[0]

    with SearchCursor(process_border, field_names="SHAPE@") as cursor:
        process_border_geometry = cursor.next()[0]
    
    result = None
    if not process_border_geometry.equals(dissolved_parcels_geometry):
        ENV.preserveGlobalIds = True
        default_gdb = get_default_gdb()
        local_process_border = CopyFeatures(process_border, f"{default_gdb}\\ProcessBorder_{ProcessName.replace('/','_')}")
        ENV.preserveGlobalIds = False
        editor = start_editing(CNFG.ParcelFabricDatabase)

        with UpdateCursor(local_process_border, ["SHAPE@"]) as cursor:
                row = next(cursor, None)  # Safely get the first row or None
                if row:
                    row[0] = dissolved_parcels_geometry
                    cursor.updateRow(row)
        stop_editing(editor)

        result = False
    else:
        AddMessage(f'{timestamp()} | The process border matches the process parcels contour for process {ProcessName}.')
        
        result = True

    Delete(dissolved_parcels)
    clear_map_selections()
    return result

def get_default_gdb() -> str:
    ''' 
    Retrieves the default geodatabase path from the current ArcGIS Pro project

    Returns:
        str: The path to the default geodatabase.
    '''
    aprx = ArcGISProject("CURRENT")
    default_gdb = aprx.defaultGeodatabase
    return default_gdb

def match_process_border_to_process_parcels(ProcessName:str) -> None:
    cadaster_process_borders = get_layer('גבולות תהליכי קדסטר')
    parcels_layer = get_layer('חלקות בתהליך')
    process_border = SelectByAttribute(cadaster_process_borders,where_clause=f""" ProcessName = '{ProcessName}' """,selection_type='NEW_SELECTION')
    process_guid = get_ProcessGUID(ProcessName)
    process_parcels = SelectByAttribute(parcels_layer,where_clause=f""" CPBUniqueID = '{process_guid}' """,selection_type='NEW_SELECTION')
    count = int(GetCount(process_parcels).getOutput(0))
    if count == 0:
        clear_map_selections()
        reopen_map()
        AddMessage(f'{timestamp()} | No parcels found for process {ProcessName}. No change to process border will be made.')
        return
    
    dissolved_parcels = Dissolve(in_features=process_parcels, out_feature_class=r"memory\dissolved_parcels")

    with SearchCursor(dissolved_parcels, field_names="SHAPE@") as cursor:
        dissolved_parcels_geometry = cursor.next()[0]

    with SearchCursor(process_border, field_names="SHAPE@") as cursor:
        process_border_geometry = cursor.next()[0]
    
    if not process_border_geometry.equals(dissolved_parcels_geometry):
        AddMessage(f'{timestamp()} | Mismatch between the process border and the dissolved process parcels was found for process {ProcessName}.\
         Updating the process border to match the process parcels contour.')
        editor = start_editing(CNFG.ParcelFabricDatabase)

        with UpdateCursor(process_border, ["SHAPE@"]) as cursor:
                row = next(cursor, None)  # Safely get the first row or None
                if row:
                    AddMessage(f'{timestamp()} | Updating process border geometry...')
                    row[0] = dissolved_parcels_geometry
                    cursor.updateRow(row)
        stop_editing(editor)

    else:
        AddMessage(f'{timestamp()} | The process border matches the process parcels contour for process {ProcessName}.')
    clear_map_selections()
    Delete(dissolved_parcels)
    reopen_map()



def match_active_tax_blocks_to_active_tax_parcels(ProcessName:str) -> None:
    cadaster_process_borders = get_layer('גבולות תהליכי קדסטר')
    parcels_layer = get_layer('חלקות')

    process_border = SelectByAttribute(cadaster_process_borders,where_clause=f""" ProcessName = '{ProcessName}' """,selection_type='NEW_SELECTION')
    tax_parcels = SelectByAttribute(parcels_layer,where_clause=f""" IsTax=1 AND RetiredByRecord IS NULL """,selection_type='NEW_SELECTION')
    intersecting_tax_parcels = SelectByLocation(in_layer=tax_parcels,overlap_type="INTERSECT",select_features=process_border,search_distance="10 Meters",selection_type="SUBSET_SELECTION")

    count = int(GetCount(intersecting_tax_parcels).getOutput(0))
    if count == 0:
        clear_map_selections()
        reopen_map()
        AddMessage(f'{timestamp()} | No tax parcels intersecting with process borders were found')
        return
    
    retired_blocks_layer = get_layer('גושים מבוטלים')

  
    tax_block_GUIDs = set()
    with SearchCursor(intersecting_tax_parcels, ['BlockUniqueID']) as cursor:
        for row in cursor:
            tax_block_GUIDs.add(row[0])
    SelectByAttribute(parcels_layer, "CLEAR_SELECTION")
    retired_block_guids = []
    for block_guid in tax_block_GUIDs:
        with SearchCursor(retired_blocks_layer, ['GlobalID'], where_clause=f"GlobalID = '{block_guid}'") as cursor:
            for row in cursor:
                retired_block_guids.append(block_guid)
                break
    if not retired_block_guids:
        clear_map_selections()
        reopen_map()
        AddMessage(f'{timestamp()} | No missing tax blocks were found')
        return

    AddMessage(f'{timestamp()} | Found {len(retired_block_guids)} tax blocks that were wrongly retired. Restoring them to active blocks layer and updating their geometry to fit their active parcels')
    editor = start_editing(CNFG.ParcelFabricDatabase)
    for block_guid in retired_block_guids:
        with UpdateCursor(retired_blocks_layer, ['RetiredByRecord'], where_clause=f"GlobalID = '{block_guid}'") as cursor:
            for row in cursor:
                row[0] = None
                cursor.updateRow(row)
    stop_editing(editor)

    for block_guid in retired_block_guids:
        update_blocks_geometry_by_active_parcels(block_guid, None)
    
    clear_map_selections()
    reopen_map()
    AddMessage(f'{timestamp()} | Restored {len(retired_block_guids)} tax blocks to active blocks layer and updated their geometry')

def split_merged_tax_fronts(ProcessName:str) -> None:
    ''' 
    Splits merged fronts in tax parcels that intersects with the given process

    '''
    parcels_layer = get_layer('חלקות')
    fronts_layer = get_layer('חזיתות')
    cadaster_process_borders = get_layer('גבולות תהליכי קדסטר')
    process_border = SelectByAttribute(cadaster_process_borders,where_clause=f""" ProcessName = '{ProcessName}' """,selection_type='NEW_SELECTION')
    unsettled_tax_parcels = SelectByAttribute(parcels_layer,where_clause=f""" LandType = 2 AND IsTax=1 AND RetiredByRecord IS NULL """,selection_type='NEW_SELECTION')
    intersecting_unsettled_tax_parcels = SelectByLocation(in_layer=unsettled_tax_parcels,overlap_type="INTERSECT",select_features=process_border,search_distance="10 Meters",selection_type="SUBSET_SELECTION")
    count_parcels = int(GetCount(intersecting_unsettled_tax_parcels).getOutput(0))
    if count_parcels == 0:
        clear_map_selections()
        reopen_map()
        AddMessage(f'{timestamp()} | No unsettled tax parcels intersecting with fronts. No fronts to split.')
        return


    fronts_to_split = SelectByLocation(in_layer=fronts_layer,overlap_type="SHARE_A_LINE_SEGMENT_WITH",select_features=intersecting_unsettled_tax_parcels,search_distance=None,selection_type="NEW_SELECTION")[0]
    #settled_parcels = SelectByAttribute(parcels_layer,where_clause=f""" LandType = 1 AND RetiredByRecord IS NULL """,selection_type='NEW_SELECTION')
    #intersecting_settled_parcels = SelectByLocation(in_layer=settled_parcels,overlap_type="INTERSECT",select_features=process_border,search_distance="10 Meters",selection_type="SUBSET_SELECTION")
    #fronts_to_split = SelectByLocation(in_layer=fronts_to_split,overlap_type="SHARE_A_LINE_SEGMENT_WITH",select_features=intersecting_settled_parcels,search_distance=None,selection_type="REMOVE_FROM_SELECTION")

    oids = [row[0] for row in SearchCursor(fronts_to_split, ["OID@","SHAPE@"]) if row[1].pointCount > 2]
    if not oids:
    
    #if count_fronts_before == 0:
        clear_map_selections()
        reopen_map()
        AddMessage(f'{timestamp()} | No merged fronts to split were found.')
        return
    fronts_to_split.setSelectionSet(oids)
    count_fronts_before = int(GetCount(fronts_to_split).getOutput(0))
    splitted_fronts = SplitLine(fronts_to_split,r"memory\splitted_fronts")
    DeleteIdentical(in_dataset=splitted_fronts,fields="Shape")

    count_fronts_after = int(GetCount(splitted_fronts).getOutput(0))
    if count_fronts_after > count_fronts_before:
        AddMessage(f'{timestamp()} | The found merged {count_fronts_before} fronts will be splitted into {count_fronts_after} fronts.')
        editor = start_editing(CNFG.ParcelFabricDatabase)
        try:
            # Append the split fronts back to the main layer
            Append(
                inputs=splitted_fronts,
                target=fronts_layer,
                expression="",
                field_mapping="",
                schema_type="NO_TEST",
                subtype="",
                match_fields=None,
                update_geometry="NOT_UPDATE_GEOMETRY",
                feature_service_mode="USE_FEATURE_SERVICE_MODE"
            )

            # Delete the original selected (merged) fronts
            with UpdateCursor(fronts_to_split, ["OID@"]) as cursor:
                for row in cursor:
                    cursor.deleteRow()
        finally:
            stop_editing(editor)

        clear_map_selections()
        reopen_map()
        AddMessage(f'{timestamp()} | Splitted {count_fronts_before} merged fronts into {count_fronts_after} fronts.')
        
    else:       
        clear_map_selections()
        reopen_map()
        AddMessage(f'{timestamp()} | No merged fronts to split were found.')
    Delete(splitted_fronts)






def get_inprocess_parcels_contour(ProcessName:str) -> Polygon|None:
    return


def clear_map_selections() -> None:
    '''
    Clears all selections in the current map

    Returns:
        None
    '''
    aprx = ArcGISProject("CURRENT")
    active_map = aprx.activeMap
    if active_map:
            active_map.clearSelection()
    

def get_parcel_parameters_by_guid(parcel_guid: str) -> tuple[int, int, int, bool]:
    '''
    Retrieves the BlockNumber, SubBlockNumber and IsTax parameters of a block given its GlobalID.

    Parameters:
        block_guid (str): The GlobalID of the block.

    Returns:
        tuple[int, int, bool]: A tuple containing the BlockNumber, SubBlockNumber, and IsTax parameters.
    '''
    parcels_layer = get_layer('חלקות')
    with SearchCursor(parcels_layer, ['ParcelNumber', 'BlockUniqueID'], where_clause=f"GlobalID = '{parcel_guid}'") as cursor:
        row = next(cursor, None)  # Safely get the first row or None
        if row:
            parcel_number = row[0]
            block_parameters = get_block_parameters_by_guid(row[1])

            return (parcel_number, *block_parameters)
    return None


def get_block_parameters_by_guid(block_guid: str) -> tuple[int, int, bool]:
    '''
    Retrieves the BlockNumber, SubBlockNumber and IsTax parameters of a block given its GlobalID.

    Parameters:
        block_guid (str): The GlobalID of the block.

    Returns:
        tuple[int, int, bool]: A tuple containing the BlockNumber, SubBlockNumber, and IsTax parameters.
    '''
    blocks_layer = get_layer('גושים')
    with SearchCursor(blocks_layer, ['BlockNumber', 'SubBlockNumber', 'IsTax'], where_clause=f"GlobalID = '{block_guid}'") as cursor:
        row = next(cursor, None)  # Safely get the first row or None
        if row:
            block_number = row[0]
            sub_block_number = row[1]
            is_tax = bool(row[2])
            return block_number, sub_block_number, is_tax
    return None
        
def get_RecordGUID_NewCadaster(process_name: str) -> str:
    
    if is_guid_txt_file_exists(process_name):

        RecordGUID = get_RecordGUID(process_name,'SHELF')
    else:
        RecordGUID = get_RecordGUID(process_name,'MAP')


    if not RecordGUID:
        AddWarning(f'{timestamp()} | ⚠️ Record {process_name} Not found')
        return None

    return RecordGUID

def is_guid_txt_file_exists(process_name: str) -> bool:
    """
    Check if CNFG.Library/<process_name_sanitized>/guid.txt exists.
    The process_name is sanitized by replacing '/' with '_' (and '\' for safety).
    """
    if not process_name:
        return False
    folder_name = process_name.replace('/', '_').replace('\\', '_')
    guid_path = os.path.join(CNFG.Library, folder_name, 'RecordGUID.txt')
    return os.path.isfile(guid_path)


def is_tax_process(process_name:str) -> bool:

    block_GUID = get_BlockGUID('ProcessName',process_name)
    blocks_layer = get_layer('גושים')

    where_clause = f"GlobalID = '{block_GUID}'"
    is_tax = False

    with SearchCursor(blocks_layer, ['IsTax'], where_clause=where_clause) as cursor:
        for row in cursor:
            if row[0] == 1:
                is_tax = True
            break  
    #TODO return error if block not found
    return is_tax

def is_settled_block_by_process(process_name:str) -> bool:

    block_GUID = get_BlockGUID('ProcessName',process_name)
    blocks_layer = get_layer('גושים')

    where_clause = f"GlobalID = '{block_GUID}'"
    is_tax = False

    with SearchCursor(blocks_layer, ['LandType'], where_clause=where_clause) as cursor:
        for row in cursor:
            if row[0] == 1:
                is_tax = True
            break  

    return is_tax



def get_ProcessName() -> str:
    ''' 
    Retrieves the process name from the process border layer

    Returns:
        str: The name of the process.
    '''
    
    process_border_layer = get_layer('גבול תכנית')

    process_name = None
    with SearchCursor(process_border_layer, ['ProcessName']) as cursor:
        for row in cursor:
            process_name = row[0]
            break

    return process_name




def append_first_registration_parcels(ProcessName:str) -> None:
    ''' 
    Appending the first registration parcels to the parcels layer

    '''


    # currently just copied from append_settled_parcels - and added condition that checks if it's a tax process
    # generally, for none tax parcels, can add immediately, for tax parcels should check if parcels exist
    # still should deal with the final parcel numbers

    RecordGUID = get_RecordGUID_NewCadaster(ProcessName)
    ProcessGuid = get_ProcessGUID(ProcessName)
    process_parcels_layer = get_layer('חלקות בתהליך')   
    record_parcels_layer = get_layer('חלקות')

    exported_process_parcels = ExportFeatures(in_features=process_parcels_layer,out_features=r"memory\exported_process_parcels",
        where_clause=f"CPBUniqueID = '{ProcessGuid}'",field_mapping="")

    # Using CalculateField instead of UpdateCursor because of performance issues
    CalculateField(in_table=exported_process_parcels,field="CreatedByRecord",expression=f"'{RecordGUID}'",
        expression_type="PYTHON3",code_block="",field_type="TEXT",enforce_domains="NO_ENFORCE_DOMAINS")
    CalculateField(in_table=exported_process_parcels,field="LandType",expression="1",
        expression_type="PYTHON3",code_block="",field_type="TEXT",enforce_domains="NO_ENFORCE_DOMAINS")
    CalculateField(in_table=exported_process_parcels,field="CreateProcessType",expression=f"{Type2CreateType(get_ProcessType(ProcessName))}",
        expression_type="PYTHON3",code_block="",field_type="TEXT",enforce_domains="NO_ENFORCE_DOMAINS")

    if not is_tax_process(ProcessName):
        field_mapping = fr'Name "Name" true true true 255 Text 0 0,Join,"/",{process_parcels_layer.name},ParcelNumber,-1,-1,{process_parcels_layer.name},BlockNumber,-1,-1,{process_parcels_layer.name},SubBlockNumber,-1,-1;'+\
                fr'ParcelNumber "מספר חלקה" true false false 0 Short 0 0,First,#,{process_parcels_layer.name},ParcelNumber,-1,-1;'+\
                fr'BlockNumber "מספר גוש" true false false 0 Long 0 0,First,#,{process_parcels_layer.name},BlockNumber,-1,-1;'+\
                fr'SubBlockNumber "מספר תת-גוש" true false false 0 Short 0 0,First,#,{process_parcels_layer.name},SubBlockNumber,-1,-1;'+\
                fr'LandType "סוג מקרקעין" true false false 0 Short 0 0,First,#,{process_parcels_layer.name},LandType,-1,-1;'+\
                fr'IsTax "שומא" true false false 0 Short 0 0,First,#,{process_parcels_layer.name},IsTax,-1,-1;'+\
                fr'StatedArea "שטח רשום" true true true 0 Double 0 0,First,#,{process_parcels_layer.name},LegalArea,-1,-1;'+\
                fr'LandDesignationPlan "יעוד הקרקע" true true false 80 Text 0 0,First,#,{process_parcels_layer.name},LandDesignationPlan,0,79;'+\
                fr'ParcelType "סוג החלקה" true false false 0 Short 0 0,First,#,{process_parcels_layer.name},ParcelType,-1,-1;'+\
                fr'BlockUniqueID "מזהה גוש" true true false 38 Guid 0 0,First,#,{process_parcels_layer.name},BlockUniqueID,-1,-1;'+\
                fr'CreatedByRecord "מזהה תהליך יוצר" true true true 38 Guid 0 0,First,#,{process_parcels_layer.name},CreatedByRecord,0,511;'+\
                fr'CreateProcessType "סוג תהליך יוצר" true false false 512 Short 0 0,First,#,{process_parcels_layer.name},CreateProcessType,0,511;'+\
                fr'LandType "סוג מקרקעין" true false false 2 Short 0 0,First,#,{process_parcels_layer.name},LandType,-1,-1'
        
        Append(inputs=exported_process_parcels,target=record_parcels_layer,expression = "",field_mapping = field_mapping,
                                    schema_type="NO_TEST",subtype="",match_fields=None,update_geometry="NOT_UPDATE_GEOMETRY",feature_service_mode="USE_FEATURE_SERVICE_MODE")
        
    num_of_features = int(GetCount(exported_process_parcels).getOutput(0))

    Delete(exported_process_parcels)
    RefreshLayer(record_parcels_layer)
    reopen_map()

    return num_of_features



def insert_first_registration_parcels(process_name:str) -> None:
    ''' 
    Appending the first registration parcels to the parcels layer

    '''
    pass


def update_blocks_geometry_by_active_parcels(block_guid:str, record_guid:str) -> int:
    ''' 
    Updating the geometry of the block by the active parcels
    Returns:
        update_status (int):
        1 if geometry was updated 
        2 if no active parcels found while the block was still active, hence the block was retired
        0 if block was already retired or block was not found, so no actions were taken
    '''

    update_status = 0
    parcels_layer = get_layer('חלקות')
    blocks_layer = get_layer('גושים')

    SelectByAttribute(parcels_layer,where_clause=f"BlockUniqueID = '{block_guid}' AND RetiredByRecord IS NULL",selection_type='NEW_SELECTION')
    num_of_parcels = int(GetCount(parcels_layer).getOutput(0))
    if num_of_parcels > 0: 
        dissolved_parcels = Dissolve(in_features=parcels_layer, out_feature_class=r"memory\dissolved_parcels")
        #dissolved_parcels = Dissolve(in_features=parcels_layer, out_feature_class=r"memory\dissolved_parcels",multi_part="MULTI_PART",unsplit_lines="UNSPLIT_LINES")
        SelectByAttribute(blocks_layer,where_clause=f"GlobalID = '{block_guid}'",selection_type='NEW_SELECTION')

        with SearchCursor(dissolved_parcels, field_names="SHAPE@") as cursor:
            new_geometry = cursor.next()[0]

        editor = start_editing(CNFG.ParcelFabricDatabase)
        with UpdateCursor(blocks_layer, ["SHAPE@"]) as cursor:
                row = next(cursor, None)  # Safely get the first row or None
                if row:
                    row[0] = new_geometry
                    cursor.updateRow(row)
        stop_editing(editor)

        update_status = 1  # Geometry was updated

        #AddMessage(f'{timestamp()} | Updated geometry for block {block_guid} from the active parcels')
        Delete(dissolved_parcels)
    else:
        # Check if the block is already retired
        with SearchCursor(blocks_layer, ['RetiredByRecord'], where_clause=f"GlobalID = '{block_guid}'") as cursor:
            for row in cursor:
                row = next(cursor, None)  # Safely get the first row or None
                if row:
                    if not row[0]:
                        update_status = 2  # No active parcels found, block is still active and will be retired
                        editor = start_editing(CNFG.ParcelFabricDatabase)
                        with UpdateCursor(blocks_layer, ['RetiredByRecord'], where_clause=f"GlobalID = '{block_guid}'") as cursor:
                            for row in cursor:
                                if record_guid:
                                    row[0] = record_guid
                                    cursor.updateRow(row)
                        stop_editing(editor)

                

    SelectByAttribute(parcels_layer,selection_type='CLEAR_SELECTION')
    SelectByAttribute(blocks_layer,selection_type='CLEAR_SELECTION')
    reopen_map()
    return update_status


def update_settled_block_geometry(processName:str) -> None:
    ''' 
    Updating current block's data (Shape,LastSetteledParcel,CreatedByRecord,BlockStatus,LandType)

    '''
    

    Process_border_layer = get_layer('גבול תכנית')
    Block_layer = get_layer('גוש הסדר')

    editor = start_editing(CNFG.ParcelFabricDatabase)
    

   
    # Get the single feature from Process_border_layer
    with SearchCursor(Process_border_layer, field_names="SHAPE@") as cursor:
        process_geometry = cursor.next()[0]



    is_updated = False
    # Update the CreatedByRecord, LandType, and BlockStatus fields in the single feature of the Block_layer
    with UpdateCursor(Block_layer, ["SHAPE@","CreatedByRecord", "LandType", "BlockStatus", "LastSetteledParcel"]) as cursor:
        row = next(cursor, None)  # Safely get the first row or None
        if row:
            row[0] = process_geometry      # SHAPE@
            cursor.updateRow(row)
            is_updated = True


    if is_updated:

        AddMessage(f'                Geometry was updated')

    else:
        AddWarning(f'                Was unable to update the block\'s geometry')

    stop_editing(editor)




def layer_exists(layer_name)-> bool:
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


def print_empty_layers(layers_list:list, layers_type:str = 'required' or 'not required') -> None:
    '''
    Prints a list of empty layers with an appropriate message

    Parameters:
        layers_list (list): A list of empty layers.
        layers_type (str): The type of layers, required or not required. 
                            For the required layers an error message will be printed.
    Returns:
        None
    '''
    if layers_list:
        for layer in layers_list:
            if layers_type == 'required':
                AddError(f'                 • The required layer {layer} is empty. Check in-Process data')
            else: # layers_type == 'not required'
                AddMessage(f"                   • No {layer} were found")

def count_features_in_group(group_layer, required_layers:list = None) -> None:
    '''
    Counts features in a group layer, prints the results and deletes empty layers.
    There is an option to pass a list of required layers that will be checked for features existence
        and if empty, an error message will be printed

    Parameters:
        group_layer (GroupLayer): The group layer to count features in.
        required_layers (list): An optional list of required layers to check for features existence.
    Returns:
        None
    '''

    if group_layer and group_layer.isGroupLayer:
        AddMessage(f'{timestamp()} | ✴️ The layers group {group_layer.name} was created. Counting features:') 

        inprocess_points = get_layer('נקודות בתהליך')
        inprocess_fronts = get_layer('חזיתות בתהליך')

        empty_non_required_layers = []
        empty_required_layers = []
        for layer in group_layer.listLayers():
            if not layer.isGroupLayer:


                # There is a bug and the GetCount function won't properly count features in 4 of the layers
                #   so to bypass it, using combination of definition query retrieval and SelectByAttribute from the main layers 
                #   to get the correct features count for these layers
                
                if layer.name in ['נקודות ביסוס','נקודות חדשות']:
                    def_query = layer.definitionQuery
                    SelectByAttribute(inprocess_points,where_clause=def_query,selection_type='NEW_SELECTION')
                    feature_count = int(GetCount(inprocess_points).getOutput(0))
                    SelectByAttribute(inprocess_points, "CLEAR_SELECTION")
                elif layer.name in ['חזיתות ביסוס','חזיתות חדשות']:
                    def_query = layer.definitionQuery
                    SelectByAttribute(inprocess_fronts,where_clause=def_query,selection_type='NEW_SELECTION')
                    feature_count = int(GetCount(inprocess_fronts).getOutput(0))
                    SelectByAttribute(inprocess_fronts, "CLEAR_SELECTION")
                else:
                    feature_count = int(GetCount(layer).getOutput(0))

                if feature_count > 0: # looking for larger than 0 because it could be -1 when it has a wrong (empty) definition query
                    AddMessage(f"                   • The layer {layer.name} has {feature_count} features")
                elif layer.name not in required_layers:
                    empty_non_required_layers.append(layer.name)
                    #AddMessage(f"                   • No {layer.name} were found")
                    Delete(layer)
                else:
                    empty_required_layers.append(layer.name)
                    #AddError(f'                 • The required layer {layer.name} is empty. Check in-Process data')

        
            else:
                print_empty_layers(empty_non_required_layers, 'not required')
                print_empty_layers(empty_required_layers, 'required')
                AddMessage(f"               The subgroup {layer.name}:")
                empty_non_required_layers = []
                empty_required_layers = []
        print_empty_layers(empty_non_required_layers, 'not required')
        print_empty_layers(empty_required_layers, 'required')

        
        del [inprocess_points,inprocess_fronts]

    else:
        AddError(f'{timestamp()} | ⚠️ The group layer {group_layer.name} was not created. Check the data and the existance of a proper *.lyrx file')



def set_environment_extent(ProcessName:str, buffer_dist:int = 30) -> None:
    '''
    Sets the environment extent to the extent of the process borders layer with an optional addition of a buffer distance
    The extent is a rectangle defined by a pair of coordinates: the lower-left corner and the upper-right corner

    Parameters:
        ProcessName (str): The name of the process
        buffer_dist (int): The buffer distance in meters that will be added to the upper-right corner 
                            and subtracted from the lower-left corner of the extent (both X and Y)

    Returns:
        None
    '''
    process_borders = get_layer('גבולות תהליכי קדסטר')
    ProcessGUID = get_ProcessGUID(ProcessName)
    process_border = SelectByAttribute(process_borders,where_clause=f""" GlobalID = '{ProcessGUID}' """,selection_type='NEW_SELECTION')

    layer_desc = Describe(process_border)
    layer_extent = layer_desc.extent
    
    expanded_extent = Extent(
        layer_extent.XMin - buffer_dist,
        layer_extent.YMin - buffer_dist,
        layer_extent.XMax + buffer_dist,
        layer_extent.YMax + buffer_dist,
    )

    ENV.extent = expanded_extent

    SelectByAttribute(process_borders, "CLEAR_SELECTION")
    del [process_border,process_borders,layer_desc,layer_extent,expanded_extent]


def update_connections() -> None:
    '''
        Updates layers' source from default to the current version

        Parameters:
        TaskType (str): The Task's type, CreateNewCadaster or ImproveNewCadaster

        Returns:
            None
    '''
    

    CONNECTION_PROPERTIES_MAP = {
        "גושים": ["גוש הסדר","גושים לא מוסדרים", "גושים מוסדרים"],
        "חלקות": ["חלקות לא מוסדרות", "חלקות מוסדרות"],
        #"נקודות גבול": ["נקודות גבול קיימות"],
        #"חזיתות": ["חזיתות קיימות"]
    }


    
    for base_layer_name, target_layers in CONNECTION_PROPERTIES_MAP.items():

        base_conn = get_layer(base_layer_name).connectionProperties

        for target_layer_name in target_layers:
            if layer_exists(target_layer_name):
                target_layer = get_layer(target_layer_name)
                if target_layer:
                    target_layer.updateConnectionProperties(target_layer.connectionProperties, base_conn)


    reopen_map()

def filter_process_layers_group(ProcessName:str, TaskType:str = 'CreateNewCadaster' or 'ImproveNewCadaster',search_distance:int="10") -> None:
    '''
    Filters the layers in the process layers\'s group based on the process borders layer, the task type and the search distance

    Parameters:
        ProcessName (str): The name of the process
        TaskType (str): The Task's type, CreateNewCadaster or ImproveNewCadaster
        search_distance (int): The search distance in meters to be used while looking for intersecting features using SelectByLocation 

    Returns:
        None
    '''

    ProcessGUID = get_ProcessGUID(ProcessName)


    if TaskType == 'CreateNewCadaster':

        BlockGUID = get_BlockGUID('ProcessName',ProcessName)
        settled_blocks_query = f"""LandType=1 AND RetiredByRecord IS NULL AND GlobalID <> '{BlockGUID}'"""
        unsettled_blocks_query = f"""LandType=2 AND RetiredByRecord IS NULL AND GlobalID <> '{BlockGUID}'"""
        new_points_layer = get_layer('נקודות חדשות')
        new_fronts_layer = get_layer('חזיתות חדשות')
        process_parcels_layer = get_layer('חלקות ביסוס')
        process_parcels_layer.updateDefinitionQueries([{'name':'Query 1', 'sql':f""" CPBUniqueID = '{ProcessGUID}' """, 'isActive':True}])
        if get_ProcessType(ProcessName) == 9: #(הסדר)
            settled_block_layer = get_layer('גוש הסדר')
            settled_block_layer.updateDefinitionQueries([{'name':'Query 1', 'sql':f""" GlobalID = '{BlockGUID}' """, 'isActive':True}]) 
        else: #(רישום ראשון)
            process_operations_table = get_layer('פעולות בתכנית')
            process_operations_table.updateDefinitionQueries([{'name':'Query 1', 'sql':f""" GlobalID = '{BlockGUID}' """, 'isActive':True}]) 

    else: #TaskType == 'ImproveNewCadaster'
        settled_blocks_query = f"""LandType=1 AND RetiredByRecord IS NULL"""
        unsettled_blocks_query = f"""LandType=2 AND RetiredByRecord IS NULL"""

    in_process_fronts_layer = get_layer('חזיתות בתהליך')
    in_process_points_layer = get_layer('נקודות בתהליך')
    blocks_layer = get_layer('גושים')
    #border_points_layer = get_layer('נקודות גבול')
    #fronts_layer = get_layer('חזיתות')
    current_process_border_layer = get_layer('גבול תכנית')
    process_base_points_layer = get_layer('נקודות ביסוס')
    process_base_fronts_layer = get_layer('חזיתות ביסוס')
    #neighboring_existing_points_layer = get_layer('נקודות גבול קיימות')
    #neighboring_existing_fronts_layer = get_layer('חזיתות קיימות')
    neighboring_settled_parcels_layer = get_layer('חלקות מוסדרות')
    neighboring_settled_blocks_layer = get_layer('גושים מוסדרים')
    neighboring_unsettled_parcels_layer = get_layer('חלקות לא מוסדרות')
    neighboring_unsettled_blocks_layer = get_layer('גושים לא מוסדרים')

    if TaskType == 'CreateNewCadaster' and not is_process_border_valid(ProcessName):
        # This part is added to deal with cases where the process border geometry is incorrect
        AddMessage(f'{timestamp()} | ⚠️ The process border for process {ProcessName} is not matching to the process\' parcels geometry.')
        AddMessage(f'      The process border layer will be redirected to a local feature class with the correct geometry.')
        local_fc_name = f"ProcessBorder_{ProcessName.replace('/','_')}"
        default_gdb = get_default_gdb()
        old_properties = current_process_border_layer.connectionProperties
        new_properties = {
            "workspace_factory": "File Geodatabase",
            "connection_info": {"database": default_gdb},
            "dataset": local_fc_name
        }
        current_process_border_layer.updateConnectionProperties(old_properties, new_properties)
        
    current_process_border_layer.updateDefinitionQueries([{'name':'Query 1', 'sql':f""" GlobalID = '{ProcessGUID}' """, 'isActive':True}])   
    
    # may be needed later
    #if TaskType == 'CreateNewCadaster':
    #    update_settled_block_geometry(ProcessName)
 
    update_connections()



    all_settled_blocks = SelectByAttribute(blocks_layer,where_clause=settled_blocks_query,selection_type='NEW_SELECTION')
    intersecting_settled_blocks = SelectByLocation(all_settled_blocks,'INTERSECT',select_features=current_process_border_layer,search_distance=f"{search_distance} Meters",selection_type="SUBSET_SELECTION")
    query = [row[0] for row in SearchCursor(intersecting_settled_blocks, 'GlobalID')]
    joined_string = ",".join(f"'{uniqueID}'" for uniqueID in query)
    sql_list = f"({joined_string})"

    neighboring_settled_blocks_layer.updateDefinitionQueries([{'name':'Query 1', 'sql':f""" GlobalID IN {sql_list} """, 'isActive':True}])   
    neighboring_settled_parcels_layer.updateDefinitionQueries([{'name':'Query 1', 'sql':f""" BlockUniqueID IN {sql_list} And RetiredByRecord IS NULL """, 'isActive':True}]) 


    SelectByAttribute(blocks_layer,selection_type="CLEAR_SELECTION",where_clause="",invert_where_clause=None)
    
    all_unsettled_blocks = SelectByAttribute(blocks_layer,where_clause=unsettled_blocks_query,selection_type='NEW_SELECTION')
    intersecting_unsettled_blocks = SelectByLocation(all_unsettled_blocks,'INTERSECT',select_features=current_process_border_layer,search_distance=f"{search_distance} Meters",selection_type="SUBSET_SELECTION")
    query = [row[0] for row in SearchCursor(intersecting_unsettled_blocks, 'GlobalID')]
    joined_string = ",".join(f"'{uniqueID}'" for uniqueID in query)
    sql_list = f"({joined_string})"
    

    neighboring_unsettled_blocks_layer.updateDefinitionQueries([{'name':'Query 1', 'sql':f""" GlobalID IN {sql_list} AND RetiredByRecord IS NULL""", 'isActive':True}])   
    neighboring_unsettled_parcels_layer.updateDefinitionQueries([{'name':'Query 1', 'sql':f""" BlockUniqueID IN {sql_list} And RetiredByRecord IS NULL """, 'isActive':True}]) 

    
    SelectByAttribute(blocks_layer,selection_type="CLEAR_SELECTION",where_clause="",invert_where_clause=None)

    all_process_points = SelectByAttribute(in_process_points_layer,where_clause=f"""CPBUniqueID = '{ProcessGUID}'""",selection_type='NEW_SELECTION')
    external_process_points = SelectByLocation(in_layer=all_process_points,overlap_type="BOUNDARY_TOUCHES",select_features=current_process_border_layer,search_distance=None,selection_type="SUBSET_SELECTION")
    query = [row[0] for row in SearchCursor(external_process_points, 'GlobalID')]
    joined_string = ",".join(f"'{uniqueID}'" for uniqueID in query)
    sql_list = f"({joined_string})"
    process_base_points_layer.updateDefinitionQueries([{'name':'Query 1', 'sql':f""" GlobalID IN {sql_list} """, 'isActive':True}])   
    if TaskType == 'CreateNewCadaster':
        SelectByAttribute(in_process_points_layer,selection_type="CLEAR_SELECTION",where_clause="",invert_where_clause=None)
        new_points_layer.updateDefinitionQueries([{'name':'Query 1', 'sql':f""" GlobalID NOT IN {sql_list} AND CPBUniqueID = '{ProcessGUID}' """, 'isActive':True}])   
    SelectByAttribute(in_process_points_layer,selection_type="CLEAR_SELECTION",where_clause="",invert_where_clause=None)



    all_process_fronts = SelectByAttribute(in_process_fronts_layer,where_clause=f"""CPBUniqueID = '{ProcessGUID}'""",selection_type='NEW_SELECTION')
    external_process_fronts = SelectByLocation(in_layer=all_process_fronts,overlap_type="SHARE_A_LINE_SEGMENT_WITH",select_features=current_process_border_layer,search_distance=None,selection_type="SUBSET_SELECTION")
    query = [row[0] for row in SearchCursor(external_process_fronts, 'GlobalID')]
    joined_string = ",".join(f"'{uniqueID}'" for uniqueID in query)
    sql_list = f"({joined_string})"
    process_base_fronts_layer.updateDefinitionQueries([{'name':'Query 1', 'sql':f""" GlobalID IN {sql_list} """, 'isActive':True}]) 
    if TaskType == 'CreateNewCadaster':
        SelectByAttribute(in_process_fronts_layer,selection_type="CLEAR_SELECTION",where_clause="",invert_where_clause=None)
        new_fronts_layer.updateDefinitionQueries([{'name':'Query 1', 'sql':f""" GlobalID NOT IN {sql_list} AND CPBUniqueID = '{ProcessGUID}' """, 'isActive':True}])   
    SelectByAttribute(in_process_fronts_layer,selection_type="CLEAR_SELECTION",where_clause="",invert_where_clause=None)


    '''
    intersecting_points = SelectByLocation(border_points_layer,'INTERSECT',select_features=current_process_border_layer,search_distance=f"{search_distance} Meters",selection_type='NEW_SELECTION')
    query = [row[0] for row in SearchCursor(intersecting_points, 'GlobalID')]
    joined_string = ",".join(f"'{uniqueID}'" for uniqueID in query)
    sql_list = f"({joined_string})"

    neighboring_existing_points_layer.updateDefinitionQueries([{'name':'Query 1', 'sql':f""" GlobalID IN {sql_list} AND RetiredByRecord IS NULL""", 'isActive':True}])     

    
    SelectByAttribute(border_points_layer,selection_type="CLEAR_SELECTION",where_clause="",invert_where_clause=None)

    
    intersecting_fronts = SelectByLocation(fronts_layer,'INTERSECT',select_features=current_process_border_layer,search_distance=f"{search_distance} Meters",selection_type='NEW_SELECTION')
    query = [row[0] for row in SearchCursor(intersecting_fronts, 'GlobalID')]
    joined_string = ",".join(f"'{uniqueID}'" for uniqueID in query)
    sql_list = f"({joined_string})"

    neighboring_existing_fronts_layer.updateDefinitionQueries([{'name':'Query 1', 'sql':f""" GlobalID IN {sql_list} AND RetiredByRecord IS NULL""", 'isActive':True}])     



    SelectByAttribute(fronts_layer,selection_type="CLEAR_SELECTION",where_clause="",invert_where_clause=None)
    '''

    del [all_settled_blocks,intersecting_settled_blocks,all_process_points,external_process_points,all_process_fronts,external_process_fronts,
        process_base_fronts_layer, process_base_points_layer, current_process_border_layer, 
        neighboring_settled_blocks_layer, neighboring_settled_parcels_layer,neighboring_unsettled_parcels_layer,neighboring_unsettled_blocks_layer,
        in_process_fronts_layer,in_process_points_layer,blocks_layer]
    #del [neighboring_existing_fronts_layer,fronts_layer,border_points_layer,neighboring_existing_points_layer,intersecting_fronts,intersecting_points]
    if TaskType == 'CreateNewCadaster':
        if get_ProcessType(ProcessName) == 9: #(הסדר)
             del [new_points_layer, new_fronts_layer, process_parcels_layer, settled_block_layer]
        else: #(רישום ראשון)
             del [process_operations_table]
       




def update_layer_fields_dict(input_layer, updates_dict, method='UpdateCursor' or 'CalculateField', clear_selection:bool = True, where_clause=None):
    
    num_of_updated_rows = 0
    if clear_selection:
        SelectByAttribute(input_layer, "CLEAR_SELECTION")

    if method == 'UpdateCursor':

        # Extract the field names and corresponding values from the dictionary
        fields_to_update = list(updates_dict.keys())

        # Start an edit session
        editor = start_editing(CNFG.ParcelFabricDatabase)

        try:
            with UpdateCursor(input_layer, fields_to_update, where_clause=where_clause) as cursor:
                for row in cursor:
                    # For each row, update all specified fields
                    for i, field_name in enumerate(fields_to_update):
                        row[i] = updates_dict[field_name]

                    # Update the row
                    cursor.updateRow(row)
                    num_of_updated_rows += 1
        finally:
            # Stop the edit session (commit by default, or roll back if errors occur)
            stop_editing(editor)

    elif method == 'CalculateField':

        # Select matching rows in the existing layer or table view
        if where_clause:
            SelectByAttribute(input_layer,"NEW_SELECTION",where_clause)
        # Loop through each field update and call CalculateField
        for field_name, calc_info in updates_dict.items():

            if isinstance(calc_info, tuple):
                # If the user passed in (expression, code_block)
                expression, code_block = calc_info
            else:
                # Otherwise, treat it as a constant (or string) expression
                # Make sure it's a string if it's numeric, e.g. "1"
                expression = str(calc_info)
                code_block = None

            CalculateField(in_table=input_layer,field=field_name,expression=expression,expression_type="PYTHON3",code_block=code_block)
            num_of_updated_rows += 1

    return num_of_updated_rows

def insert_process_to_records(ProcessName:str) -> int:
        
    process_borders_layer = get_layer('גבולות תהליכי קדסטר')
    record_borders_layer  = get_layer('גבולות רישומים')

    # Define the fields to copy
    fields = [
        "ProcessName", "ProcessType", "GeodeticNetwork", "Status", "SurveyorLicenseID",
        "DataSource", "PlanName", "BlockUniqueID", "SHAPE@"
    ]
    target_fields = [
        "Name", "RecordType", "GeodeticNetwork", "Status", "SurveyorLicenseID",
        "DataSource", "PlanName", "BlockUniqueID", "SHAPE@"
    ]

    # Select features to copy
    where_clause = f"ProcessName = '{ProcessName}'"
    rows_to_insert = []
    with SearchCursor(process_borders_layer, fields, where_clause=where_clause) as search_cursor:
        for row in search_cursor:
            rows_to_insert.append(row)

    # Insert into target layer
    editor = start_editing(CNFG.ParcelFabricDatabase)
    inserted_count = 0
    try:
        with InsertCursor(record_borders_layer, target_fields) as insert_cursor:
            for row in rows_to_insert:
                insert_cursor.insertRow(row)
                inserted_count += 1
    finally:
        stop_editing(editor)

    RefreshLayer(record_borders_layer)
    reopen_map()

    return inserted_count




def append_process_to_records(ProcessName:str) -> int:
        
    process_borders_layer = get_layer('גבולות תהליכי קדסטר')
    record_borders_layer  = get_layer('גבולות רישומים')

    field_mapping = fr'Name "שם מפה" true true true 255 Text 0 0,First,#,{process_borders_layer.name},ProcessName,0,100;'+\
                fr'RecordType "סוג תהליך" true true true 4 Long 0 0,First,#,{process_borders_layer.name},ProcessType,-1,-1;'+\
                fr'GeodeticNetwork "רשת בקרה" true true false 2 Short 0 0,First,#,{process_borders_layer.name},GeodeticNetwork,-1,-1;'+\
                fr'Status "סטטוס" true true false 2 Short 0 0,First,#,{process_borders_layer.name},Status,-1,-1;'+\
                fr'SurveyorLicenseID "רשיון מודד" true true false 2 Short 0 0,First,#,{process_borders_layer.name},SurveyorLicenseID,-1,-1;'+\
                fr'DataSource "מקור הנתונים" true true false 2 Short 0 0,First,#,{process_borders_layer.name},DataSource,-1,-1;'+\
                fr'PlanName "תכנית מפורטת" true true false 255 Text 0 0,First,#,{process_borders_layer.name},PlanName,0,255;'+\
                fr'BlockUniqueID "מזהה גוש" true true false 38 Guid 0 0,First,#,{process_borders_layer.name},BlockUniqueID,-1,-1'              


    Append(inputs = process_borders_layer, target = record_borders_layer, expression = f"ProcessName = '{ProcessName}'", field_mapping = field_mapping,
         schema_type = "NO_TEST", subtype = "", match_fields = None, update_geometry = "NOT_UPDATE_GEOMETRY")

    reopen_map()

    SelectByAttribute(record_borders_layer,where_clause=f"Name = '{ProcessName}'",selection_type="NEW_SELECTION")
    appended_features_count = int(GetCount(record_borders_layer).getOutput(0))
    SelectByAttribute(record_borders_layer, "CLEAR_SELECTION")

    return appended_features_count


def insert_settled_parcels(ProcessName:str) -> int:

    RecordGUID = get_RecordGUID_NewCadaster(ProcessName)
    #BlockGUID = get_BlockGUID('ProcessName', ProcessName)
    ProcessGuid = get_ProcessGUID(ProcessName)
    process_parcels_layer = get_layer('חלקות בתהליך')
    record_parcels_layer = get_layer('חלקות')

    # Define the fields to copy from process_parcels_layer and their mapping to record_parcels_layer
    source_fields = [
        "ParcelNumber", "BlockNumber", "SubBlockNumber", "IsTax",
        "LegalArea", "LandDesignationPlan", "ParcelType", "BlockUniqueID", "SHAPE@"
    ]
    target_fields = [
        "ParcelNumber", "BlockNumber", "SubBlockNumber", "IsTax",
        "StatedArea", "LandDesignationPlan", "ParcelType", "BlockUniqueID", "SHAPE@",
        "CreatedByRecord","LandType","CreateProcessType"
    ]

    # Select features to copy
    where_clause = f"CPBUniqueID = '{ProcessGuid}'"
    rows_to_insert = []
    with SearchCursor(process_parcels_layer, source_fields, where_clause=where_clause) as search_cursor:
        for row in search_cursor:
            rows_to_insert.append(row)

    # Insert into target layer
    editor = start_editing(CNFG.ParcelFabricDatabase)
    inserted_count = 0
    try:
        with InsertCursor(record_parcels_layer, target_fields) as insert_cursor:
            for row in rows_to_insert:
                parcel_row = row + (RecordGUID, "1", "3")
                insert_cursor.insertRow(parcel_row)
                inserted_count += 1
    finally:
        stop_editing(editor)

    RefreshLayer(record_parcels_layer)
    reopen_map()

    return inserted_count


def append_settled_parcels(ProcessName:str) -> int:

    
    RecordGUID = get_RecordGUID_NewCadaster(ProcessName)
    ProcessGuid = get_ProcessGUID(ProcessName)
    process_parcels_layer = get_layer('חלקות בתהליך')   
    record_parcels_layer = get_layer('חלקות')

    exported_process_parcels = ExportFeatures(in_features=process_parcels_layer,out_features=r"memory\exported_process_parcels",
        where_clause=f"CPBUniqueID = '{ProcessGuid}'",field_mapping="")

    # Using CalculateField instead of UpdateCursor because of performance issues
    CalculateField(in_table=exported_process_parcels,field="CreatedByRecord",expression=f"'{RecordGUID}'",
        expression_type="PYTHON3",code_block="",field_type="TEXT",enforce_domains="NO_ENFORCE_DOMAINS")
    CalculateField(in_table=exported_process_parcels,field="LandType",expression="1",
        expression_type="PYTHON3",code_block="",field_type="TEXT",enforce_domains="NO_ENFORCE_DOMAINS")
    CalculateField(in_table=exported_process_parcels,field="CreateProcessType",expression=f"{Type2CreateType(get_ProcessType(ProcessName))}",
        expression_type="PYTHON3",code_block="",field_type="TEXT",enforce_domains="NO_ENFORCE_DOMAINS")


    field_mapping = fr'Name "Name" true true true 255 Text 0 0,Join,"/",{process_parcels_layer.name},ParcelNumber,-1,-1,{process_parcels_layer.name},BlockNumber,-1,-1,{process_parcels_layer.name},SubBlockNumber,-1,-1;'+\
            fr'ParcelNumber "מספר חלקה" true false false 0 Short 0 0,First,#,{process_parcels_layer.name},ParcelNumber,-1,-1;'+\
            fr'BlockNumber "מספר גוש" true false false 0 Long 0 0,First,#,{process_parcels_layer.name},BlockNumber,-1,-1;'+\
            fr'SubBlockNumber "מספר תת-גוש" true false false 0 Short 0 0,First,#,{process_parcels_layer.name},SubBlockNumber,-1,-1;'+\
            fr'LandType "סוג מקרקעין" true false false 0 Short 0 0,First,#,{process_parcels_layer.name},LandType,-1,-1;'+\
            fr'IsTax "שומא" true false false 0 Short 0 0,First,#,{process_parcels_layer.name},IsTax,-1,-1;'+\
            fr'StatedArea "שטח רשום" true true true 0 Double 0 0,First,#,{process_parcels_layer.name},LegalArea,-1,-1;'+\
            fr'LandDesignationPlan "יעוד הקרקע" true true false 80 Text 0 0,First,#,{process_parcels_layer.name},LandDesignationPlan,0,79;'+\
            fr'ParcelType "סוג החלקה" true false false 0 Short 0 0,First,#,{process_parcels_layer.name},ParcelType,-1,-1;'+\
            fr'BlockUniqueID "מזהה גוש" true true false 38 Guid 0 0,First,#,{process_parcels_layer.name},BlockUniqueID,-1,-1;'+\
			fr'CreatedByRecord "מזהה תהליך יוצר" true true true 38 Guid 0 0,First,#,{process_parcels_layer.name},CreatedByRecord,0,511;'+\
			fr'CreateProcessType "סוג תהליך יוצר" true false false 512 Short 0 0,First,#,{process_parcels_layer.name},CreateProcessType,0,511;'+\
			fr'LandType "סוג מקרקעין" true false false 2 Short 0 0,First,#,{process_parcels_layer.name},LandType,-1,-1'
    
    Append(inputs=exported_process_parcels,target=record_parcels_layer,expression = "",field_mapping = field_mapping,
                                schema_type="NO_TEST",subtype="",match_fields=None,update_geometry="NOT_UPDATE_GEOMETRY",feature_service_mode="USE_FEATURE_SERVICE_MODE")
    
    num_of_features = int(GetCount(exported_process_parcels).getOutput(0))

    Delete(exported_process_parcels)
    RefreshLayer(record_parcels_layer)
    reopen_map()

    return num_of_features


def append_settled_parcels_old(ProcessName:str) -> tuple[int,int]:

    RecordGUID = get_RecordGUID_NewCadaster(ProcessName)
    BlockGUID = get_BlockGUID('ProcessName',ProcessName)
    ProcessGuid = get_ProcessGUID(ProcessName)
    process_parcels_layer = get_layer('חלקות בתהליך')   
    record_parcels_layer = get_layer('חלקות')



    field_mapping = fr'Name "Name" true true true 255 Text 0 0,Join,"/",{process_parcels_layer.name},ParcelNumber,-1,-1,{process_parcels_layer.name},BlockNumber,-1,-1,{process_parcels_layer.name},SubBlockNumber,-1,-1;'+\
            fr'ParcelNumber "מספר חלקה" true false false 0 Short 0 0,First,#,{process_parcels_layer.name},ParcelNumber,-1,-1;'+\
            fr'BlockNumber "מספר גוש" true false false 0 Long 0 0,First,#,{process_parcels_layer.name},BlockNumber,-1,-1;'+\
            fr'SubBlockNumber "מספר תת-גוש" true false false 0 Short 0 0,First,#,{process_parcels_layer.name},SubBlockNumber,-1,-1;'+\
            fr'LandType "סוג מקרקעין" true false false 0 Short 0 0,First,#,{process_parcels_layer.name},LandType,-1,-1;'+\
            fr'IsTax "שומא" true false false 0 Short 0 0,First,#,{process_parcels_layer.name},IsTax,-1,-1;'+\
            fr'StatedArea "שטח רשום" true true true 0 Double 0 0,First,#,{process_parcels_layer.name},LegalArea,-1,-1;'+\
            fr'LandDesignationPlan "יעוד הקרקע" true true false 80 Text 0 0,First,#,{process_parcels_layer.name},LandDesignationPlan,0,79;'+\
            fr'ParcelType "סוג החלקה" true false false 0 Short 0 0,First,#,{process_parcels_layer.name},ParcelType,-1,-1;'+\
            fr'BlockUniqueID "מזהה גוש" true true false 38 Guid 0 0,First,#,{process_parcels_layer.name},BlockUniqueID,-1,-1'

    
    Append(inputs=process_parcels_layer,target=record_parcels_layer,expression = f"CPBUniqueID = '{ProcessGuid}'",field_mapping = field_mapping,
        schema_type="NO_TEST",subtype="",match_fields=None,update_geometry="NOT_UPDATE_GEOMETRY")
    
    reopen_map()

    SelectByAttribute(record_parcels_layer,where_clause=f"""BlockUniqueID='{BlockGUID}' AND RetiredByRecord IS NULL""",selection_type="NEW_SELECTION")
    appended_features_count = int(GetCount(record_parcels_layer).getOutput(0))
    SelectByAttribute(record_parcels_layer, "CLEAR_SELECTION")
  
    inserted_parcels = SelectByAttribute(record_parcels_layer,where_clause=f"""BlockUniqueID='{BlockGUID}' AND RetiredByRecord IS NULL""",selection_type='NEW_SELECTION')
    calculated_features_count = int(GetCount(inserted_parcels)[0])

    CalculateField(in_table=inserted_parcels,field="CreatedByRecord",expression=f"'{RecordGUID}'",
        expression_type="SQL",code_block="",field_type="TEXT",enforce_domains="NO_ENFORCE_DOMAINS")

    CalculateField(in_table=inserted_parcels,field="LandType",expression="1",
        expression_type="SQL",code_block="",field_type="TEXT",enforce_domains="NO_ENFORCE_DOMAINS")
    
    CalculateField(in_table=inserted_parcels,field="CreateProcessType",expression="3",
        expression_type="SQL",code_block="",field_type="TEXT",enforce_domains="NO_ENFORCE_DOMAINS")
    

    return appended_features_count, calculated_features_count


def insert_new_fronts(ProcessName:str, query:str) -> int:
            
    RecordGUID = get_RecordGUID_NewCadaster(ProcessName)
    Process_GUID = get_ProcessGUID(ProcessName)

    process_fronts_layer = get_layer('חזיתות בתהליך')
    record_fronts_layer = get_layer('חזיתות')

    # Define the fields to copy and their mapping
    source_fields = [
        "LineType", "LegalLength", "Radius", "SHAPE@"
    ]
    target_fields = [
        "LineType", "Distance", "Radius", "SHAPE@", "CreatedByRecord"
    ]

    # Select features to copy based on the query
    rows_to_insert = []
    with SearchCursor(process_fronts_layer, source_fields, where_clause=query) as search_cursor:
        for row in search_cursor:
            rows_to_insert.append(row)

    # Insert into target layer
    editor = start_editing(CNFG.ParcelFabricDatabase)
    inserted_count = 0
    try:
        with InsertCursor(record_fronts_layer, target_fields) as insert_cursor:
            for row in rows_to_insert:
                front_row = row + (RecordGUID,)
                insert_cursor.insertRow(front_row)
                inserted_count += 1
    finally:
        stop_editing(editor)

    RefreshLayer(record_fronts_layer)
    reopen_map()

    return inserted_count

def append_new_fronts(ProcessName:str, query:str) -> int:


    RecordGUID = get_RecordGUID_NewCadaster(ProcessName)
    Process_GUID = get_ProcessGUID(ProcessName)

    process_fronts_layer = get_layer('חזיתות בתהליך')
    record_fronts_layer = get_layer('חזיתות')

    exported_process_fronts = ExportFeatures(in_features=process_fronts_layer,out_features=r"memory\exported_process_fronts",
        where_clause=query,field_mapping="")
    
    CalculateField(in_table=exported_process_fronts,field="CreatedByRecord",expression=f"'{RecordGUID}'",
        expression_type="PYTHON3",code_block="",field_type="TEXT",enforce_domains="NO_ENFORCE_DOMAINS")

    field_mapping = fr'LineType "סוג הקו" true false true 0 Short 0 0,First,#,{process_fronts_layer.name},LineType,-1,-1;' + \
        fr'Distance "אורך רשום" true true true 0 Double 0 0,First,#,{process_fronts_layer.name},LegalLength,-1,-1;' + \
        fr'Radius "רדיוס" true true true 0 Double 0 0,First,#,{process_fronts_layer.name},Radius,-1,-1;' + \
        fr'CreatedByRecord "מזהה תהליך יוצר" true true true 38 Guid 0 0,First,#,{process_fronts_layer.name},CreatedByRecord,0,511'

    Append(inputs=process_fronts_layer,target=record_fronts_layer,expression = "",field_mapping = field_mapping,
        schema_type="NO_TEST",subtype="",match_fields=None,update_geometry="NOT_UPDATE_GEOMETRY")
    
    num_of_features = int(GetCount(exported_process_fronts).getOutput(0))

    Delete(process_fronts_layer)
    RefreshLayer(record_fronts_layer)
    reopen_map()

    return num_of_features




    pass

def append_new_fronts_old(ProcessName:str, query:str) -> tuple[int,int]:
            
    RecordGUID = get_RecordGUID_NewCadaster(ProcessName)
    Process_GUID = get_ProcessGUID(ProcessName)

    process_fronts_layer = get_layer('חזיתות בתהליך')
    record_fronts_layer = get_layer('חזיתות')
    


    field_mapping = fr'LineType "סוג הקו" true false true 0 Short 0 0,First,#,{process_fronts_layer.name},LineType,-1,-1;' + \
        fr'Distance "אורך רשום" true true true 0 Double 0 0,First,#,{process_fronts_layer.name},LegalLength,-1,-1;' + \
        fr'Radius "רדיוס" true true true 0 Double 0 0,First,#,{process_fronts_layer.name},Radius,-1,-1;' + \
        fr'CreatedByRecord "מזהה תהליך יוצר" true true true 38 Guid 0 0,First,#,{process_fronts_layer.name},CPBUniqueID,-1,-1'

    Append(inputs=process_fronts_layer,target=record_fronts_layer,expression = query,field_mapping = field_mapping,
        schema_type="NO_TEST",subtype="",match_fields=None,update_geometry="NOT_UPDATE_GEOMETRY")

    reopen_map()

    SelectByAttribute(record_fronts_layer,where_clause=f""" CreatedByRecord = '{Process_GUID}' """,selection_type="NEW_SELECTION")
    appended_features_count = int(GetCount(record_fronts_layer).getOutput(0))
    SelectByAttribute(record_fronts_layer, "CLEAR_SELECTION")

    inserted_fronts = SelectByAttribute(record_fronts_layer,where_clause=f""" CreatedByRecord = '{Process_GUID}' """,selection_type='NEW_SELECTION')

    calculated_features_count = int(GetCount(inserted_fronts)[0])

    CalculateField(in_table=inserted_fronts,field="CreatedByRecord",expression=f"'{RecordGUID}'",
        expression_type="SQL",code_block="",field_type="TEXT",enforce_domains="NO_ENFORCE_DOMAINS")

    return appended_features_count, calculated_features_count


def insert_new_border_points(ProcessName:str,query:str) -> int:

    RecordGUID = get_RecordGUID_NewCadaster(ProcessName)
    Process_GUID = get_ProcessGUID(ProcessName)

    process_points_layer = get_layer('נקודות בתהליך')
    record_points_layer = get_layer('נקודות גבול')

    # Define the fields to copy and their mapping
    source_fields = [
        "PointName", "Class", "IsControlBorder", "DataSource", "MarkCode", "SHAPE@"
    ]
    target_fields = [
        "Name", "Class", "IsControlBorder","DataSource", "MarkCode", "SHAPE@", "CreatedByRecord"
    ]

    # Select features to copy based on the query
    rows_to_insert = []
    with SearchCursor(process_points_layer, source_fields, where_clause=query) as search_cursor:
        for row in search_cursor:
            rows_to_insert.append(row)

    # Insert into target layer
    editor = start_editing(CNFG.ParcelFabricDatabase)
    inserted_count = 0
    try:
        with InsertCursor(record_points_layer, target_fields) as insert_cursor:
            for row in rows_to_insert:
                point_row = row + (RecordGUID,)
                insert_cursor.insertRow(point_row)
                inserted_count += 1
    finally:
        stop_editing(editor)

    RefreshLayer(record_points_layer)
    reopen_map()

    return inserted_count


def append_new_border_points(ProcessName:str, query:str) -> int:

    RecordGUID = get_RecordGUID_NewCadaster(ProcessName)
    Process_GUID = get_ProcessGUID(ProcessName)

    process_points_layer = get_layer('נקודות בתהליך')  
    record_points_layer = get_layer('נקודות גבול')


    exported_process_points = ExportFeatures(in_features=process_points_layer,out_features=r"memory\exported_process_points",
        where_clause=query,field_mapping="")
    
    CalculateField(in_table=exported_process_points,field="CreatedByRecord",expression=f"'{RecordGUID}'",
        expression_type="PYTHON3",code_block="",field_type="TEXT",enforce_domains="NO_ENFORCE_DOMAINS")
    

    field_mapping=fr'Name "שם נקודה" true true true 255 Text 0 0,First,#,{process_points_layer.name},PointName,0,19;' + \
        fr'Class "סיווג" true true false 0 Short 0 0,First,#,{process_points_layer.name},Class,-1,-1;' + \
        fr'IsControlBorder "נקודת גבול ובקרה" true false false 0 Short 0 0,First,#,{process_points_layer.name},IsControlBorder,-1,-1;' + \
        fr'CreatedByRecord "מזהה תהליך יוצר" true true true 38 Guid 0 0,First,#,{process_points_layer.name},CreatedByRecord,0,511;' + \
        fr'DataSource "מקור הנקודה" true false false 0 Short 0 0,First,#,{process_points_layer.name},DataSource,-1,-1;' + \
        fr'MarkCode "סימון" true false false 0 Short 0 0,First,#,{process_points_layer.name},MarkCode,-1,-1' 



    Append(inputs=process_points_layer,target=record_points_layer,expression = "",field_mapping = field_mapping,
        schema_type="NO_TEST",subtype="",match_fields=None,update_geometry="NOT_UPDATE_GEOMETRY")


    num_of_features = int(GetCount(exported_process_points).getOutput(0))

    Delete(exported_process_points)
    RefreshLayer(record_points_layer)
    reopen_map()

    return num_of_features
    


def append_new_border_points_old(ProcessName:str,query:str) -> tuple[int, int]:

    RecordGUID = get_RecordGUID_NewCadaster(ProcessName)
    Process_GUID = get_ProcessGUID(ProcessName)

    process_points_layer = get_layer('נקודות בתהליך')  
    record_points_layer = get_layer('נקודות גבול')



    field_mapping=fr'Name "שם נקודה" true true true 255 Text 0 0,First,#,{process_points_layer.name},PointName,0,19;' + \
        fr'Class "סיווג" true true false 0 Short 0 0,First,#,{process_points_layer.name},Class,-1,-1;' + \
        fr'IsControlBorder "נקודת גבול ובקרה" true false false 0 Short 0 0,First,#,{process_points_layer.name},IsControlBorder,-1,-1;' + \
        fr'CreatedByRecord "מזהה תהליך יוצר" true true true 38 Guid 0 0,First,#,{process_points_layer.name},CPBUniqueID,-1,-1;' + \
        fr'DataSource "מקור הנקודה" true false false 0 Short 0 0,First,#,{process_points_layer.name},DataSource,-1,-1;' + \
        fr'MarkCode "סימון" true false false 0 Short 0 0,First,#,{process_points_layer.name},MarkCode,-1,-1' 



    Append(inputs=process_points_layer,target=record_points_layer,expression = query,field_mapping = field_mapping,
        schema_type="NO_TEST",subtype="",match_fields=None,update_geometry="NOT_UPDATE_GEOMETRY")
    reopen_map()

    SelectByAttribute(record_points_layer,where_clause=f""" CreatedByRecord = '{Process_GUID}' """,selection_type="NEW_SELECTION")
    appended_features_count = int(GetCount(record_points_layer).getOutput(0))
    SelectByAttribute(record_points_layer, "CLEAR_SELECTION")

    inserted_points = SelectByAttribute(record_points_layer,where_clause=f""" CreatedByRecord = '{Process_GUID}' """,selection_type='NEW_SELECTION')

    calculated_features_count = int(GetCount(inserted_points)[0])
    
    CalculateField(in_table=inserted_points,field="CreatedByRecord",expression=f"'{RecordGUID}'",
        expression_type="SQL",code_block="",field_type="TEXT",enforce_domains="NO_ENFORCE_DOMAINS")
    

    return appended_features_count, calculated_features_count
