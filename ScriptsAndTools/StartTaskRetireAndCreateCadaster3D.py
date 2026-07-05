from arcpy import AddMessage, GetParameter, GetParameterAsText, env as ENV, Exists
from arcpy.mp import ArcGISProject
from arcpy.conversion import ExportFeatures
from arcpy.da import SearchCursor, UpdateCursor, InsertCursor
from arcpy.management import Append, MakeFeatureLayer as MakeLayer, CalculateField, AddField, AlterField, MakeQueryLayer, SelectLayerByLocation as SelectByLocation
from Utils.TypeHints import *
from Utils.Configs import CNFG
from Utils.VersionManagement import open_version
from Utils.UpdateAttributes import retire_3D_parcels_and_substractions, retire_3D_points, update_record_status
from Utils.Validations import validation_set, features_exist, creating_record_is_duplicated
from Utils.Helpers import create_shelf, get_ProcessGUID, get_RecordGUID, timestamp, zoom_to_aoi, filter_to_aoi, \
                          get_FinalParcel, reopen_map, cursor_length, set_priority, load_to_records, Type2CreateType, \
                          get_ProcessType, get_layer, get_aprx_name, activate_record, get_BlockGUID, process_only_creates, \
                          Type2CancelType

ENV.preserveGlobalIds = False
ENV.addOutputsToMap = False


def display_process_data(ProcessName: str) -> None:
    """
    Display process-related data layers in the active map.

    Parameters:
        ProcessName (str): The name of the process for which data is displayed.
    """

    CurrentMap: Map = ArcGISProject("current").listMaps('סצנת עריכה')[0]
    ProcessGUID: str = get_ProcessGUID(ProcessName)
    query_name: str = f'Process {ProcessName}'

    CurrentMap.addDataFromPath(fr'{CNFG.LayerFiles}RetireAndCreateProcess3DGroup_{CNFG.Environment}.lyrx')
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
        FieldMap: str = fr'ParcelNumber "מספר חלקה" true false false 2 Short 0 0,First,#,{inprocess_parcels3D},ParcelNumber,-1,-1;' + \
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
        new_parcels: Layer = MakeLayer(new_parcels, "new_parcels")[0]

        # Add and calculate fields in the exported feature class
        AddField(new_parcels, "ParcelType", field_type="SHORT", field_alias="סוג חלקה", field_domain="")
        AddField(new_parcels, "CreatedByRecord", field_type="GUID", field_alias="מזהה תהליך יוצר")
        AddField(new_parcels, "CreateProcessType", field_type= "SHORT", field_alias="סוג תהליך יוצר")
        AddField(new_parcels, "FinalParcelNumber", field_type="SHORT", field_alias="מספר חלקה סופי")

        CalculateField(new_parcels, "ParcelType", expression= 2, expression_type="PYTHON3")
        CalculateField(new_parcels, "CreatedByRecord", expression= f"'{get_RecordGUID(ProcessName, 'SHELF')}'", expression_type= "PYTHON3")
        CalculateField(new_parcels, "CreateProcessType", expression= Type2CreateType(get_ProcessType(ProcessName)), expression_type= "PYTHON3")

        # Update temporary parcel number to final number
        new_parcel_numbers: Ucur = UpdateCursor(new_parcels, ['ParcelNumber', 'BlockNumber', 'SubBlockNumber', 'FinalParcelNumber'])
        for idx, parcel in enumerate(new_parcel_numbers, start=1):
            temporary_parcel: int = parcel[0]
            parcel[3]: int = get_FinalParcel(temporary_parcel, parcel[1], parcel[2])
            new_parcel_numbers.updateRow(parcel)
            AddMessage(f'{timestamp()} | {idx}/{count} | ✔️ Temporary parcel {temporary_parcel} added as active parcel {parcel[3]} at block {parcel[1]}/{parcel[2]}')
        del new_parcel_numbers

        # Load calculated feature class to versioned layer.
        #    NOTE: 1) The Append will only work by not preserving Global ID's and setting feature_service_mode to False
        #          2) The Name field will automatically be computed by a calculation attribute rule
        FieldMap: str = fr'ParcelNumber "מספר חלקה" true false false 0 Short 0 0,First,#,{exported_name},FinalParcelNumber,-1,-1;' + \
                        fr'BlockNumber "מספר גוש" true false false 0 Long 0 0,First,#,{exported_name},BlockNumber,-1,-1;' + \
                        fr'SubBlockNumber "מספר תת-גוש" true false false 0 Short 0 0,First,#,{exported_name},SubBlockNumber,-1,-1;' + \
                        fr'BlockUniqueID "מזהה גוש" true true false 38 Guid 0 0,First,#,{exported_name},BlockUniqueID,-1,-1;' + \
                        fr'ParcelType "סוג חלקה" true false false 0 Short 0 0,First,#,{exported_name},ParcelType,-1,-1;' + \
                        fr'StatedVolume "נפח רשום במטר מעוקב" true false false 0 Double 0 0,First,#,{exported_name},StatedVolume,-1,-1;' + \
                        fr'ProjectedArea "שטח היטל" true false false 0 Double 0 0,First,#,{exported_name},ProjectedArea,-1,-1;' + \
                        fr'UpperLevel "רום עליון" true false false 0 Double 0 0,First,#,{exported_name},UpperLevel,-1,-1;' + \
                        fr'LowerLevel "רום תחתון" true false false 0 Double 0 0,First,#,{exported_name},LowerLevel,-1,-1;' + \
                        fr'LandDescription "שימושי קרקע" true true false 100 Text 0 0,First,#,{exported_name},LandDescription,0,99;' + \
                        fr'LandType "סוג מקרקעין" true false false 0 Short 0 0,First,#,{exported_name},LandType,-1,-1;' + \
                        fr'IsTax "שומא" true false false 0 Short 0 0,First,#,{exported_name},IsTax,-1,-1;' + \
                        fr'LandDesignation "ייעוד קרקע" true true false 100 Text 0 0,First,#,{exported_name},LandDesignation,0,99;' + \
                        fr'CreatedByRecord "מזהה תהליך יוצר" true true false 38 Guid 0 0,First,#,{exported_name},CreatedByRecord,-1,-1;' + \
                        fr'CreateProcessType "סוג תהליך יוצר" true false false 0 Short 0 0,First,#,{exported_name},CreateProcessType,-1,-1;'

        Append(inputs= exported_name, target= get_layer('חלקות תלת-ממדיות'), schema_type= "NO_TEST", field_mapping= FieldMap, feature_service_mode="NO_FEATURE_SERVICE_MODE")

        del FieldMap, exported_name

    else:
        AddMessage(f'{timestamp()} | ✔️ No new 3D Parcels to add')

    del inprocess_parcels3D, query, count


