import pandas as pd
import os
from Utils.Configs import CNFG
from Utils.Helpers import delete_file, get_ProcessType, get_ProcessGUID, get_RecordGUID, remove_intermediate_vertices, start_editing, stop_editing, get_BlockGUID,get_layer, reopen_map, get_ActiveRecord
from Utils.NewCadasterHelpers import insert_new_fronts, insert_new_border_points, get_ProcessName, get_RecordGUID_NewCadaster
from Utils.ValidationsNewCadaster import layer_exists
from arcpy import AddMessage, AddError, AddWarning, GetParameterAsText, PointGeometry, env, CopyFeatures_management as CopyFeatures, Delete_management as Delete, Describe
from arcpy.mp import ArcGISProject
from arcpy.da import SearchCursor, UpdateCursor
from arcpy.management import SelectLayerByLocation as SelectByLocation, SelectLayerByAttribute as SelectByAttribute,GetCount, SplitLineAtPoint, Append, CreateFeatureclass, DeleteIdentical, PointsToLine
from arcpy.parcel import BuildParcelFabric
from arcpy.edit import Snap
from arcpy.parcel import MergeCollinearParcelBoundaries
from Utils.TypeHints import *

env.overwriteOutput = True
#Change workspace if gdb
#env.workspace = CNFG.ParcelFabricDatabase if CNFG.ParcelFabricDatabase.endswith('.gdb/') else env.workspace 




def build_record(ProcessName: str) -> None:
    """ Build a fabric for the record """

    AddMessage(f'\n ⭕ Building record {ProcessName} \n')
    #records_layer = get_layer('גבולות רישומים')
    #records_layer = ArcGISProject("CURRENT").listMaps()[0].listLayers('רישומים')[0]
    records_layer = ArcGISProject("CURRENT").activeMap.listLayers('רישומים')[0]
    try:
        BuildParcelFabric(records_layer, extent="DEFAULT", record_name = ProcessName)
        AddMessage(f"    ✔ Record {ProcessName} Built successfully \n ")
    except:
        AddMessage(f"    ⚠️ Record {ProcessName} couldn't be built \n ")

def points_match(line1, line2):
    return (line1.firstPoint.equals(line2.firstPoint) and line1.lastPoint.equals(line2.lastPoint)) or \
           (line1.firstPoint.equals(line2.lastPoint) and line1.lastPoint.equals(line2.firstPoint))

def print_list(list_string):
    
    # Split the string based on commas
    items = list_string.split(',')
    
    # Remove single quotes and print each item on a new line
    for item in items:
        item = item.strip().strip("'")  # Remove surrounding whitespace and single quotes
        AddMessage(f"            {item}")  
    
def merge_collinear_fronts(TaskType:str = 'CreateNewCadaster' or 'ImproveNewCadaster'):
    """
        Merges collinear fronts
    """
    
    record_fronts_layer = get_layer('חזיתות')
    process_borders_layer = get_layer('גבול תכנית')
    SelectByLocation(in_layer=record_fronts_layer,overlap_type="SHARE_A_LINE_SEGMENT_WITH",select_features=process_borders_layer)
    num_before = int(GetCount(record_fronts_layer).getOutput(0))
    AddMessage('\n ⭕ Looking for duplicate fronts overlapping with the process border: \n')
    MergeCollinearParcelBoundaries(in_parcel_boundaries=record_fronts_layer, offset_tolerance="0.01 Meters")
    SelectByLocation(in_layer=record_fronts_layer,overlap_type="SHARE_A_LINE_SEGMENT_WITH",select_features=process_borders_layer)
    num_after = int(GetCount(record_fronts_layer).getOutput(0))
    SelectByAttribute(record_fronts_layer, "CLEAR_SELECTION")

    if num_before != num_after:
        AddMessage(f'    ✔ {num_before - num_after} duplicate fronts were removed \n')
    else:
        AddMessage(f'    ✔ No duplicate fronts were found \n')

