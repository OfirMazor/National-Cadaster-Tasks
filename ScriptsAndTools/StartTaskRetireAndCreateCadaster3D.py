from os import startfile
from arcpy import RefreshLayer, AddMessage, GetParameterAsText, env as ENV
from arcpy.mp import ArcGISProject
from arcpy.conversion import ExportFeatures
from arcpy.da import SearchCursor, UpdateCursor, InsertCursor
from arcpy.management import Append, MakeFeatureLayer as MakeLayer, CalculateField, AddField, AlterField
from Utils.Configs import CNFG
from Utils.TypeHints import *
from Utils.VersionManagement import open_version
from Utils.UpdateAttributes import retire_3D_parcels_and_substractions, retire_3D_points, update_record_status
from Utils.Validations import validation_set, features_exist, creating_record_is_duplicated
from Utils.Helpers import create_shelf, get_ProcessGUID, get_RecordGUID, get_ActiveParcel2DGUID, timestamp, \
    zoom_to_aoi, filter_to_aoi, get_FinalParcel, reopen_map, cursor_length, \
    set_priority, load_to_records, Type2CreateType, get_ProcessType, get_layer, get_aprx_name

ENV.preserveGlobalIds = False


def display_process_data(ProcessName: str) -> None:
    """
    Display process-related data layers in the current ArcGIS project map.

    Parameters:
        ProcessName (str): The name of the process for which data is displayed.
    """

    CurrentMap: Map = ArcGISProject("current").listMaps('סצנת עריכה')[0]
    ProcessGUID: str = get_ProcessGUID(ProcessName)
    query_name: str = f'Process {ProcessName}'

    CurrentMap.addDataFromPath(fr'{CNFG.LayerFiles}RetireAndCreateProcess3DGroup.lyrx')
    GroupLayer: Layer = CurrentMap.listLayers('תכנית')[0]
    GroupLayer.name = f'{ProcessName} תכנית'
    del GroupLayer

    Pointslayer: Layer = CurrentMap.listLayers('נקודות לשימור וחדשות')[0]
    Parcelslayer: Layer = CurrentMap.listLayers('חלקות חדשות')[0]
    Substractionslayer: Layer = CurrentMap.listLayers('גריעות לשימור וחדשות')[0]
    ProjectedParcelslayer: Layer = CurrentMap.listLayers('היטלי חלקות חדשות')[0]
    ProjectedSubstractionslayer: Layer = CurrentMap.listLayers('היטלי גריעות לשימור וחדשות')[0]
    Processlayer: Layer = CurrentMap.listLayers('גבול תכנית')[0]
    SequenceTable: Table = CurrentMap.listTables('פעולות בתכנית')[0]

    SequenceTable.updateDefinitionQueries([{'name': query_name, 'sql': f"CPBUniqueID = '{ProcessGUID}'", 'isActive': True}])
    Processlayer.updateDefinitionQueries([{'name': query_name, 'sql': f"GlobalID = '{ProcessGUID}'", 'isActive': True}])

    for layer in [Pointslayer, Substractionslayer, Parcelslayer]:
        layer.updateDefinitionQueries([{'name': query_name, 'sql': f"Role IN (2,3) AND CPBUniqueID = '{ProcessGUID}'", 'isActive': True}])
        RefreshLayer(layer)

    parcels3D_guids: set[str] = {row[0] for row in SearchCursor(Parcelslayer, 'GlobalID')}
    if parcels3D_guids:  # 3D plans types of substraction-recalculation  won't contain new parcels
        parcels3D_guids: str = ", ".join(f"'{p}'" for p in parcels3D_guids)
        ProjectedParcelslayer.updateDefinitionQueries([{'name': query_name, 'sql': f" Parcel3DUniqueID IN ({parcels3D_guids}) ", 'isActive': True}])
    else:
        ProjectedParcelslayer.updateDefinitionQueries([{'name': query_name, 'sql': f" OBJECTID = -1 ", 'isActive': True}])

    substractions_guids: set[str] = {row[0] for row in SearchCursor(Substractionslayer, 'GlobalID')}
    if substractions_guids:  # 3D plans types of substraction-recalculation  won't contain new substractions
        substractions_guids: str = ", ".join(f"'{s}'" for s in substractions_guids)
        ProjectedSubstractionslayer.updateDefinitionQueries([{'name': query_name, 'sql': f" SubstractionUniqueID IN ({substractions_guids}) ", 'isActive': True}])
    else:
        ProjectedSubstractionslayer.updateDefinitionQueries([{'name': query_name, 'sql': f" OBJECTID = -1 ", 'isActive': True}])

    del parcels3D_guids, substractions_guids

    for layer in [Pointslayer, Parcelslayer, Substractionslayer]:
        features_exist(layer)

    filter_to_aoi(ProcessName)