def load_intermediate_3D_parcels(ProcessName: str) -> None:
    """

    """
    if not process_only_creates(ProcessName):

        # Count the intermediate 3D parcels to be loaded. 3D process that performs only subtraction calculations will result in zero intermediate 3D parcels.
        inprocess_parcels3D: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessParcels3D"
        query: str = f"CPBUniqueID = '{get_ProcessGUID(ProcessName)}' AND Role = 4 "
        count: int = cursor_length(SearchCursor(inprocess_parcels3D, "OBJECTID", query))

        if count > 0:
            AddMessage(f'\n ⭕ Adding intermediate 3D parcels:')
            # Export inprocess 3D parcels to home GDB and add necessary fields
            FieldMap: str = fr'ParcelNumber "מספר חלקה" true false false 2 Short 0 0,First,#,{inprocess_parcels3D},ParcelNumber,-1,-1;' + \
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

            exported_name: str = fr"{ArcGISProject('current').defaultGeodatabase}\intermediate_parcels"
            intermediate_parcels: Result = ExportFeatures(in_features=inprocess_parcels3D, out_features=exported_name, where_clause=query, field_mapping=FieldMap)
            intermediate_parcels: Layer = MakeLayer(intermediate_parcels, "intermediate_parcels")[0]

            # Add and calculate fields in the exported feature class
            AddField(intermediate_parcels, "ParcelType", field_type="SHORT", field_alias="סוג חלקה", field_domain="")
            AddField(intermediate_parcels, "CreatedByRecord", field_type="GUID", field_alias="מזהה תהליך יוצר")
            AddField(intermediate_parcels, "CreateProcessType", field_type="SHORT", field_alias="סוג תהליך יוצר")
            AddField(intermediate_parcels, "FinalParcelNumber", field_type="SHORT", field_alias="מספר חלקה סופי")
            AddField(intermediate_parcels, "RetiredByRecord", field_type="GUID", field_alias="מזהה תהליך מבטל")
            AddField(intermediate_parcels, "CancelProcessType", field_type="SHORT", field_alias="סוג תהליך מבטל")

            records_guid: str = get_RecordGUID(ProcessName, 'SHELF')

            CalculateField(intermediate_parcels, "ParcelType", expression=2, expression_type="PYTHON3")
            CalculateField(intermediate_parcels, "CreatedByRecord", expression=f"'{records_guid}'", expression_type="PYTHON3")
            CalculateField(intermediate_parcels, "CreateProcessType", expression=Type2CreateType(get_ProcessType(ProcessName)), expression_type="PYTHON3")
            CalculateField(intermediate_parcels, "RetiredByRecord", expression=f"'{records_guid}'", expression_type="PYTHON3")
            CalculateField(intermediate_parcels, "CancelProcessType", expression=Type2CancelType(get_ProcessType(ProcessName)), expression_type="PYTHON3")
            del records_guid

            # Update temporary parcel number to final number
            intermediate_parcels_numbers: Ucur = UpdateCursor(intermediate_parcels, ['ParcelNumber', 'BlockNumber', 'SubBlockNumber', 'FinalParcelNumber'])
            for idx, parcel in enumerate(intermediate_parcels_numbers, start=1):
                temporary_parcel: int = parcel[0]
                parcel[3]: int = get_FinalParcel(temporary_parcel, parcel[1], parcel[2])
                intermediate_parcels_numbers.updateRow(parcel)
                AddMessage(f'{timestamp()} | {idx}/{count} | ✔️ Temporary parcel {temporary_parcel} added as intermediate parcel {parcel[3]} at block {parcel[1]}/{parcel[2]}')
            del intermediate_parcels_numbers


            # Load calculated feature class to versioned layer.
            #    NOTE: 1) The Append will only work by not preserving Global ID's and setting feature_service_mode to False
            #          2) The Name field will automatically be computed by a calculation attribute rule
            FieldMap: str = fr'ParcelNumber "מספר חלקה" true false false 0 Short 0 0,First,#,{exported_name},FinalParcelNumber,-1,-1;' + \
                            fr'BlockNumber "מספר גוש" true false false 0 Long 0 0,First,#,{exported_name},BlockNumber,-1,-1;' + \
                            fr'SubBlockNumber "מספר תת-גוש" true false false 0 Short 0 0,First,#,{exported_name},SubBlockNumber,-1,-1;' + \
                            fr'BlockUniqueID "מזהה גוש" true true false 38 Guid 0 0,First,#,{exported_name},BlockUniqueID,-1,-1;' + \
                            fr'ParcelType "סוג חלקה" true false false 0 Short 0 0,First,#,{exported_name},ParcelType,-1,-1;' + \
                            fr'StatedVolume "נפח רשום במטר מעוקב" true false false 0 Double 0 0,First,#,{exported_name},StatedVolume,-1,-1;' + \
                            fr'ProjectedArea "שטח היטל" true false false 0 Double 0 0,First,#,{exported_name},ProjectedArea,-1,-1;' + \
                            fr'UpperLevel "רום עליון" true false false 0 Double 0 0,First,#,{exported_name},UpperLevel,-1,-1;' + \
                            fr'LowerLevel "רום תחתון" true false false 0 Double 0 0,First,#,{exported_name},LowerLevel,-1,-1;' + \
                            fr'LandDescription "שימושי קרקע" true true false 100 Text 0 0,First,#,{exported_name},LandDescription,0,99;' + \
                            fr'LandType "סוג מקרקעין" true false false 0 Short 0 0,First,#,{exported_name},LandType,-1,-1;' + \
                            fr'IsTax "שומא" true false false 0 Short 0 0,First,#,{exported_name},IsTax,-1,-1;' + \
                            fr'LandDesignation "ייעוד קרקע" true true false 100 Text 0 0,First,#,{exported_name},LandDesignation,0,99;' + \
                            fr'CreatedByRecord "מזהה תהליך יוצר" true true false 38 Guid 0 0,First,#,{exported_name},CreatedByRecord,-1,-1;' + \
                            fr'RetiredByRecord "מזהה תהליך מבטל" true true false 38 Guid 0 0,First,#,{exported_name},RetiredByRecord,-1,-1;' + \
                            fr'CreateProcessType "סוג תהליך יוצר" true false false 0 Short 0 0,First,#,{exported_name},CreateProcessType,-1,-1;' + \
                            fr'CancelProcessType "סוג תהליך מבטל" true false false 0 Short 0 0,First,#,{exported_name},CancelProcessType,-1,-1;'

            Append(inputs=exported_name, target=get_layer('חלקות תלת-ממדיות'), schema_type="NO_TEST", field_mapping=FieldMap, feature_service_mode="NO_FEATURE_SERVICE_MODE")
            del FieldMap, exported_name