'''
def append_unmatched_fronts(ProcessName,fronts_list):
    """
        Appending unmatched fronts to the record fronts
    """
    process_fronts_layer = get_layer('חזיתות בתהליך')
    record_fronts_layer = get_layer('חזיתות')

    Process_GUID = get_ProcessGUID(ProcessName)
    RecordGUID = get_RecordGUID(ProcessName,'MAP')

    field_mapping = fr'GlobalID "GlobalID" false false true 38 GlobalID 0 0,First,#,{process_fronts_layer.name},GlobalID,-1,-1;' + \
        fr'CreatedByRecord "Created By Record" true true true 38 Guid 0 0,First,#,{process_fronts_layer.name},CPBUniqueID,-1,-1;' + \
        fr'RetiredByRecord "Retired By Record" true true true 38 Guid 0 0,First,#;' + \
        fr'Direction "Direction" true true true 8 Double 0 0,First,#;' + \
        fr'Distance "Distance" true true true 8 Double 0 0,First,#,{process_fronts_layer.name},LegalLength,-1,-1;' + \
        fr'Radius "Radius" true true true 8 Double 0 0,First,#,{process_fronts_layer.name},Radius,-1,-1;' + \
        fr'ArcLength "Arc Length" true true true 8 Double 0 0,First,#;' + \
        fr'Radius2 "Radius2" true true true 8 Double 0 0,First,#;' + \
        fr'COGOType "COGO Type" true true true 4 Long 0 0,First,#;' + \
        fr'IsCOGOGround "Is COGO Ground" true true true 4 Long 0 0,First,#;' + \
        fr'Rotation "Rotation" true true true 8 Double 0 0,First,#;' + \
        fr'Scale "Scale" true true true 8 Double 0 0,First,#;' + \
        fr'ParentLineID "מזהה חזית קודמת" true true true 38 Guid 0 0,First,#;' + \
        fr'DirectionAccuracy "דיוק כיוון" true true true 8 Double 0 0,First,#;' + \
        fr'DistanceAccuracy "דיוק אורך" true true true 8 Double 0 0,First,#;' + \
        fr'LabelPosition "מיקום תווית" true true true 4 Long 0 0,First,#;' + \
        fr'LineType "סוג הקו" true true false 2 Short 0 0,First,#,{process_fronts_layer.name},LineType,-1,-1;' + \
        fr'StartPointUniqueID "מזהה נקודת התחלה" true true false 38 Guid 0 0,First,#,{process_fronts_layer.name},StartPointUniqueID,-1,-1;' + \
        fr'EndPointUniqueID "מזהה נקודת סיום" true true false 38 Guid 0 0,First,#,{process_fronts_layer.name},EndPointUniqueID,-1,-1'
    

    Append(inputs=process_fronts_layer,target=record_fronts_layer,expression=fr'GlobalID IN ({fronts_list})',field_mapping = field_mapping,
        schema_type="NO_TEST",subtype="",match_fields=None,update_geometry="NOT_UPDATE_GEOMETRY")

    reopen_map()



    editor = start_editing(CNFG.ParcelFabricDatabase)
    count = 0
    SelectByAttribute(record_fronts_layer, "CLEAR_SELECTION")
    #SelectByAttribute(record_fronts_layer,where_clause=f""" CreatedByRecord = '{Process_GUID}' """,selection_type="NEW SELECTION")
    with UpdateCursor(record_fronts_layer, ["GlobalID", "CreatedByRecord"], f""" CreatedByRecord = '{Process_GUID}' """) as cursor:
        for row in cursor:
            row[1] = RecordGUID
            count = count + 1
            cursor.updateRow(row)
    stop_editing(editor)
    reopen_map()


    AddMessage(fr'    ⚡ loaded {count} new fronts')

def append_unmatched_points(ProcessName,points_list):
    """
        Appending unmatched points to the record points
    """

    process_points_layer = get_layer('נקודות בתהליך')
    record_points_layer = get_layer('נקודות גבול')

    Process_GUID = get_ProcessGUID(ProcessName)
    RecordGUID = get_RecordGUID(ProcessName,'MAP')


    field_mapping=fr'UpdatedByRecord "מזהה תהליך מעדכן" true true false 38 Guid 0 0,First,#;' + \
        fr'CreatedByRecord "Created By Record" true true true 38 Guid 0 0,First,#,{process_points_layer.name},CPBUniqueID,-1,-1;' + \
        fr'RetiredByRecord "Retired By Record" true true true 38 Guid 0 0,First,#;' + \
        fr'Name "Name" true true true 255 Text 0 0,First,#,{process_points_layer.name},PointName,0,19;' + \
        fr'IsFixed "Fixed Shape" true true true 0 Long 0 0,First,#;' + \
        fr'AdjustmentConstraint "Adjustment Constraint" true true true 0 Long 0 0,First,#;' + \
        fr'Preserve "Preserve" true true true 0 Long 0 0,First,#;' + \
        fr'X "X" true true true 0 Double 0 0,First,#;' + \
        fr'Y "Y" true true true 0 Double 0 0,First,#;' + \
        fr'Z "Z" true true true 0 Double 0 0,First,#;' + \
        fr'XYAccuracy "XY Accuracy" true true true 0 Double 0 0,First,#;' + \
        fr'ZAccuracy "Z Accuracy" true true true 0 Double 0 0,First,#;' + \
        fr'XYUncertainty "XY Uncertainty" true true true 0 Double 0 0,First,#;' + \
        fr'EllipseMajor "Error Ellipse Semi Major" true true true 0 Double 0 0,First,#;' + \
        fr'EllipseMinor "Error Ellipse Semi Minor" true true true 0 Double 0 0,First,#;' + \
        fr'EllipseDirection "Error Ellipse Direction" true true true 0 Double 0 0,First,#;' + \
        fr'GlobalID "GlobalID" false false true 38 GlobalID 0 0,First,#,{process_points_layer.name},GlobalID,-1,-1;' + \
        fr'Class "סיווג" true true false 0 Short 0 0,First,#,{process_points_layer.name},Class,-1,-1;' + \
        fr'DataSource "מקור הנקודה" true false false 0 Short 0 0,First,#,{process_points_layer.name},DataSource,-1,-1;' + \
        fr'MarkCode "סימון" true false false 0 Short 0 0,First,#,{process_points_layer.name},MarkCode,-1,-1;' + \
        fr'IsControlBorder "נקודת גבול ובקרה" true false false 0 Short 0 0,First,#,{process_points_layer.name},IsControlBorder,-1,-1'


    Append(inputs=process_points_layer,target=record_points_layer,expression=fr'GlobalID IN ({points_list})',field_mapping = field_mapping,
        schema_type="NO_TEST",subtype="",match_fields=None,update_geometry="NOT_UPDATE_GEOMETRY")
    reopen_map()

    editor = start_editing(CNFG.ParcelFabricDatabase)
    count = 0

    SelectByAttribute(record_points_layer, "CLEAR_SELECTION")
    #SelectByAttribute(record_points_layer,where_clause=f""" CreatedByRecord = '{Process_GUID}' """,selection_type="NEW SELECTION")
    with UpdateCursor(record_points_layer, ["GlobalID", "CreatedByRecord"], f""" CreatedByRecord = '{Process_GUID}' """) as cursor:
        for row in cursor:
            row[1] = RecordGUID
            count = count + 1
            cursor.updateRow(row)
    stop_editing(editor)
    reopen_map()

    AddMessage(fr'    ⚡ loaded {count} new points')
'''