def load_new_3D_parcels(ProcessName: str) -> None:
    """
    Loads new 3D parcels from a process into the active 3D parcel layer based on a specific process name.
    When a 3D process does not create new 3D Parcel (for instance 3D Process that contains only substractions calculation) the function will skip.
    Note: The arcpy.da.InsertCursor will not work here since the SHAPE@ token can't create multipatch geometry object.

    Parameters:
        ProcessName (str): The name of the process that created the 3D parcels.
    """
    AddMessage(f'\n ⭕ Adding new 3D parcels:')

    # Count the new 3D parcels to be loaded. 3D process that performs only subtraction calculations will result in zero new 3D parcels.
    inprocess_parcels3D: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessParcels3D"
    query: str = f"Role = 2 AND CPBUniqueID = '{get_ProcessGUID(ProcessName)}'"
    count: int = cursor_length(SearchCursor(inprocess_parcels3D, "OBJECTID", query))

    if count > 0:
        AddMessage(f'{timestamp()} | ⚡ {count} New parcels will be added')

        # Export inprocess 3D parcels to home GDB and add necessary fields
        ENV.preserveGlobalIds = False
        ENV.addOutputsToMap = False
        FieldMap: str = fr'GlobalID "מזהה חלקה" false false true 38 GlobalID 0 0,First,#,5011\2022 תכנית\חלקות חדשות,GlobalID,-1,-1;' + \
                        fr'ParcelNumber "מספר חלקה" true false false 2 Short 0 0,First,#,{inprocess_parcels3D},ParcelNumber,-1,-1;' + \
                        fr'BlockNumber "מספר גוש" true false false 4 Long 0 0,First,#,{inprocess_parcels3D},BlockNumber,-1,-1;' + \
                        fr'SubBlockNumber "מספר תת-גוש" true false false 2 Short 0 0,First,#,{inprocess_parcels3D},SubBlockNumber,-1,-1;' + \
                        fr'BlockUniqueID "מזהה גוש" true true false 38 Guid 0 0,First,#,{inprocess_parcels3D},BlockUniqueID,-1,-1;' + \
                        fr'StatedVolume "נפח רשום במטר מעוקב" true false false 8 Double 0 0,First,#,{inprocess_parcels3D},StatedVolume,-1,-1;' + \
                        fr'ProjectedArea "שטח היטל" true false false 8 Double 0 0,First,#,{inprocess_parcels3D},ProjectedArea,-1,-1;' + \
                        fr'UpperLevel "רום עליון" true false false 8 Double 0 0,First,#,{inprocess_parcels3D},UpperLevel,-1,-1;' + \
                        fr'LowerLevel "רום תחתון" true false false 8 Double 0 0,First,#,{inprocess_parcels3D},LowerLevel,-1,-1;' + \
                        fr'LandDesignation "ייעוד קרקע" true true false 100 Text 0 0,First,#,{inprocess_parcels3D},LandDesignation,0,99;' + \
                        fr'LandDescription "תיאור קרקע" true true false 100 Text 0 0,First,#,{inprocess_parcels3D},LandDescription,0,99;' + \
                        fr'LandType "סוג מקרקעין" true false false 2 Short 0 0,First,#,{inprocess_parcels3D},LandType,-1,-1;' + \
                        fr'IsTax "שומא" true false false 2 Short 0 0,First,#,{inprocess_parcels3D},IsTax,-1,-1'

        exported_name: str = fr"{ArcGISProject('current').defaultGeodatabase}\new_parcels"
        new_parcels: Result = ExportFeatures(in_features= inprocess_parcels3D, out_features= exported_name, where_clause= query, field_mapping= FieldMap)
        new_parcels: Layer = MakeLayer(new_parcels, "new_parcels").getOutput(0)

        # Add and calculate fields in the exported feature class
        AddField(new_parcels, "Name", field_type="TEXT", field_alias="מספר מלא", field_length= 25)
        AddField(new_parcels, "ParcelType", field_type="SHORT", field_alias="סוג חלקה", field_domain="")
        AddField(new_parcels, "CreatedByRecord", field_type="GUID", field_alias="מזהה תהליך יוצר")
        AddField(new_parcels, "CreateProcessType", field_type= "SHORT", field_alias="סוג תהליך יוצר", )

        CalculateField(new_parcels, "ParcelType", expression= 2, expression_type="PYTHON3")
        CalculateField(new_parcels, "CreatedByRecord", expression= f"'{get_RecordGUID(ProcessName, 'SHELF')}'", expression_type= "PYTHON3")
        CalculateField(new_parcels, "CreateProcessType", expression= Type2CreateType(get_ProcessType(ProcessName)), expression_type= "PYTHON3")

        new_parcel_numbers: Ucur = UpdateCursor(new_parcels, ['ParcelNumber', 'BlockNumber', 'SubBlockNumber'])
        for idx, parcel in enumerate(new_parcel_numbers, start=1):
            temporary_parcel: int = parcel[0]
            parcel[0] = get_FinalParcel(temporary_parcel, parcel[1], parcel[2])
            new_parcel_numbers.updateRow(parcel)
            AddMessage(f'{timestamp()} | {idx}/{count} | ✔️ Temporary parcel {temporary_parcel} added as active parcel {parcel[0]} at block {parcel[1]}/{parcel[2]}')
        del new_parcel_numbers

        code_block: str = """def ConcatenateFields(*args): return "/".join([str(i) for i in args if i])"""
        CalculateField(new_parcels, "Name", expression="ConcatenateFields(!ParcelNumber!, !BlockNumber!, !SubBlockNumber!)", expression_type="PYTHON3", code_block=code_block)
        del code_block, new_parcels, FieldMap, exported_name


    else:
        AddMessage(f'{timestamp()} | ✔️ No new 3D Parcels to add')

    del count