def load_new_projected_3D_parcels() -> None:
    """

    """

    AddMessage(f'\n ⭕ Adding new projections of 3D parcels:')

    # Count the new projections to be loaded. Note: 3D process that performs only subtraction calculations will result in zero new projections.
    inprocess_projected_parcels3D: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessProjectedParcels3D"
    query: str = get_layer('היטלי חלקות חדשות').definitionQuery
    count: int = cursor_length(SearchCursor(inprocess_projected_parcels3D, "OBJECTID", query))

    if count > 0:
        AddMessage(f'{timestamp()} | ⚡ {count} New parcel projections will be added')

        # Export inprocess 3D parcels projections to home GDB

        new_3D_parcels_guids: list[str] = []
        projections_export: str = fr"{ArcGISProject('current').defaultGeodatabase}\new_parcels_projections"

        FieldMap: str = fr'Parcel3DUniqueID "מזהה חלקה תלת-ממדית" true true false 38 Guid 0 0,First,#,{inprocess_projected_parcels3D},Parcel3DUniqueID,-1,-1;'
        new_projections: Result = ExportFeatures(inprocess_projected_parcels3D, projections_export, query, field_mapping= FieldMap)
        new_projections: Layer = MakeLayer(new_projections, "new_projections")[0]

        # Add GUID field of the new 3D parcel in the exported feature class and compute it.
        AddField(new_projections, "FinalParcelGlobalID", "GUID", field_alias="מזהה חלקה תלת ממדית סופית")

        inprocess_parcels3D: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessParcels3D"
        new_projections_cursor: Ucur = UpdateCursor(new_projections, ['Parcel3DUniqueID', 'FinalParcelGlobalID'])

        for idx, row in enumerate(new_projections_cursor, start=1):
            temporary_parcel: list[int] = [[i[0], i[1], i[2]] for i in SearchCursor(inprocess_parcels3D, ['ParcelNumber', 'BlockNumber', 'SubBlockNumber'], f"GlobalID='{row[0]}'")][0]
            final_parcel_number: int = get_FinalParcel(temporary_parcel[0], temporary_parcel[1], temporary_parcel[2])
            final_parcel_name: str = f"{final_parcel_number}/{ temporary_parcel[1]}/{temporary_parcel[2]}"
            final_parcel_guid_query: str = f"""SELECT TOP 1 GlobalID
                                               FROM PF.Parcels3D
                                               WHERE Name = '{final_parcel_name}' AND GDB_IS_DELETE = 0
                                               ORDER BY GDB_ARCHIVE_OID DESC"""
            final_parcel_guid_result: Table = MakeQueryLayer(CNFG.ParcelFabricDatabase, 'final_parcel_guid_result', final_parcel_guid_query)[0]
            final_parcel_guid: str = SearchCursor(final_parcel_guid_result, 'GlobalID').next()[0]
            row[1]: str = final_parcel_guid
            new_projections_cursor.updateRow(row)

            new_3D_parcels_guids.append(final_parcel_guid)
            AddMessage(f'{timestamp()} | {idx}/{count} | ✔️ Projection for parcel {final_parcel_number} at block {temporary_parcel[1]}/{temporary_parcel[2]} added')

        FieldMap: str = fr'Parcel3DUniqueID "מזהה חלקה תלת-ממדית" true true false 38 Guid 0 0,First,#,{projections_export},FinalParcelGlobalID,-1,-1;'
        projected_layer: Layer = get_layer('היטלי חלקות תלת-ממדיות')
        Append(projections_export, projected_layer, "NO_TEST", FieldMap, feature_service_mode="USE_FEATURE_SERVICE_MODE")
        del new_projections_cursor, FieldMap, inprocess_parcels3D, new_projections, projections_export

        # Update the filter of active projected layer
        new_3D_parcels: str = ', '.join(["'" + guid + "'" for guid in new_3D_parcels_guids])

        aoi_blocks_layer: Layer = SelectByLocation(get_layer('גושים'), 'INTERSECT', get_layer('גבול תכנית'), "1 Meter")[0]
        aoi_blocks: Scur = SearchCursor(aoi_blocks_layer, 'GlobalID', "RetiredByRecord IS NULL")
        aoi_blocks: str = ', '.join(["'" + row[0] + "'" for row in aoi_blocks])
        ArcGISProject('current').activeMap.clearSelection()

        aoi_3D_parcels: Scur = SearchCursor(get_layer('חלקות תלת-ממדיות'), 'GlobalID', f"RetiredByRecord IS NULL AND BlockUniqueID IN ({aoi_blocks})")
        del aoi_blocks_layer, aoi_blocks

        if cursor_length(aoi_3D_parcels) > 0:
            aoi_3D_parcels: str = ', '.join(["'" + row[0] + "'" for row in aoi_3D_parcels])
            sql: str = f"Parcel3DUniqueID IN ({aoi_3D_parcels},{new_3D_parcels})"
        else:
            sql: str = f"Parcel3DUniqueID IN ({new_3D_parcels})"

        query_params: dict[str, Any] = {'name': 'Area of Interest', 'sql': sql, 'isActive': True}
        projected_layer.updateDefinitionQueries([query_params])

        del projected_layer, new_3D_parcels, aoi_3D_parcels, sql, query_params
    del inprocess_projected_parcels3D, query, count