def are_identical(record_fronts):
    """
        Checks if the selected record fronts have the same geometry among themselves
    """
    geometries = []
    with SearchCursor(record_fronts, ["SHAPE@"]) as row:
        for temp_row in row:
            geometries.append(temp_row[0])

    num_of_lines = len(geometries)
    for i in range(num_of_lines-1):
        if not geometries[i].equals(geometries[i+1]):
            return False
    return True
    
def is_passing_through_border_points(process_front, record_points):
    """
        Checks if the selected process front is passing through border points
    """
    contained_points = SelectByLocation(in_layer=record_points,overlap_type="COMPLETELY_WITHIN",select_features=process_front,selection_type="NEW_SELECTION")
    num_of_contained_points = int(GetCount(contained_points).getOutput(0))

    if num_of_contained_points > 0:
        return True
    return False


def break_fronts_at_border_points(ProcessName:str, TaskType:str = 'CreateNewCadaster' or 'ImproveNewCadaster') -> None:
    """
        Breaking existing fronts which are crossing via border points matching the process points
    """
    process_points_layer = get_layer('נקודות ביסוס')
    record_points_layer = get_layer('נקודות גבול')
    record_fronts_layer = get_layer('חזיתות')
    process_fronts_layer = get_layer('חזיתות ביסוס')



    if TaskType == 'ImproveNewCadaster':
        blocks_layer = get_layer('גושים')
        settled_blocks = SelectByAttribute(blocks_layer,where_clause=" LandType = 1 ",selection_type="NEW SELECTION")
        process_points_layer = SelectByLocation(process_points_layer,"BOUNDARY_TOUCHES",settled_blocks,None,"NEW SELECTION","NOT_INVERT")
        process_fronts_layer = SelectByLocation(process_fronts_layer,"SHARE_A_LINE_SEGMENT_WITH",settled_blocks,None,"NEW SELECTION","NOT_INVERT")
        SelectByAttribute(blocks_layer, "CLEAR_SELECTION")
        del [blocks_layer,settled_blocks]
    
    matching_record_points = SelectByLocation(record_points_layer,"ARE_IDENTICAL_TO",process_points_layer,None,"NEW_SELECTION","NOT_INVERT")
    fronts_for_retirment = SelectByLocation(in_layer=record_fronts_layer,overlap_type="COMPLETELY_CONTAINS",select_features=matching_record_points,selection_type="NEW_SELECTION")       
    num_of_fronts_for_retirment = int(GetCount(fronts_for_retirment).getOutput(0))
    
    if num_of_fronts_for_retirment > 0:
        if TaskType == 'CreateNewCadaster':
            AddMessage('\n ⭕ Breaking external fronts that pass through border points: \n')
        else: #if TaskType == 'ImproveNewCadaster':
            AddMessage('\n ⭕ Breaking external fronts that pass through border points (only for points that are along the settled borders): \n')

        AddMessage(f"    {num_of_fronts_for_retirment} Fronts will be retired and replaced with shorter collinear fronts:")
        RecordGUID = get_RecordGUID_NewCadaster(ProcessName)
        editor = start_editing(CNFG.ParcelFabricDatabase)
        sr = Describe(record_fronts_layer).spatialReference
        new_fronts = CreateFeatureclass("memory","new_fronts",template=record_fronts_layer,spatial_reference=sr)
        counter = 1
        with UpdateCursor(fronts_for_retirment, ["SHAPE@","GlobalID", "RetiredByRecord"]) as old_fronts_cursor:
            for row in old_fronts_cursor:
                #splitted_line = SplitLineAtPoint(in_features=row[0],point_features=matching_record_points,out_feature_class=r"memory\splited_line")
                splitted_line = SplitLineAtPoint(in_features=row[0],point_features=matching_record_points,out_feature_class=r"memory\splited_line",search_radius="0.1 Meters")
                #num_of_parts = int(GetCount(splitted_line).getOutput(0))
                Append(inputs = splitted_line, target = new_fronts,schema_type="NO_TEST")


                row[2] = RecordGUID
                old_fronts_cursor.updateRow(row)
                AddMessage(f"    ({counter}/{num_of_fronts_for_retirment}) Front {row[1]} was retired and will be replaced by shorter fronts")
                counter += 1


        with UpdateCursor(new_fronts, ["GlobalID","CreatedByRecord","LineType"]) as new_fronts_cursor:
            for row in new_fronts_cursor:
                row[1] = RecordGUID
                row[2] = 1
                new_fronts_cursor.updateRow(row)

        Snap(in_features=new_fronts,snap_environment=fr"'{process_fronts_layer}' END '0.1 Meters'")

        SelectByAttribute(record_fronts_layer, "CLEAR_SELECTION")
        DeleteIdentical(in_dataset=new_fronts,fields="Shape",xy_tolerance=None,z_tolerance=0)
        Append(inputs = new_fronts, target = record_fronts_layer,schema_type="NO_TEST")
        num_of_new_fronts = int(GetCount(new_fronts).getOutput(0))
        AddMessage(f"    {num_of_new_fronts} new fronts were added")
        reopen_map()
        stop_editing(editor)
        reopen_map()
        #CopyFeatures(new_fronts,os.path.join(env.workspace, "output"))
        Delete("memory\new_fronts")
        Delete("memory\splited_line")

    SelectByAttribute(record_points_layer, "CLEAR_SELECTION")
    SelectByAttribute(record_fronts_layer, "CLEAR_SELECTION")
    SelectByAttribute(process_points_layer, "CLEAR_SELECTION")
    SelectByAttribute(process_fronts_layer, "CLEAR_SELECTION")
    del [process_points_layer,record_points_layer,record_fronts_layer,process_fronts_layer]