def load_new_projected_3D_parcels() -> None:
    """

    """
    AddMessage(f'\n ⭕ Adding new projections of 3D parcels:')

    # The exported new parcels from load_new_3D_parcels executed earlier
    new_parcels3D_path: str = fr"{ArcGISProject('current').defaultGeodatabase}\new_parcels"

    # Export the new projections of 3D parcels of the process
    # Note: exporting directly from the layer of היטלי חלקות חדשות generated an empty output for some reason, hence the export input will be from the feature class.
    ENV.preserveGlobalIds = False
    process_projection_path: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessProjectedParcels3D"
    exported_projections_path: str = fr"{ArcGISProject('current').defaultGeodatabase}\new_parcels_projections"
    query: str = get_layer('היטלי חלקות חדשות').definitionQuery
    field_mapping: str = fr'Parcel3DUniqueID "מזהה חלקה תלת-ממדית" true true false 38 Guid 0 0,First,#,{process_projection_path},Parcel3DUniqueID,-1,-1;' + \
                         fr'GlobalID "מזהה היטל חלקה תלת-ממדית" false false true 38 GlobalID 0 0,First,#,{process_projection_path},GlobalID,-1,-1;' + \
                         fr'Shape__Area "שטח גיאומטריה" false true true 0 Double 0 0,First,#,{process_projection_path},Shape__Area,-1,-1;' + \
                         fr'Shape__Length "היקף גיאומטריה" false true true 0 Double 0 0,First,#,{process_projection_path},Shape__Length,-1,-1'
    ExportFeatures(in_features= process_projection_path, out_features= exported_projections_path, field_mapping=field_mapping, where_clause=query)  # -> The exported features will have new Global IDs

    # Calculate and replace the Parcel3DUniqueID values from guid of the in-process parcel to the active parcels.
    new_projections: Ucur = UpdateCursor(exported_projections_path, 'Parcel3DUniqueID')
    count: int = cursor_length(new_projections)
    inprocess_parcels3D_path: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessParcels3D"

    for idx, projection in enumerate(new_projections, start=1):
        # Get the final parcel number
        inprocess_parcel_guid: str = projection[0]  # The value to be replaced
        temporary_parcel_info: Scur = SearchCursor(inprocess_parcels3D_path, ['ParcelNumber', 'BlockNumber', 'SubBlockNumber'], f"GlobalID = '{inprocess_parcel_guid}'")
        temp_number, block, subblock = temporary_parcel_info.next()
        final_parcel_num: int = get_FinalParcel(temp_number, block, subblock)
        del inprocess_parcel_guid, temporary_parcel_info

        # Get the final parcel GUID and update the value
        final_parcel_guid: str = SearchCursor(new_parcels3D_path, 'GlobalID', f"Name = '{final_parcel_num}/{block}/{subblock}'").next()[0]
        projection[0]: str = final_parcel_guid  # Replacing te value with the correct GlobalID
        new_projections.updateRow(projection)
        AddMessage(f'{timestamp()} | {idx}/{count} | ✔️ Projection of 3D parcel {final_parcel_num} at block {block}/{subblock} added')
        del final_parcel_num, final_parcel_guid

    del new_projections, count, exported_projections_path, new_parcels3D_path, inprocess_parcels3D_path


