from pandas import DataFrame
from arcpy import GetParameter, GetParameterAsText, AddMessage, env as ENV
from arcpy.mp import ArcGISProject
from arcpy.da import SearchCursor
from arcpy.analysis import Buffer
from arcpy.parcel import ImportParcelFabricPoints
from arcpy.management import MakeFeatureLayer as MakeLayer
from Utils.Configs import CNFG
from Utils.TypeHints import Literal, Result, Layer, df
from Utils.Helpers import get_ActiveRecord, drop_layer, get_layer, AddTabularMessage, timestamp


def IPFP(source_points: Layer,
         distance: str = '1 Meters',
         update_mode: Literal["Update matched and create unmatched", "Only create unmatched", "Only update matched"] = 'Only update matched',
         update_type:  Literal["All Attributes", "Geometry (X, Y, Z)", "Retire & replace"] = 'All Attributes') -> None:

    """
    Import and update parcel fabric active points in the Parcel Fabric.
    This function uses `ImportParcelFabricPoints` GP tool to import or modify points from a source layer into the active points,
    updating matched points and/or creating unmatched points based on the specified mode.
    The results are processed and displayed in a tabular format in ArcGIS messages.
    If conflicts were found - a layer of a red buffered conflicts - rings, will be added to the map.
    the rings radius will be expressed by the same distance value set by the user.

    Parameters:
        source_points (Layer): The input point layer containing the points to be imported.
        distance (str, optional): The search distance (in map units) used to match source points with existing parcel points.
                                  Default is 1 meter.
        update_mode (Literal["Update matched and create unmatched", "Only create unmatched", "Only update matched"], optional):
            Determines how to handle matched and unmatched points:
            - "Update matched and create unmatched": Update matched points and create unmatched points.
            - "Only create unmatched": Only create unmatched points without updating existing points.
            - "Only update matched": Only update matched points without creating new ones.
            Default is 'Only update matched'.
        update_type (Literal["All Attributes", "Geometry (X, Y, Z)", "Retire & replace"], optional):
            Determines which attributes of matched points to update:
            - "All Attributes": Update all attributes.
            - "Geometry (X, Y, Z)": Update only the geometry (X, Y, Z) of points.
            - "Retire & replace": Retire existing points and replace them with the new points.
            Default is 'All Attributes'.
    """
    original_overwrite: bool = ENV.overwriteOutput
    update_mode_dict: dict[str, str] = {"Update matched and create unmatched": "UPDATE_AND_CREATE",
                                        "Only create unmatched": "CREATE_ONLY",
                                        "Only update matched": "UPDATE_ONLY"}


    update_type_dict: dict[str, str] = {"All Attributes": "ALL",
                                        "Geometry (X, Y, Z)": "GEOMETRY_XYZ",
                                        "Retire & replace": "RETIRE_AND_REPLACE"}


    record_name: str|None = get_ActiveRecord('Name')
    Mode: str  = update_mode_dict[update_mode]
    Type: str  = update_type_dict[update_type]

    if record_name and Mode and Type:
        ENV.overwriteOutput = True
        AddMessage('\n ⭕ Importing or modifying active points \n ')
        drop_layer('קונפליקטים')

        results: Result = ImportParcelFabricPoints(source_points= source_points,
                                                   target_parcel_fabric= get_layer('רישומים'),
                                                   match_point_method= "PROXIMITY",
                                                   search_distance= distance,
                                                   update_type= Type,
                                                   record_name= record_name,
                                                   match_field= None,
                                                   conflicts_table= 'ConflictsTable' if update_mode != "CREATE_ONLY" else None,
                                                   update_create_option= Mode,
                                                   target_points= get_layer('נקודות גבול') if update_mode != "CREATE_ONLY" else None,
                                                   where_clause= "RetiredByRecord IS NULL" if update_mode != "CREATE_ONLY" else "")


        # Report The results and check whether conflicts were found
        AddMessage(f'{timestamp()} | Review the results:')

        result_table: dict[str, int|str] = {}
        conflicts_count: int = 0
        fixed_shapes_points: bool = False

        for m in results.getAllMessages()[1:-1]:
            log_type: int = m[0]  # Massages are 0 and warnings are 50

            if log_type != 50:  # Massages
                key, value = m[2].rsplit(': ', 1)
                result_table[key]: int = value

            elif log_type == 50 and m[1] == 3027:  # Warning of Fixed-Shaped Points (Usually When Class is set as 1)
                fixed_shapes_points = True

            elif log_type == 50 and m[1] != 3027:
                conflicts_count += 1

        result_table: df = DataFrame({'Metric': 'Stats', **result_table}, index=[0])
        AddTabularMessage(result_table)

        # When there are active points with fixed-shape in the matching process.
        if fixed_shapes_points:
            AddMessage(f'{timestamp()} | ⚠️ Fixed-shape points were involved in the matching and cannot be move or update. Unfix these points to enable movement or updates.')

        # When conflicts are found, a buffered layer of the conflict points will be computed and added to the active map.
        if conflicts_count > 0:
            home_gdb: str = fr'{ArcGISProject("current").defaultGeodatabase}'
            conflicts_table: str = fr'{home_gdb}\ConflictsTable'
            conflicts_buffer: str = fr'{home_gdb}\Conflicts'

            conflicts_oid: str = ', '.join([str(row[0]) for row in SearchCursor(conflicts_table, 'SOURCE_OID')])

            ENV.addOutputsToMap = False
            conflicts_points: Layer = MakeLayer(source_points, 'conflicts', f"OBJECTID IN ({conflicts_oid})")[0]
            Buffer(conflicts_points, conflicts_buffer, distance)

            ENV.addOutputsToMap = True
            ArcGISProject("current").activeMap.addDataFromPath(fr'{CNFG.LayerFiles}Conflicts.lyrx')
            conflicts_layer: Layer = get_layer("קונפליקטים")
            new_connection: dict[str, str|dict[str, str]] = {'dataset': 'Conflicts',
                                                             'workspace_factory': 'File Geodatabase',
                                                             'connection_info': {'database': home_gdb}}
            conflicts_layer.updateConnectionProperties(None, new_connection)
            AddMessage(f'{timestamp()} | ⚠️ Conflicts within {distance.lower()} are displayed on the active map')


        del results, record_name, result_table, conflicts_count
        ENV.overwriteOutput = original_overwrite
        ENV.addOutputsToMap = False


if __name__ == '__main__':
    IPFP(source_points= GetParameter(0),
         distance= GetParameterAsText(1),
         update_mode= GetParameterAsText(2),
         update_type= GetParameterAsText(3))