def modify_external_fronts_attributes(ProcessName:str, TaskType:str = 'CreateNewCadaster' or 'ImproveNewCadaster') -> None:

    """
        Modifying the attributes of the external fronts 
    """
    
    process_fronts_layer = get_layer('חזיתות ביסוס')
    record_fronts_layer = get_layer('חזיתות')
    process_points_layer = get_layer('נקודות ביסוס')
    record_points_layer = get_layer('נקודות גבול')
    process_borders_layer = get_layer('גבול תכנית')



    if TaskType == 'ImproveNewCadaster':
        blocks_layer = get_layer('גושים')
        settled_blocks = SelectByAttribute(blocks_layer,where_clause=" LandType = 1 ",selection_type="NEW SELECTION")
        process_points_layer = SelectByLocation(process_points_layer,"BOUNDARY_TOUCHES",settled_blocks,None,"NEW SELECTION","NOT_INVERT")
        process_fronts_layer = SelectByLocation(process_fronts_layer,"SHARE_A_LINE_SEGMENT_WITH",settled_blocks,None,"NEW SELECTION","NOT_INVERT")
        #PointsToLine(Input_Features=process_points_layer,Output_Feature_Class="memory\points_to_polyline")
        SelectByAttribute(blocks_layer, "CLEAR_SELECTION")
        del [blocks_layer,settled_blocks]

    num_of_process_fronts = int(GetCount(process_fronts_layer).getOutput(0))

    env.preserveGlobalIds = True
    matching_record_points = SelectByLocation(record_points_layer,"ARE_IDENTICAL_TO",process_points_layer,None,"NEW_SELECTION","NOT_INVERT")
    matching_record_points = CopyFeatures(matching_record_points,"memory\matching_record_points")
    env.preserveGlobalIds = False
    SelectByAttribute(record_points_layer, "CLEAR_SELECTION")
    missing_process_points = SelectByLocation(record_points_layer,"INTERSECT",process_borders_layer,None,"NEW_SELECTION","NOT_INVERT")
    missing_process_points = SelectByLocation(missing_process_points,"ARE_IDENTICAL_TO",process_points_layer,None,"REMOVE_FROM_SELECTION","NOT_INVERT")



    # Fields to copy
    process_fields = ["LegalLength", "Radius"]
    record_fields = ["Distance", "Radius"]

    RecordGuid = get_RecordGUID_NewCadaster(ProcessName)

    if TaskType == 'CreateNewCadaster':
        AddMessage('\n ⭕ Modifying base fronts attributes: \n')
    else: #if TaskType == 'ImproveNewCadaster':
        AddMessage('\n ⭕ Modifying base fronts attributes (only for fronts that are along the settled borders): \n')
    
    editor = start_editing(CNFG.ParcelFabricDatabase)

    counter = 1

    collinear_passing_through_record_points = []
    other_collinear = []
    matching_with_duplicates = []
    no_matching_fronts = []

    # Iterate through each line in the process_fronts_layer
    with SearchCursor(process_fronts_layer, ["SHAPE@"] + process_fields + ["GlobalID"]) as process_cursor:
        for process_row in process_cursor:
            process_line_geometry = process_row[0]
            start_point = process_line_geometry.firstPoint
            end_point = process_line_geometry.lastPoint

            SelectByLocation(record_fronts_layer, "SHARE_A_LINE_SEGMENT_WITH", process_line_geometry)
            num_of_record_fronts = int(GetCount(record_fronts_layer).getOutput(0))
            if num_of_record_fronts==1:
                with UpdateCursor(record_fronts_layer, ["SHAPE@", "StartPointUniqueID", "EndPointUniqueID"] + record_fields + ["UpdatedByRecord","GlobalID"]) as record_cursor:
                    for record_row in record_cursor:
                        record_line_geometry = record_row[0]

                        # Check for full match
                        if record_line_geometry.equals(process_line_geometry):
                            # Copy attributes from process_fronts to record_fronts
                            for i, field in enumerate(record_fields):
                                record_row[i + 3] = process_row[i + 1]

                            # Set the UpdatedByRecord field with the constant RecordID value
                            record_row[5] = RecordGuid

                            # Find the StartPointID and EndPointID based on the points in record_points_layer
                            tempPoint = SelectByLocation(matching_record_points, "ARE_IDENTICAL_TO", PointGeometry(start_point))
                            start_point_id = None
                            with SearchCursor(tempPoint, ["GlobalID"]) as points_cursor:
                                for point_row in points_cursor:
                                    start_point_id = point_row[0]
                                    break

                            tempPoint = SelectByLocation(matching_record_points, "ARE_IDENTICAL_TO", PointGeometry(end_point))
                            end_point_id = None
                            with SearchCursor(tempPoint, ["GlobalID"]) as points_cursor:
                                for point_row in points_cursor:
                                    end_point_id = point_row[0]
                                    break

                            # Update the StartPointID and EndPointID fields
                            record_row[1] = start_point_id
                            record_row[2] = end_point_id
                            AddMessage(f"    ({counter}/{num_of_process_fronts}) Updated attributes for front {record_row[6]}: \n            StartPointUniqueID: {record_row[1]} EndPointUniqueID: {record_row[2]} \n            UpdatedByRecord: {RecordGuid} Distance: {record_row[3]} Radius: {record_row[4]}")
                            counter += 1
                            # Update the row in the record_fronts_layer
                            record_cursor.updateRow(record_row)
                            break

                        else:
                            other_collinear.append(process_row[3])    
                            
            elif num_of_record_fronts > 1:
                if is_passing_through_border_points(process_line_geometry,missing_process_points):
                    collinear_passing_through_record_points.append(process_row[3])
                elif are_identical(record_fronts_layer):
                    matching_with_duplicates.append(process_row[3])
                else:
                    other_collinear.append(process_row[3])
            else:
                no_matching_fronts.append(process_row[3])
            SelectByAttribute(matching_record_points, "CLEAR_SELECTION")

    stop_editing(editor)
 


    if no_matching_fronts:
        num_of_fronts = len(no_matching_fronts)
        fronts_list = ','.join(f"'{gid}'" for gid in no_matching_fronts)
        #AddMessage(f"    ⚠️ For {num_of_fronts} process fronts no matching results were found, these fronts will be appended:\n {fronts_list}")
        AddMessage(f"    ⚠️ For {num_of_fronts} process fronts no matching results were found, these fronts will be appended:\n ")
        print_list(fronts_list)
        #append_unmatched_fronts(ProcessName,fronts_list)
        query = fr'GlobalID IN ({fronts_list})'
        num_of_appended_features = insert_new_fronts(ProcessName,query)
        if not num_of_appended_features:
            AddWarning(fr'    ⚠️ Failed to load {num_of_fronts} new fronts')
        else:
            AddMessage(fr'    ⚡ loaded {num_of_appended_features} new fronts')




    if collinear_passing_through_record_points:
        num_of_fronts = len(collinear_passing_through_record_points)
        fronts_list = ','.join(f"'{gid}'" for gid in collinear_passing_through_record_points)
        #AddMessage(f"    ⚠️ {num_of_fronts} process fronts are passing through border points that are not appearing in the process:\n     {fronts_list}\n     no changes will be made")
        AddMessage(f"    ⚠️ {num_of_fronts} process fronts are passing through border points that are not appearing in the process:\n        no changes will be made")
        print_list(fronts_list)

    if matching_with_duplicates:
        num_of_fronts = len(matching_with_duplicates)
        fronts_list = ','.join(f"'{gid}'" for gid in matching_with_duplicates)
        #AddMessage(f"    ⚠️ For {num_of_fronts} process fronts duplicated matching fronts were found:\n     {fronts_list}\n     no changes will be made")
        AddMessage(f"    ⚠️ For {num_of_fronts} process fronts duplicated matching fronts were found:\n        no changes will be made")
        print_list(fronts_list)

    if other_collinear:
        num_of_fronts = len(other_collinear)
        fronts_list = ','.join(f"'{gid}'" for gid in other_collinear)
        #AddMessage(f"    ⚠️ For {num_of_fronts} process fronts partial matches were found:\n     {fronts_list}\n     no changes will be made")
        AddMessage(f"    ⚠️ For {num_of_fronts} process fronts partial matches were found:\n       no changes will be made")
        print_list(fronts_list)

    SelectByAttribute(record_points_layer, "CLEAR_SELECTION")
    SelectByAttribute(process_fronts_layer, "CLEAR_SELECTION")
    SelectByAttribute(process_points_layer, "CLEAR_SELECTION")
    SelectByAttribute(record_fronts_layer, "CLEAR_SELECTION")
    del [process_fronts_layer,record_fronts_layer,matching_record_points]
    del [process_points_layer,record_points_layer,process_borders_layer,missing_process_points]
    Delete("memory\matching_record_points")
    AddMessage(f"    ✔ The fronts modifying process is complete.")