def load_new_substractions(ProcessName: str) -> None:
    """

    """
    AddMessage(f'\n ⭕ Adding new substractions:')
    # Count the new substractions to be loaded.
    inprocess_substractions: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessSubstractions"
    query: str = f"Role = 2 AND CPBUniqueID = '{get_ProcessGUID(ProcessName)}'"
    count: int = cursor_length(SearchCursor(inprocess_substractions, "OBJECTID", query))

    if count > 0:
        AddMessage(f'{timestamp()} | ⚡ {count} New substractions will be added')

        # Export inprocess substractions to home GDB and add necessary fields
        ENV.preserveGlobalIds = False
        ENV.addOutputsToMap = False

        FieldMap: str = fr'GlobalID "מזהה גריעה" false false true 38 GlobalID 0 0,First,#,{inprocess_substractions},GlobalID,-1,-1;' + \
                        fr'TemporarySubstractionNumber "מספר גריעה ארעי" true true false 10 Short 0 0,First,#,{inprocess_substractions},TemporarySubstractionNumber,-1,-1;' + \
                        fr'FinalSubstractionNumber "מספר גריעה סופי" true true false 10 Short 0 0,First,#,{inprocess_substractions},FinalSubstractionNumber,-1,-1;' + \
                        fr'Parcel3DNumber "מספר חלקה תלת-ממדית" true false false 10 Short 0 0,First,#,{inprocess_substractions},Parcel3DNumber,-1,-1;' + \
                        fr'Parcel2DNumber "מספר חלקה קרקעית" true false false 10 Short 0 0,First,#,{inprocess_substractions},Parcel2DNumber,-1,-1;' + \
                        fr'Parcel2DType "סוג חלקה קרקעית" true true false 2 Short 0 0,First,#,{inprocess_substractions},Parcel2DType,-1,-1;' + \
                        fr'BlockNumber "מספר גוש" true false false 10 Long 0 0,First,#,{inprocess_substractions},BlockNumber,-1,-1;' + \
                        fr'SubBlockNumber "מספר תת-גוש" true false false 2 Short 0 0,First,#,{inprocess_substractions},SubBlockNumber,-1,-1;' + \
                        fr'StatedVolume "נפח רשום במעוקב" true false false 8 Double 0 0,First,#,{inprocess_substractions},StatedVolume,-1,-1;' + \
                        fr'ProjectedArea "שטח היטל" true false false 8 Double 0 0,First,#,{inprocess_substractions},ProjectedArea,-1,-1;' + \
                        fr'UpperLevel "רום עליון" true false false 8 Double 0 0,First,#,{inprocess_substractions},UpperLevel,-1,-1;' + \
                        fr'LowerLevel "רום תחתון" true false false 8 Double 0 0,First,#,{inprocess_substractions},LowerLevel,-1,-1;' + \
                        fr'RelativePosition "מיקום גריעה ביחס לפני הקרקע" true false false 2 Short 0 0,First,#,{inprocess_substractions},RelativePosition,-1,-1;' + \
                        fr'SubstractionType "סוג גריעה" true false false 2 Short 0 0,First,#,{inprocess_substractions},SubstractionType,-1,-1;' + \
                        fr'Parcel3DUniqueID "מזהה חלקה תלת-ממדית" true true false 38 Guid 0 0,First,#,{inprocess_substractions},Parcel3DUniqueID,-1,-1;' + \
                        fr'Parcel2DUniqueID "מזהה חלקה קרקעית" true true false 38 Guid 0 0,First,#,{inprocess_substractions},Parcel2DUniqueID,-1,-1;' + \
                        fr'BlockUniqueID "מזהה גוש" true true false 38 Guid 0 0,First,#,{inprocess_substractions},BlockUniqueID,-1,-1'


        exported_name: str = fr"{ArcGISProject('current').defaultGeodatabase}\new_substractions"
        ExportFeatures(in_features= inprocess_substractions, out_features= exported_name, where_clause= query, field_mapping= FieldMap)

        # Arrange necessary fields in the exported feature class:

        # - SubstractionNumber:
        AlterField(in_table= exported_name, field="FinalSubstractionNumber", new_field_name="SubstractionNumber", new_field_alias="מספר גריעה", field_type="SHORT", field_is_nullable="NULLABLE")
        #   - Name:
        AddField(exported_name, "Name", field_type="TEXT", field_alias="מספר מלא", field_length=25)
        CalculateField(exported_name, "Name", "ConcatenateFields(!SubstractionNumber!, !BlockNumber!, !SubBlockNumber!)", "PYTHON3", """def ConcatenateFields(*args): return "/".join([str(i) for i in args if i])""")
        #   - SubstractionType:
        CalculateField(exported_name, "SubstractionType", expression=2, expression_type="PYTHON3")
        #   - CreatedByRecord:
        AddField(exported_name, "CreatedByRecord", field_type= "GUID", field_alias= "מזהה תהליך יוצר")
        CalculateField(exported_name, "CreatedByRecord", expression=f"'{get_RecordGUID(ProcessName, 'SHELF')}'", expression_type="PYTHON3")
        #   - CreateProcessType:
        AddField(exported_name, "CreateProcessType", field_type= "SHORT", field_alias= "סוג תהליך יוצר", )
        CalculateField(exported_name, "CreateProcessType", expression= Type2CreateType(get_ProcessType(ProcessName)), expression_type= "PYTHON3")
        #   - :
        fields: list[str] = ['Parcel3DNumber', 'BlockNumber', 'SubBlockNumber', 'TemporarySubstractionNumber', 'SubstractionNumber', 'Parcel3DUniqueID', 'Parcel2DNumber', 'Parcel2DUniqueID', 'Parcel2DType']
        info: Ucur = UpdateCursor(exported_name, fields)
        for idx, row in enumerate(info, start=1):
            row[0]: int = get_FinalParcel(row[0], row[1], row[2])
            row[5]: str = SearchCursor(fr"{ArcGISProject('current').defaultGeodatabase}\new_parcels", 'GlobalID', f"ParcelNumber = {row[0]}").next()[0]  # The new Name of the 3D parcel. Note: the function get_ActiveParcel3DGUID won't work here since the source of 3D parcels is a local export at this moment.

            # If 2D parcel is temporary - the 2D parcel fields will be updated.
            if row[8] == 1:
                row[6]: int = get_FinalParcel(row[6], row[1], row[2])  # The finalParcel2D number
                row[7]: str = get_ActiveParcel2DGUID(f"{row[6]}/{row[1]}/{row[2]}")  # The new Name of the 3D parcel
                row[8]: int = 2  # Final (סופית)

            info.updateRow(row)
            AddMessage(f'{timestamp()} | {idx}/{count} | ✔️ Temporary substraction {row[3]} added as active substraction {row[4]} at block {row[1]}/{row[2]}')

        del fields, info, exported_name, FieldMap

    del inprocess_substractions, query, count