def load_intermediate_3D_parcels_projections() -> None:
    """

    """
    intermediate_3D_parcels: str = fr"{ArcGISProject('current').defaultGeodatabase}\intermediate_parcels"
    if Exists(intermediate_3D_parcels):

        pass
    # TODO: continue


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

        FieldMap: str = fr'TemporarySubstractionNumber "מספר גריעה ארעי" true true false 10 Short 0 0,First,#,{inprocess_substractions},TemporarySubstractionNumber,-1,-1;' + \
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
                        fr'BlockUniqueID "מזהה גוש" true true false 38 Guid 0 0,First,#,{inprocess_substractions},BlockUniqueID,-1,-1;' + \
                        fr'Parcel2DUniqueID "מזהה חלקה קרקעית" true true false 38 Guid 0 0,First,#,{inprocess_substractions},Parcel2DUniqueID,-1,-1'

        exported_name: str = fr"{ArcGISProject('current').defaultGeodatabase}\new_substractions"
        ExportFeatures(in_features= inprocess_substractions, out_features= exported_name, where_clause= query, field_mapping= FieldMap)

        # Arrange and update necessary fields in the exported feature class:

        # - SubstractionNumber:
        AlterField(in_table= exported_name, field="FinalSubstractionNumber", new_field_name="SubstractionNumber", new_field_alias="מספר גריעה", field_type="SHORT", field_is_nullable="NULLABLE")
        #   - SubstractionType:
        CalculateField(exported_name, "SubstractionType", expression=2, expression_type="PYTHON3")
        #   - CreatedByRecord:
        AddField(exported_name, "CreatedByRecord", field_type= "GUID", field_alias= "מזהה תהליך יוצר")
        CalculateField(exported_name, "CreatedByRecord", expression=f"'{get_RecordGUID(ProcessName, 'SHELF')}'", expression_type="PYTHON3")
        #   - CreateProcessType:
        AddField(exported_name, "CreateProcessType", field_type= "SHORT", field_alias= "סוג תהליך יוצר", )
        CalculateField(exported_name, "CreateProcessType", expression= Type2CreateType(get_ProcessType(ProcessName)), expression_type= "PYTHON3")
        #   - Final parcels numbers, block guid and 2D parcel type:
        fields: list[str] = ['Parcel3DNumber', 'BlockNumber', 'SubBlockNumber', 'TemporarySubstractionNumber', 'SubstractionNumber', 'Parcel2DNumber', 'Parcel2DType', 'BlockUniqueID', 'Parcel2DUniqueID']
        # row indexes               0                1               2                        3                         4                   5                6                7                 8
        info: Ucur = UpdateCursor(exported_name, fields)
        for idx, row in enumerate(info, start=1):
            block_name: str  = fr"{row[1]}/{row[2]}"
            # BlockUniqueID
            row[7]: str = get_BlockGUID('BlockName', block_name)
            # Final 3D Parcel Number
            row[0]: int = get_FinalParcel(row[0], row[1], row[2])
            # If 2D parcel is temporary...
            if row[6] == 1:
                # Final 2D Parcel Number
                referenced_process_guid: str = SearchCursor(fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessParcels2D", 'CPBUniqueID', f"GlobalID = '{row[8]}'").next()[0]
                row[5]: int = get_FinalParcel(row[5], row[1], row[2], referenced_process_guid)
                # Final 2D Parcel Type (סופית)
                row[6]: int = 2

            info.updateRow(row)
            AddMessage(f'{timestamp()} | {idx}/{count} | ✔️ Temporary substraction {row[3]} added as active substraction {row[4]} at block {block_name}')

        # Load calculated feature class to versioned layer.
        #    NOTE: 1) The Append will only work by not preserving Global ID's and setting feature_service_mode to False.
        #          2) The Name, Parcel3DUniqueID and Parcel2DUniqueId fields will automatically be computed by a calculation attribute rule.
        FieldMap: str = fr'SubstractionNumber "מספר גריעה" true false false 0 Short 0 0,First,#,{exported_name},SubstractionNumber,-1,-1;' + \
                        fr'Parcel3DNumber "מספר חלקה תלת-ממדית" true false false 0 Short 0 0,First,#,{exported_name},Parcel3DNumber,-1,-1;' + \
                        fr'Parcel2DNumber "מספר חלקה קרקעית" true false false 0 Short 0 0,First,#,{exported_name},Parcel2DNumber,-1,-1;' + \
                        fr'BlockNumber "מספר גוש" true false false 0 Long 0 0,First,#,{exported_name},BlockNumber,-1,-1;' + \
                        fr'SubBlockNumber "מספר תת-גוש" true false false 0 Short 0 0,First,#,{exported_name},SubBlockNumber,-1,-1;' + \
                        fr'StatedVolume "נפח רשום במעוקב" true false false 0 Double 0 0,First,#,{exported_name},StatedVolume,-1,-1;' + \
                        fr'ProjectedArea "שטח היטל" true false false 0 Double 0 0,First,#,{exported_name},ProjectedArea,-1,-1;' + \
                        fr'UpperLevel "רום עליון" true false false 0 Double 0 0,First,#,{exported_name},UpperLevel,-1,-1;' + \
                        fr'LowerLevel "רום תחתון" true false false 0 Double 0 0,First,#,{exported_name},LowerLevel,-1,-1;' + \
                        fr'RelativePosition "מיקום גריעה ביחס לפני הקרקע" true false false 0 Short 0 0,First,#,{exported_name},RelativePosition,-1,-1;' + \
                        fr'SubstractionType "סוג גריעה" true false false 0 Short 0 0,First,#,{exported_name},SubstractionType,-1,-1;' + \
                        fr'BlockUniqueID "מזהה גוש" true true false 38 Guid 0 0,First,#,{exported_name},BlockUniqueID,-1,-1;' + \
                        fr'CreatedByRecord "מזהה תהליך יוצר" true true false 38 Guid 0 0,First,#,{exported_name},CreatedByRecord,-1,-1;' + \
                        fr'CreateProcessType "סוג תהליך יוצר" true false false 0 Short 0 0,First,#,{exported_name},CreateProcessType,-1,-1'

        Append(inputs=exported_name, target=get_layer('גריעות'), schema_type="NO_TEST", field_mapping=FieldMap, feature_service_mode="NO_FEATURE_SERVICE_MODE")


        del fields, info, exported_name, FieldMap

    del inprocess_substractions, query, count


def load_new_projected_substractions(ProcessName: str) -> None:
    """

    """

    AddMessage(f'\n ⭕ Adding new projections of substractions:')
    inprocess_substractions: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessSubstractions"
    inprocess_projected_substractions: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessProjectedSubstractions"

    # Count the new substractions from the process.
    new_substractions_guids: list[str] = [i[0] for i in SearchCursor(inprocess_substractions, "GlobalID", f"CPBUniqueID='{get_ProcessGUID(ProcessName)}' And Role=2")]
    count_new_substractions: int = len(new_substractions_guids)

    if count_new_substractions > 0:
        # Count the new substractions projections from the process (they should be equal to the count of new substractions).
        new_guids_str: str = ','.join(["'" + guid + "'" for guid in new_substractions_guids])
        query: str = f"SubstractionUniqueID IN ({new_guids_str})"
        count_new_projections: int = cursor_length(SearchCursor(inprocess_projected_substractions, "OBJECTID", query))

        if count_new_projections == count_new_substractions:
            AddMessage(f'{timestamp()} | ⚡ {count_new_projections} New substraction projections will be added')

            # Export inprocess substractions projections to home GDB
            new_substractions_guids: list[str] = []
            projections_export: str = fr"{ArcGISProject('current').defaultGeodatabase}\new_substractions_projections"
            FieldMap: str = fr'SubstractionUniqueID "מזהה גריעה" true true false 38 Guid 0 0,First,#,{inprocess_projected_substractions},SubstractionUniqueID,-1,-1;'
            new_projections: Result = ExportFeatures(inprocess_projected_substractions, projections_export, query, field_mapping= FieldMap)
            new_projections: Layer = MakeLayer(new_projections, "new_projections")[0]

            # Add GUID field of the new substractions in the exported feature class and compute it.
            AddField(new_projections, "FinalSubstractionGlobalID", "GUID", field_alias="מזהה גריעה סופית")

            inprocess_substractions: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessSubstractions"
            new_projections_cursor: Ucur = UpdateCursor(new_projections, ['SubstractionUniqueID', 'FinalSubstractionGlobalID'])

            for idx, row in enumerate(new_projections_cursor, start=1):
                final_substraction: list[int] = [[i[0], i[1], i[2]] for i in SearchCursor(inprocess_substractions, ['FinalSubstractionNumber', 'BlockNumber', 'SubBlockNumber'], f"GlobalID='{row[0]}'")][0]
                final_name: str = f"{final_substraction[0]}/{final_substraction[1]}/{final_substraction[2]}"
                final_guid_query: str = f"""SELECT TOP 1 GlobalID
                                            FROM PF.Substractions
                                            WHERE Name = '{final_name}' AND GDB_IS_DELETE = 0
                                            ORDER BY GDB_ARCHIVE_OID DESC"""
                final_guid_result: Table = MakeQueryLayer(CNFG.ParcelFabricDatabase, 'final_substraction_guid_result', final_guid_query)[0]
                final_substraction_guid: str = SearchCursor(final_guid_result, 'GlobalID').next()[0]
                row[1]: str = final_substraction_guid
                new_projections_cursor.updateRow(row)
                new_substractions_guids.append(final_substraction_guid)
                AddMessage(f'{timestamp()} | {idx}/{count_new_projections} | ✔️ Projection for parcel {final_substraction[0]} at block {final_substraction[1]}/{final_substraction[2]} added')

            FieldMap: str = fr'SubstractionUniqueID "מזהה גריעה" true true false 38 Guid 0 0,First,#,{projections_export},FinalSubstractionGlobalID,-1,-1;'
            projected_layer: Layer = get_layer('היטלי גריעות')
            Append(projections_export, projected_layer, "NO_TEST", FieldMap, feature_service_mode="USE_FEATURE_SERVICE_MODE")

            # Update the filter of active projected layer
            new_substractions: str = ', '.join(["'" + guid + "'" for guid in new_substractions_guids])

            aoi_blocks_layer: Layer = SelectByLocation(get_layer('גושים'), 'INTERSECT', get_layer('גבול תכנית'), "1 Meter")[0]
            aoi_blocks: Scur = SearchCursor(aoi_blocks_layer, 'GlobalID', "RetiredByRecord IS NULL")
            aoi_blocks: str = ', '.join(["'" + row[0] + "'" for row in aoi_blocks])
            ArcGISProject('current').activeMap.clearSelection()

            aoi_substractions: Scur = SearchCursor(get_layer('גריעות'), 'GlobalID', f"RetiredByRecord IS NULL AND BlockUniqueID IN ({aoi_blocks})")
            del aoi_blocks_layer, aoi_blocks

            if cursor_length(aoi_substractions) > 0:
                aoi_substractions: str = ', '.join(["'" + row[0] + "'" for row in aoi_substractions])
                sql: str = f"SubstractionUniqueID IN ({aoi_substractions},{new_substractions})"
            else:
                sql: str = f"SubstractionUniqueID IN ({new_substractions})"

            query_params: dict[str, Any] = {'name': 'Area of Interest', 'sql': sql, 'isActive': True}
            projected_layer.updateDefinitionQueries([query_params])

            del projections_export, FieldMap, new_projections, new_projections_cursor
        del new_guids_str, count_new_projections
    del inprocess_substractions, new_substractions_guids, inprocess_projected_substractions, count_new_substractions


def load_new_3D_points(ProcessName: str) -> None:
    """
    Load new 3D border points features into the active 3D border points layer.
    This function fetches new points data from the 'נקודות לשימור וחדשות' layer, compute additional necessary fields
    and appends it to the 'נקודות גבול תלת-ממדיות' layer in the current ArcGIS project Scene map.
    Note: The coordinate information (fields X, Y and Z) will compute automatically with Calculation Attribute Rules.

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
        active_3D_points: Icur = InsertCursor(get_layer('נקודות גבול תלת-ממדיות'),  data_fields + ['CreatedByRecord'])

        # Add the new point data
        for row in new_data:
            updated_row: tuple[Any] = row + (record_guid,)
            active_3D_points.insertRow(updated_row)

        del active_3D_points, record_guid
        AddMessage(f'{timestamp()} | ✔️ 3D points added successfully')

    else:
        AddMessage(f'{timestamp()} | ✔️ No new 3D points to add')

    del process_points_patch, data_fields, query, new_data, total


def start_task_RetireAndCreateCadaster3D(Independent: bool, ProcessName: str|None,) -> None:
    """
    Workflow for starting the Create And Retire Cadaster 3D task.

    Parameters:
        Independent (bool): An option to start the task environment for a different process than the one suggested by the APRX file. This option may be useful when the CMS is down. Default is False.
        ProcessName (str): The name of the cadaster process. This Parameter
    """

    set_priority()

    # Whether the process is executed from CMS or independent task.
    ProcessName: str = get_aprx_name() if not Independent else ProcessName

    qualified: bool = validation_set('RetireAndCreateCadaster3D', ProcessName)

    if qualified:

        create_shelf(ProcessName, True)  # Will skip if executed from CMS

        open_version(ProcessName)

        if creating_record_is_duplicated(ProcessName):
            update_record_status(ProcessName, new_status=5)  # מעדכן סטאטוס לרשומה
        else:
            load_to_records(ProcessName)

        display_process_data(ProcessName)

        activate_record(ProcessName)  # Known issue: The records layer is not updated until the end of the execution of GP tool.

        # Retire
        retire_3D_parcels_and_substractions(ProcessName)

        retire_3D_points(ProcessName)

        # Create
        load_new_3D_parcels(ProcessName)

        load_intermediate_3D_parcels(ProcessName)

        load_new_substractions(ProcessName)

        load_new_3D_points(ProcessName)

        load_new_projected_3D_parcels()

        load_intermediate_3D_parcels_projections()

        load_new_projected_substractions(ProcessName)

        # TODO: add modify_3D_preserved_points(?) for existing points (Role=3) to update their attributes.

        # Closers
        reopen_map()
        zoom_to_aoi()


if __name__ == "__main__":
    start_task_RetireAndCreateCadaster3D(Independent= GetParameter(0), ProcessName= GetParameterAsText(1))