def modify_external_points_attributes(ProcessName:str, TaskType:str = 'CreateNewCadaster' or 'ImproveNewCadaster') -> None:
    
    """
        Modifying the attributes of the border points 
    """
    process_points_layer = get_layer('נקודות ביסוס')
    record_points_layer = get_layer('נקודות גבול')


    if TaskType == 'ImproveNewCadaster':
        blocks_layer = get_layer('גושים')
        settled_blocks = SelectByAttribute(blocks_layer,where_clause=" LandType = 1 ",selection_type="NEW SELECTION")
        process_points_layer = SelectByLocation(process_points_layer,"BOUNDARY_TOUCHES",settled_blocks,None,"NEW SELECTION","NOT_INVERT")
        SelectByAttribute(blocks_layer, "CLEAR_SELECTION")
        del [blocks_layer,settled_blocks]

    num_of_process_points = int(GetCount(process_points_layer).getOutput(0))

    env.preserveGlobalIds = True
    matching_record_points = SelectByLocation(record_points_layer,"ARE_IDENTICAL_TO",process_points_layer,None,"NEW_SELECTION","NOT_INVERT")
    matching_record_points = CopyFeatures(matching_record_points,"memory\matching_record_points")
    SelectByAttribute(record_points_layer, "CLEAR_SELECTION")
    env.preserveGlobalIds = False
    no_match_points = []
    more_than_one_match_points = []
    counter = 1

    if TaskType == 'CreateNewCadaster':
        AddMessage('\n ⭕ Modifying base points attributes: \n')
    else: #if TaskType == 'ImproveNewCadaster':
        AddMessage('\n ⭕ Modifying base points attributes (only for points that are along the settled borders): \n')

    editor = start_editing(CNFG.ParcelFabricDatabase)
    # Iterate through each point in the process_points layer
    with SearchCursor(process_points_layer, ["SHAPE@", "PointName", "Class","GlobalID"]) as process_cursor:
        for process_row in process_cursor:
            process_point_geometry = process_row[0]
            point_name = process_row[1]
            point_class = process_row[2]

            # Select the matching point in the record_points layer by location
            currentRecordPoint = SelectByLocation(matching_record_points, "ARE_IDENTICAL_TO", process_point_geometry)
            count = int(GetCount(currentRecordPoint).getOutput(0))
            #count = get_number_of_selections(currentRecordPoint)
            if count == 0:
                no_match_points.append(process_row[3])
                # AddWarning(f"    No matching point found for process point {process_row[3]} ")
            elif count > 1:
                more_than_one_match_points.append(process_row[3])
                #AddWarning(f"    found {count} matching points for process point {process_row[3]}. No updates were made ")
            else:
                # Update the matching point in the record_points layer
                with UpdateCursor(currentRecordPoint, ["Name", "Class","GlobalID"]) as record_cursor:
                    for record_row in record_cursor:
                        record_row[0] = point_name  # Copy point_name
                        record_row[1] = point_class  # Copy class
                        AddMessage(f"    ({counter}/{num_of_process_points}) Updated border point {record_row[2]} with point name {point_name} and class {point_class}")
                        counter += 1
                        record_cursor.updateRow(record_row)
            
            SelectByAttribute(currentRecordPoint, "CLEAR_SELECTION")


    if no_match_points:
        num_of_points = len(no_match_points)
        points_list = ','.join(f"'{gid}'" for gid in no_match_points)
        #AddMessage(f"    ⚠️ {num_of_points} process points were not found in the record points layer, these points will be appended:\n      {points_list}")
        AddMessage(f"    ⚠️ {num_of_points} process points were not found in the record points layer, these points will be appended:\n")
        print_list(points_list)
        #append_unmatched_points(ProcessName,points_list)
        query = fr'GlobalID IN ({points_list})'

        num_of_appended_features = insert_new_border_points(ProcessName,query)
        if not num_of_appended_features:
            AddWarning(fr'    ⚠️ Failed to load {num_of_points} new border points')
        else:
            AddMessage(fr'    ⚡ loaded {num_of_appended_features} new border points')



    if more_than_one_match_points:
        num_of_points = len(more_than_one_match_points)
        points_list = ','.join(f"'{gid}'" for gid in more_than_one_match_points)
        #AddMessage(f"    ⚠️ {num_of_points} process points have more than one matching point in the record points layer:\n     {points_list}\n     no changes will be made")
        AddMessage(f"    ⚠️ {num_of_points} process points have more than one matching point in the record points layer:\n       no changes will be made")
        print_list(points_list)

    #del [process_points_layer,record_points_layer,matching_record_points]
    SelectByAttribute(process_points_layer, "CLEAR_SELECTION")
    del [process_points_layer,record_points_layer]
    Delete("memory\matching_record_points")
    stop_editing(editor)
    AddMessage(f"    ✔ The points modifying process is complete.")
    