def load_new_projected_substractions(ProcessName) -> None:
    """

    """
    AddMessage(f'\n ⭕ Adding new projections of substractions:')

    # Export the new projections of substractions of the process
    new_substractions_path: str = fr"{ArcGISProject('current').defaultGeodatabase}\new_substractions"  # The exported new substractions from load_new_substraction executed earlier
    inprocess_substractions_path: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessSubstractions"
    inprocess_projected_substractions: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessProjectedSubstractions"
    new_substractions_projections: str = fr"{ArcGISProject('current').defaultGeodatabase}\new_substractions_projections"

    # Note: exporting directly from the layer of היטלי גריעות חדשות generated an empty output for some reason, hence the export input will be from the feature class.
    ENV.preserveGlobalIds = False
    query: str = f"CPBUniqueID = '{get_ProcessGUID(ProcessName)}' And Role = 2"
    new_substractions_guids: str = ", ".join(f"'{guid[0]}'" for guid in SearchCursor(inprocess_substractions_path, 'GlobalID', query))
    query: str = f"SubstractionUniqueID IN ({new_substractions_guids})"
    field_mapping: str = fr'SubstractionUniqueID "מזהה גריעה" true true false 38 Guid 0 0,First,#,{inprocess_projected_substractions},SubstractionUniqueID,-1,-1;' + \
                         fr'GlobalID "מזהה היטל גריעה" false false true 38 GlobalID 0 0,First,#,{inprocess_projected_substractions},GlobalID,-1,-1;' + \
                         fr'Shape__Area "שטח גיאומטריה" false true true 0 Double 0 0,First,#,{inprocess_projected_substractions},Shape__Area,-1,-1;' + \
                         fr'Shape__Length "היקף גיאומטריה" false true true 0 Double 0 0,First,#,{inprocess_projected_substractions},Shape__Length,-1,-1'

    ExportFeatures(inprocess_projected_substractions, new_substractions_projections, query, field_mapping= field_mapping)  # -> The exported features will have new Global IDs
    del inprocess_projected_substractions, field_mapping, new_substractions_guids
    # Calculate and replace the SubstractionUniqueID values from guid of the in-process parcel to the active substraction.

    new_substractions_projections: Ucur = UpdateCursor(new_substractions_projections, 'SubstractionUniqueID')
    count: int = cursor_length(new_substractions_projections)

    for idx, row in enumerate(new_substractions_projections, start=1):
        SubstractionNumber, BlockNumber, SubBlockNumber = SearchCursor(inprocess_substractions_path, ['FinalSubstractionNumber', 'BlockNumber', 'SubBlockNumber'], f"GlobalID = '{row[0]}'").next()
        query: str = f"SubstractionNumber = {SubstractionNumber} And BlockNumber = {BlockNumber} And SubBlockNumber = {SubBlockNumber}"
        new_substraction_guid: str = SearchCursor(new_substractions_path, 'GlobalID', query).next()[0]

        row[0]: str = new_substraction_guid
        new_substractions_projections.updateRow(row)
        AddMessage(f'{timestamp()} | {idx}/{count} | ✔️ Projection of substraction {SubstractionNumber} at block {BlockNumber}/{SubBlockNumber} added')

    del new_substractions_path, inprocess_substractions_path, new_substractions_projections, count


def load_new_3D_points(ProcessName: str) -> None:
    """
    Load new 3D border points features into the active 3D border points layer.
    This function fetches new points data from the 'נקודות לשימור וחדשות' layer, compute additional necessary fields
    and appends it to the 'נקודות גבול תלת-ממדיות' layer in the current ArcGIS project Scene map.

    Parameters:
        ProcessName (str): The name of the process that created the 3D points.
    """

    AddMessage(f'\n ⭕ Adding new 3D border points:')

    process_points_patch: str = f"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessBorderPoints3D"
    data_fields: list[str] = ['Name', 'Class', 'DataSource', 'IsControlBorder', 'Shape@']
    query: str = f"CPBUniqueID = '{get_ProcessGUID(ProcessName)}' And Role = 2"  # חדשות בלבד
    new_data: Scur = SearchCursor(process_points_patch, data_fields, query)
    total: int = cursor_length(new_data)

    if total > 0:
        AddMessage(f'{timestamp()} | ⚡ {total} New 3D points will be added')
        record_guid: str = get_RecordGUID(ProcessName, 'SHELF')
        fields_to_compute: list[str] = ['X', 'Y', 'Z', 'CreatedByRecord']
        active_3D_points: Icur = InsertCursor(get_layer('נקודות גבול תלת-ממדיות'),  data_fields + fields_to_compute)

        for row in new_data:
            # TODO: if the calculation attribute rules will work on X,Y,Z fields- this coordinates calculation should be removed
            # Compute geometry fields (even if calculation rules automatically computed them)
            x_coord: float = row[4].centroid.X
            y_coord: float = row[4].centroid.Y
            z_coord: float = row[4].centroid.Z

            # Add the new point data
            updated_row: tuple[Any] = row + (x_coord, y_coord, z_coord, record_guid,)
            active_3D_points.insertRow(updated_row)

        del active_3D_points, record_guid, fields_to_compute
        AddMessage(f'{timestamp()} | ✔️ 3D points added successfully')

    else:
        AddMessage(f'{timestamp()} | ✔️ No new 3D points to add')

    del process_points_patch, data_fields, query, new_data, total