def modify_new_fronts_attributes(ProcessName:str, Filter:str = 'INTERNAL' or 'EXTERNAL') -> None:
    """
        Modifying the attributes of the new fronts created by the process
    """

    # if there is no internal new fronts in the process, exit the function
    if Filter == 'INTERNAL' and not layer_exists('חזיתות חדשות'):
        return
    
    RecordGuid = get_RecordGUID_NewCadaster(ProcessName)


    all_fronts_layer = get_layer('חזיתות')
    all_points_layer = get_layer('נקודות גבול')
    process_borders_layer = get_layer('גבול תכנית')

    fronts_layer = SelectByAttribute(all_fronts_layer,where_clause=f""" CreatedByRecord = '{RecordGuid}' """,selection_type="NEW SELECTION")

    if Filter == 'EXTERNAL':
        fronts_layer = SelectByLocation(fronts_layer, "SHARE_A_LINE_SEGMENT_WITH", process_borders_layer, None, "SUBSET_SELECTION", "NOT_INVERT")
    elif Filter == 'INTERNAL':
        fronts_layer = SelectByLocation(fronts_layer, "SHARE_A_LINE_SEGMENT_WITH", process_borders_layer, None, "REMOVE_FROM_SELECTION", "NOT_INVERT")




    points_layer = SelectByAttribute(all_points_layer,where_clause=f""" CreatedByRecord = '{RecordGuid}' """,selection_type="NEW SELECTION")
    points_layer = SelectByLocation(all_points_layer, "INTERSECT", process_borders_layer, None, "ADD_TO_SELECTION", "NOT_INVERT")
    points_layer = SelectByLocation(all_points_layer, "INTERSECT", fronts_layer, None, "SUBSET_SELECTION", "NOT_INVERT")


    num_of_new_fronts = int(GetCount(fronts_layer).getOutput(0))
    env.preserveGlobalIds = True
    matching_points = CopyFeatures(points_layer,"memory\matching_points")
    SelectByAttribute(points_layer, "CLEAR_SELECTION")
    env.preserveGlobalIds = False
    counter = 1

        
    if Filter == 'EXTERNAL':
        AddMessage('\n ⭕ Modifying external new fronts'' attributes: \n')
    elif Filter == 'INTERNAL':
        AddMessage('\n ⭕ Modifying internal new fronts'' attributes: \n')



    editor = start_editing(CNFG.ParcelFabricDatabase)
    # Iterate through each line in the fronts feature class
    with UpdateCursor(fronts_layer, ["SHAPE@", "StartPointUniqueID", "EndPointUniqueID","GlobalID"]) as fronts_cursor:
        for front_row in fronts_cursor:
            line_geometry = front_row[0]
            start_point = line_geometry.firstPoint
            end_point = line_geometry.lastPoint
            
             # Find the exact matching point for the start point
            selected_points = SelectByLocation(matching_points, "ARE_IDENTICAL_TO", PointGeometry(start_point))
            start_point_id = None
            with SearchCursor(selected_points, ["GlobalID"]) as points_cursor:
                for point_row in points_cursor:
                    start_point_id = point_row[0]
                    break

            SelectByAttribute(selected_points, "CLEAR_SELECTION")

            # Find the exact matching point for the end point
            selected_points = SelectByLocation(matching_points, "ARE_IDENTICAL_TO", PointGeometry(end_point))
            end_point_id = None
            with SearchCursor(selected_points, ["GlobalID"]) as points_cursor:
                for point_row in points_cursor:
                    end_point_id = point_row[0]
                    break
                SelectByAttribute(selected_points, "CLEAR_SELECTION")
            # Update the fronts feature class if exact matches are found
            if start_point_id:
                front_row[1] = start_point_id
            if end_point_id:
                front_row[2] = end_point_id

            AddMessage(f"    ({counter}/{num_of_new_fronts}) Updated front {front_row[3]}:\n            StartPointUniqueID: {start_point_id} EndPointUniqueID: {end_point_id}")
            counter += 1
            # Update the row
            fronts_cursor.updateRow(front_row)
            
    stop_editing(editor)
    if Filter == 'EXTERNAL':
        AddMessage(f"    ✔ The new external fronts modifying process is complete.")
    elif Filter == 'INTERNAL':
        AddMessage(f"    ✔ The new internal fronts modifying process is complete.")
    
    del [fronts_layer, points_layer]
    Delete("memory\matching_points")

def update_attributes_new_cadaster(ProcessName:str, TaskType:str = 'CreateNewCadaster' or 'ImproveNewCadaster') -> None:
    #merge_collinear_fronts(TaskType)
    modify_external_points_attributes(ProcessName,TaskType)
    if TaskType == 'CreateNewCadaster':
        modify_new_fronts_attributes(ProcessName,'INTERNAL')
    break_fronts_at_border_points(ProcessName,TaskType)
    modify_external_fronts_attributes(ProcessName,TaskType)
    if TaskType == 'CreateNewCadaster':
        modify_new_fronts_attributes(ProcessName,'EXTERNAL')
        build_record(ProcessName)

if __name__ == "__main__":

    ProcessName: str|None = get_ActiveRecord()
    if not ProcessName:
        ProcessName: str|None = get_ProcessName()
    #ProcessName = GetParameterAsText(0)
    TaskType = GetParameterAsText(0)

    update_attributes_new_cadaster(ProcessName, TaskType)


    