def append_parcels3D_and_substractions_data() -> None:
    """
    Loads all the new features from the exported feature classes with their new GlobalID values preserved.
    """
    AddMessage(f'\n ⭕ Loading all new features:')
    home_gdb: str = ArcGISProject('current').defaultGeodatabase
    ENV.preserveGlobalIds = True

    # Parcels3D:
    inputs: str = fr"{home_gdb}\new_parcels"
    FM: str = fr'GlobalID "מזהה חלקה" false false true 38 GlobalID 0 0,First,#,{inputs},GlobalID,-1,-1;' + \
              fr'ParcelNumber "מספר חלקה" true false false 2 Short 0 0,First,#,{inputs},ParcelNumber,-1,-1;' + \
              fr'BlockNumber "מספר גוש" true false false 4 Long 0 0,First,#,{inputs},BlockNumber,-1,-1;' + \
              fr'SubBlockNumber "מספר תת-גוש" true false false 2 Short 0 0,First,#,{inputs},SubBlockNumber,-1,-1;' + \
              fr'BlockUniqueID "מזהה גוש" true true false 38 Guid 0 0,First,#,{inputs},BlockUniqueID,-1,-1;' + \
              fr'ParcelType "סוג חלקה" true false false 2 Short 0 0,First,#,{inputs},ParcelType,-1,-1;' + \
              fr'StatedVolume "נפח רשום במטר מעוקב" true false false 8 Double 0 0,First,#,{inputs},StatedVolume,-1,-1;' + \
              fr'ProjectedArea "שטח היטל" true false false 8 Double 0 0,First,#,{inputs},ProjectedArea,-1,-1;' + \
              fr'UpperLevel "רום עליון" true false false 8 Double 0 0,First,#,{inputs},UpperLevel,-1,-1;' + \
              fr'LowerLevel "רום תחתון" true false false 8 Double 0 0,First,#,{inputs},LowerLevel,-1,-1;' + \
              fr'LandDesignation "ייעוד קרקע" true true false 100 Text 0 0,First,#,{inputs},LandDesignation,0,99;' + \
              fr'LandDescription "תיאור קרקע" true true false 100 Text 0 0,First,#,{inputs},LandDescription,0,99;' + \
              fr'LandType "סוג מקרקעין" true false false 2 Short 0 0,First,#,{inputs},LandType,-1,-1;' + \
              fr'IsTax "שומא" true false false 2 Short 0 0,First,#,{inputs},IsTax,-1,-1;' + \
              fr'Name "מספר מלא" true true false 25 Text 0 0,First,#,{inputs},Name,0,24;' + \
              fr'CreatedByRecord "מזהה תהליך יוצר" true true false 38 Guid 0 0,First,#,{inputs},CreatedByRecord,-1,-1;' + \
              fr'RetiredByRecord "מזהה תהליך מבטל" true true false 38 Guid 0 0,First,#;' + \
              fr'CalculatedArea "שטח מחושב במטר רבוע" true true false 8 Double 0 0,First,#;' + \
              fr'CreateProcessType "סוג תהליך יוצר" true false false 2 Short 0 0,First,#,{inputs},CreateProcessType,-1,-1;' + \
              fr'CancelProcessType "סוג תהליך מבטל" true true false 2 Short 0 0,First,#;' + \
              fr'UpdatedByRecord "מזהה תהליך מעדכן" true true false 38 Guid 0 0,First,#'
    Append(inputs= inputs, target= get_layer('חלקות תלת-ממדיות'), schema_type="NO_TEST", field_mapping= FM, feature_service_mode="USE_FEATURE_SERVICE_MODE")

    # ProjectedParcels3D:
    inputs: str = fr"{home_gdb}\new_parcels_projections"
    FM: str = fr'Parcel3DUniqueID "מזהה חלקה תלת-ממדית" true true false 38 Guid 0 0,First,#,{inputs},Parcel3DUniqueID,-1,-1;' + \
              fr'GlobalID "מזהה היטל חלקה תלת-ממדית" false false true 38 GlobalID 0 0,First,#,{inputs},GlobalID,-1,-1'
    Append(inputs= inputs, target= get_layer('היטלי חלקות תלת-ממדיות'), schema_type="NO_TEST", field_mapping= FM, feature_service_mode="USE_FEATURE_SERVICE_MODE")

    # Substractions:
    inputs: str = fr"{home_gdb}\new_substractions"
    FM: str = fr'GlobalID "מזהה גריעה" false false true 38 GlobalID 0 0,First,#,{inputs},GlobalID,-1,-1;' + \
              fr'SubstractionNumber "מספר גריעה" true false false 2 Short 0 5,First,#,{inputs},SubstractionNumber,-1,-1;' + \
              fr'Parcel3DNumber "מספר חלקה תלת-ממדית" true false false 2 Short 0 5,First,#,{inputs},Parcel3DNumber,-1,-1;' + \
              fr'Parcel2DNumber "מספר חלקה קרקעית" true false false 2 Short 0 5,First,#,{inputs},Parcel2DNumber,-1,-1;' + \
              fr'BlockNumber "מספר גוש" true false false 4 Long 0 10,First,#,{inputs},BlockNumber,-1,-1;' + \
              fr'SubBlockNumber "מספר תת-גוש" true false false 2 Short 0 5,First,#,{inputs},SubBlockNumber,-1,-1;' + \
              fr'StatedVolume "נפח רשום במעוקב" true false false 8 Double 8 38,First,#,{inputs},StatedVolume,-1,-1;' + \
              fr'ProjectedArea "שטח היטל" true false false 8 Double 8 38,First,#,{inputs},ProjectedArea,-1,-1;' + \
              fr'UpperLevel "רום עליון" true false false 8 Double 8 38,First,#,{inputs},UpperLevel,-1,-1;' + \
              fr'LowerLevel "רום תחתון" true false false 8 Double 8 38,First,#,{inputs},LowerLevel,-1,-1;' + \
              fr'RelativePosition "מיקום גריעה ביחס לפני הקרקע" true false false 2 Short 0 5,First,#,{inputs},RelativePosition,-1,-1;' + \
              fr'SubstractionType "סוג גריעה" true false false 2 Short 0 5,First,#,{inputs},SubstractionType,-1,-1;' + \
              fr'Parcel3DUniqueID "מזהה חלקה תלת-ממדית" true true false 38 Guid 0 0,First,#,{inputs},Parcel3DUniqueID,-1,-1;' + \
              fr'Parcel2DUniqueID "מזהה חלקה קרקעית" true true false 38 Guid 0 0,First,#,{inputs},Parcel2DUniqueID,-1,-1;' + \
              fr'BlockUniqueID "מזהה גוש" true true false 38 Guid 0 0,First,#,{inputs},BlockUniqueID,-1,-1;' + \
              fr'CreatedByRecord "מזהה תהליך יוצר" true true false 38 Guid 0 0,First,#,{inputs},CreatedByRecord,-1,-1;' + \
              fr'UpdatedByRecord "מזהה תהליך מעדכן" true true false 38 Guid 0 0,First,#;' + \
              fr'RetiredByRecord "מזהה תהליך מבטל" true true false 38 Guid 0 0,First,#;' + \
              fr'CreateProcessType "סוג תהליך יוצר" true false false 2 Short 0 5,First,#,{inputs},CreateProcessType,-1,-1;' + \
              fr'CancelProcessType "סוג תהליך מבטל" true true false 2 Short 0 5,First,#'
    Append(inputs= inputs, target= get_layer('גריעות'), schema_type="NO_TEST", field_mapping= FM, feature_service_mode="USE_FEATURE_SERVICE_MODE")

    # ProjectedSubstractions:
    inputs: str = fr"{home_gdb}\new_substractions_projections"
    FM: str = fr'SubstractionUniqueID "מזהה גריעה" true true false 38 Guid 0 0,First,#,{inputs},SubstractionUniqueID,-1,-1;' + \
              fr'GlobalID "מזהה היטל גריעה" false false true 38 GlobalID 0 0,First,#,{inputs},GlobalID,-1,-1'
    Append(inputs=inputs, target=get_layer('היטלי גריעות'), schema_type="NO_TEST", field_mapping=FM, feature_service_mode="USE_FEATURE_SERVICE_MODE")

    # Closers
    ENV.preserveGlobalIds = False
    del home_gdb, inputs, FM
    AddMessage(f'{timestamp()} | ✔️ New features loaded to the active layers')


def start_task_RetireAndCreateCadaster3D(ProcessName: str|None) -> None:
    """
    Workflow for starting the Create And Retire Cadaster 3D task.

    Parameters:
        ProcessName (str): The name of the cadaster process.
    """

    set_priority()

    # Whether the process is executed from CMS or independent task.
    ProcessName: str = get_aprx_name() if not ProcessName else ProcessName

    qualified: bool = validation_set('RetireAndCreateCadaster3D', ProcessName)

    if qualified:

        shelf: str = create_shelf(ProcessName)

        open_version(ProcessName)

        startfile(fr'{shelf}')

        if creating_record_is_duplicated(ProcessName):
            update_record_status(ProcessName, new_status=5)  # מעדכן סטאטוס לרשומה
        else:
            load_to_records(ProcessName)

        display_process_data(ProcessName)

        # activate_record(ProcessName)  # Known issue: The records layer is not updated until the end of the execution of GP tool.

        zoom_to_aoi()

        # Retire
        retire_3D_parcels_and_substractions(ProcessName)

        retire_3D_points(ProcessName)

        # Create
        load_new_3D_parcels(ProcessName)
        # TODO: add load_intermediate_3D_parcels(?) if the process is not only creates.

        load_new_projected_3D_parcels()
        # TODO: add load_intermediate_3D_parcels_projections(?) if the process is not only creates.

        load_new_substractions(ProcessName)

        load_new_projected_substractions(ProcessName)

        append_parcels3D_and_substractions_data()

        load_new_3D_points(ProcessName)
        # TODO: add load_intermediate_3D_points(?) if the process is not only creates.

        # TODO: add modify_3D_preserved_points(?) for existing points (Role=3) to update their attributes.

        # Closers
        reopen_map()
        zoom_to_aoi()


if __name__ == "__main__":
    start_task_RetireAndCreateCadaster3D(ProcessName= GetParameterAsText(0))
