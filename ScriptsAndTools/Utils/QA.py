import numpy as np
from pandas import DataFrame
from Utils.TypeHints import *
from Utils.Configs import CNFG
from Utils.VersionManagement import get_VersionName
from Utils.Helpers import get_layer, timestamp, drop_layer, AddTabularMessage, get_display_extent, get_table
from arcpy import AddMessage, Exists, EnvManager, env as ENV, Array, Polygon, Point, SpatialReference
from arcpy.mp import ArcGISProject
from arcpy.conversion import ExportFeatures
from arcpy.da import SearchCursor, InsertCursor
from arcpy.parcel import FindGapsAndOverlaps, FindAdjacentParcelPoints, FindDisconnectedParcelPoints
from arcpy.management import Copy, Delete, ValidateTopology, EvaluateRules, GetCount, SelectLayerByLocation as SelectByLocation


def eval_validation_rules() -> None:
    """
    Evaluate the validation attribute rules.

    Reference:
        https://pro.arcgis.com/en/pro-app/latest/tool-reference/data-management/evaluate-rules.htm
    """
    AddMessage(f'\n{timestamp()} | Evaluating attribute rules')
    workspace: str = fr"{CNFG.ParcelFabricFeatureServer};version={get_VersionName('רישומים')}"
    EvaluateRules(workspace, ['VALIDATION_RULES'], ENV.extent, 'ASYNC')

    polygon_errors_count: int = int(GetCount(get_layer('שטחי אימות')).getOutput(0))
    line_errors_count: int = int(GetCount(get_layer('קווי אימות')).getOutput(0))
    point_errors_count: int = int(GetCount(get_layer('נקודות אימות')).getOutput(0))

    total: int = polygon_errors_count + line_errors_count + point_errors_count
    if total > 0:
        AddMessage(f"{timestamp()} | ❌ Found {total} violated attribute rules \n ")
        errors_df: df = DataFrame(data= {"Metric": "Count",
                                         f"{'❌' if polygon_errors_count > 0 else '✅'} | Polygon Errors": polygon_errors_count,
                                         f"{'❌' if line_errors_count > 0 else '✅'} | Line Errors": line_errors_count,
                                         f"{'❌' if point_errors_count > 0 else '✅'} | Point Errors": point_errors_count},
                                  index= [0])
        AddTabularMessage(errors_df)

    else:
        AddMessage(f"{timestamp()} | ✅ Attribute rules were not violated")


def eval_topology_rules() -> None:
    """
    Validate the topology rules.

    Reference:
        https://pro.arcgis.com/en/pro-app/latest/tool-reference/data-management/validate-topology.htm
    """
    AddMessage(f'\n{timestamp()} | Evaluating topology rules')

    with EnvManager(extent= get_display_extent()):
        ValidateTopology(get_layer('טופולוגיה'), "Visible_Extent")

    polygon_errors_count: int = int(GetCount(get_layer('שגיאות מסוג פוליגון')).getOutput(0))
    line_errors_count: int = int(GetCount(get_layer('שגיאות מסוג קו')).getOutput(0))
    point_errors_count: int = int(GetCount(get_layer('שגיאות מסוג נקודה')).getOutput(0))

    total: int = polygon_errors_count + line_errors_count + point_errors_count
    if total > 0:
        AddMessage(f"{timestamp()} | ❌ Found {total} violated topology rules \n ")
        errors_df: df = DataFrame(data= {"Metric": "Count",
                                         f"{'❌' if polygon_errors_count > 0 else '✅'} | Polygon Errors": polygon_errors_count,
                                         f"{'❌' if line_errors_count > 0 else '✅'} | Line Errors": line_errors_count,
                                         f"{'❌' if point_errors_count > 0 else '✅'} | Point Errors": point_errors_count},
                                     index= [0])
        AddTabularMessage(errors_df)

    else:
        AddMessage(f"{timestamp()} | ✅ Topology rules were not violated")


def track_deviated_parcel_areas() -> None:
    """
    Identifies parcels with deviated registered areas.
    This function compares the stated area of parcels with their calculated shape area.
    It determines deviations based on a normalized threshold and categorizes parcels as either "Valid" or "Invalid".
    If any parcels have deviated areas, the results are stored in the home geodatabase as DB table and added to the ArcGIS current map for quality control.
    """
    AddMessage(f'\n{timestamp()} | Calculating deviations of parcels areas')

    # Clear previews results if exists
    to_drop: list[Table] = ArcGISProject('current').activeMap.listTables('חלקות עם שטחים חורגים')
    if len(to_drop) > 0:
        for t in to_drop:
            ArcGISProject('current').activeMap.removeTable(t)

    results_path: str = fr'{ArcGISProject("current").defaultGeodatabase}\DeviatedAreaParcels'
    if Exists(results_path):
        Delete(results_path)

    schema: dict[str, type] = {'GlobalID': str, 'ParcelNumber': 'Int32', 'BlockNumber': 'Int32', 'SubBlockNumber': 'Int8',
                               'StatedArea': float, 'Shape__Area': float}
    cols: list[str] = list(schema.keys())

    extent: Extent = get_display_extent()
    extent_polygon: Polygon = Polygon(Array([Point(extent.XMin, extent.YMin), Point(extent.XMin, extent.YMax),
                                             Point(extent.XMax, extent.YMax), Point(extent.XMax, extent.YMin)]),
                                      SpatialReference(2039))

    selected_parcels: Layer = SelectByLocation(in_layer=get_layer("חלקות"), select_features=extent_polygon).getOutput(0)

    search: Scur = SearchCursor(selected_parcels, cols)
    data: df = DataFrame(search, columns= cols).astype(schema).sort_values(['BlockNumber', 'SubBlockNumber', 'ParcelNumber'])
    del search, schema, selected_parcels, extent_polygon, extent
    ArcGISProject('current').activeMap.clearSelection()

    data['AbsDifference'] = abs(data['StatedArea'] - data['Shape__Area'])
    data['NormalizedStatedArea1'] = 0.3 * np.sqrt(data['StatedArea']) + 0.005 * data['StatedArea']
    data['NormalizedStatedArea2'] = 0.8 * np.sqrt(data['StatedArea']) + 0.002 * data['StatedArea']
    data['MaxNormalizedStatedArea'] = data[['NormalizedStatedArea1', 'NormalizedStatedArea2']].max(axis=1)
    data['Validation'] = np.where(data['MaxNormalizedStatedArea'] > data['AbsDifference'], 'Valid', 'Invalid')

    data: df = data.query("Validation == 'Invalid'").drop(columns='Validation').rename(columns = {'Shape__Area': 'CalculatedArea'})

    count: int = len(data)

    if count > 0:
        AddMessage(f'{timestamp()} | ❌ Found {count} parcels with deviated areas')
        Copy(fr'{CNFG.TemplatesPath}Templates.gdb\DeviatedAreaParcels', results_path)
        cols: list[str] = ['Parcel2DUniqueID'] + list(data.keys())[1:]
        results: Icur = InsertCursor(results_path, cols)
        for row in data.itertuples(index=False, name=None):
            results.insertRow(row)

        del cols, results


        ArcGISProject('current').activeMap.addDataFromPath(results_path)
        ArcGISProject('current').activeMap.addTableToGroup(get_layer("בקרת איכות"), get_table('חלקות עם שטחים חורגים'))
        to_drop: list[Table] = ArcGISProject('current').activeMap.listTables('חלקות עם שטחים חורגים')
        if len(to_drop) > 1:
            ArcGISProject('current').activeMap.removeTable(to_drop[-1])

        # del results_table

    else:
        AddMessage(f'{timestamp()} | ✅ No deviation in parcels areas were found')

    del data, count


def track_adjacent_points(tolerance: Optional[float|int] = 0.1) -> None:
    """
    Identifies and tracks adjacent current points by using a specified tolerance distance threshold.

    parameters:
        tolerance (float): The distance for the search radius of each current point. Default is 0.1 meters.

    Reference:
        https://pro.arcgis.com/en/pro-app/latest/tool-reference/parcel/find-adjacent-parcel-points.htm
    """
    AddMessage(f'\n{timestamp()} | Tracking for adjacent active points')

    home_gdb: str = ArcGISProject("current").defaultGeodatabase
    output: str = fr'{home_gdb}\AdjacentPoints'
    drop_layer('נקודות סמוכות')

    results: Result = FindAdjacentParcelPoints(get_layer("נקודות גבול"), out_feature_class= output, tolerance= tolerance)
    results: int = int(results.getMessage(2).split(' ')[-1])  # The count of errors detected

    if results > 0:
        AddMessage(f"{timestamp()} | ❌ Found {results} adjacent points")
        current_map: Map = ArcGISProject('current').activeMap
        current_map.addDataFromPath(fr'{CNFG.LayerFiles}AdjacentPoints.lyrx')
        layer: Layer = get_layer('נקודות סמוכות')
        new_connection: dict[str, dict[str, str]] = {'dataset': 'AdjacentPoints', 'workspace_factory': 'File Geodatabase', 'connection_info': {'database': home_gdb}}
        layer.updateConnectionProperties(None, new_connection)
        current_map.moveLayer(get_layer("אימות נתונים"), get_layer("נקודות סמוכות"), "BEFORE")
    else:
        AddMessage(f"{timestamp()} | ✅ No adjacent points were found")

    ArcGISProject('current').activeMap.clearSelection()
    del results, output


def track_gaps_overlaps(max_width: Optional[float|int] = 2.0) -> None:
    """
    Identifies and tracks gaps and overlaps between current parcel and current blocks layers in an ArcGIS project by
    using a specified maximum width threshold.

    parameters:
        max_width (float): The maximum width threshold in meters for detecting gaps and overlaps. Default is 2 meters.

    Reference:
        https://pro.arcgis.com/en/pro-app/latest/tool-reference/parcel/find-gaps-and-overlaps.htm
    """
    AddMessage(f'\n{timestamp()} | Tracking for gaps & overlaps between active parcels and blocks')

    home_gdb: str = ArcGISProject("current").defaultGeodatabase
    output: str = fr'{home_gdb}\GapsAndOverlaps'
    drop_layer('חורים וחפיפות')

    # Select the features in the chosen extent
    extent: Extent = get_display_extent()
    extent_polygon = Polygon(Array([Point(extent.XMin, extent.YMin), Point(extent.XMin, extent.YMax),
                                    Point(extent.XMax, extent.YMax), Point(extent.XMax, extent.YMin)]),
                             SpatialReference(2039))

    parcels: Layer = SelectByLocation(in_layer=get_layer("חלקות"), select_features=extent_polygon).getOutput(0)
    blocks: Layer = SelectByLocation(in_layer=get_layer("גושים"), select_features=extent_polygon).getOutput(0)

    # Find the gaps and overlaps between active parcels and active blocks
    results: Result = FindGapsAndOverlaps(in_parcel_features= [parcels, blocks], out_feature_class= output, maximum_width= max_width, detection_type= "WITHIN_LAYER")

    gaps_between_parcels: int = int(results.getAllMessages()[-3][-1].split(' ')[-1])
    gaps_between_blocks: int = int(results.getAllMessages()[3][-1].split(' ')[-1])
    total_gaps: int = gaps_between_parcels + gaps_between_blocks

    overlaps_between_parcels: int = int(results.getAllMessages()[4][-1].split(' ')[-1])
    overlaps_between_blocks: int = int(results.getAllMessages()[-2][-1].split(' ')[-1])
    total_overlaps: int = overlaps_between_parcels + overlaps_between_blocks

    total_errors: int = total_gaps + total_overlaps

    # Report the results if there are any errors fond
    if total_errors > 0:
        errors_table: df = DataFrame({"Metric": "Count",
                                      f"{'❌' if gaps_between_parcels > 0 else '✅'} | Gaps between parcels": gaps_between_parcels,
                                      f"{'❌' if gaps_between_blocks > 0 else '✅'} | Gaps between blocks": gaps_between_blocks,
                                      f"{'❌' if overlaps_between_parcels > 0 else '✅'} | Overlaps between parcels": overlaps_between_parcels,
                                      f"{'❌' if overlaps_between_blocks > 0 else '✅'} | Overlaps between blocks": overlaps_between_blocks},
                                        index = [0])
        AddTabularMessage(errors_table)

        current_map: Map = ArcGISProject('current').activeMap
        current_map.addDataFromPath(fr'{CNFG.LayerFiles}GapsAndOverlaps.lyrx')
        layer: Layer = get_layer("חורים וחפיפות")
        current_map.moveLayer(get_layer("אימות נתונים"), layer, "BEFORE")

        new_connection: dict[str, dict[str, str]] = {'dataset': 'GapsAndOverlaps', 'workspace_factory': 'File Geodatabase', 'connection_info': {'database': home_gdb}}
        layer.updateConnectionProperties(None, new_connection)

    else:
        AddMessage(f"{timestamp()} | ✅ No gaps or overlaps were found")

    ArcGISProject('current').activeMap.clearSelection()
    del output, parcels, blocks, extent_polygon, extent, results


def track_disconnected_points() -> None:
    """
    Identifies and tracks disconnected active points in the area of interest.

    Reference:
        https://pro.arcgis.com/en/pro-app/latest/tool-reference/parcel/find-disconnected-parcel-points.htm
    """
    AddMessage(f'\n{timestamp()} | Tracking for disconnected active points')

    home_gdb: str = ArcGISProject("current").defaultGeodatabase
    output: str = fr'{home_gdb}\DisconnectedPoints'
    drop_layer('נקודות מנותקות')

    results: Result = FindDisconnectedParcelPoints(get_layer("נקודות גבול"), output, consider_edge= 'CONSIDER_EDGE')
    results: int = int(results.getMessage(2)[-1].split(' ')[-1])

    if results > 0:
        AddMessage(f"{timestamp()} | ❌ Found {results} disconnected points")
        current_map: Map = ArcGISProject('current').activeMap
        current_map.addDataFromPath(fr'{CNFG.LayerFiles}DisconnectedPoints.lyrx')
        layer: Layer = get_layer("נקודות מנותקות")
        current_map.moveLayer(get_layer("אימות נתונים"), layer, "BEFORE")

        new_connection: dict[str, dict[str, str]] = {'dataset': 'DisconnectedPoints', 'workspace_factory': 'File Geodatabase', 'connection_info': {'database': home_gdb}}
        layer.updateConnectionProperties(None, new_connection)
    else:
        AddMessage(f"{timestamp()} | ✅ No disconnected points were found")

    del output, results
    ArcGISProject('current').activeMap.clearSelection()


def track_volumetric_overlaps() -> None:
    """
    Computes the intersection of multipatch features to produce closed multipatches encompassing the overlapping volumes,
    open multipatch features from the common surface areas, or lines from the intersecting edges.

    Reference:
        https://pro.arcgis.com/en/pro-app/latest/tool-reference/3d-analyst/intersect-3d-3d-analyst-.htm
    """

    from arcpy import CheckExtension
    from arcpy.ddd import Intersect3D

    if CheckExtension("3D") == "Available":
        # TODO: export a copy of the multipatch layer excluding the GlobalID field. Reference: Case 04043897 .

        Parcels3D: Layer = get_layer('חלקות תלת-ממדיות')
        ExportFeatures(get_layer('חלקות תלת-ממדיות'), r'memory/Parcels3D', field_mapping= fr'')
        parcels_overlays: str = fr"{ArcGISProject('current').defaultGeodatabase}/parcels_overlays"
        Intersect3D(in_feature_class_1= Parcels3D, out_feature_class= parcels_overlays, output_geometry_type= "SOLID")
        total_parcels_overlaps: int = 0

        Substractions: Layer = get_layer('גריעות')
        substractions_overlays: str = fr"{ArcGISProject('current').defaultGeodatabase}/substractions_overlays"
        Intersect3D(in_feature_class_1= Substractions, out_feature_class= substractions_overlays, output_geometry_type="SOLID")
        total_substractions_overlaps: int = 0

        total_errors: int = total_substractions_overlaps + total_parcels_overlaps

        # Report the results if there are any errors fond
        if total_errors > 0:
            errors_table: df = DataFrame(data= {"Metric": "Count",
                                                f"{'❌' if total_parcels_overlaps > 0 else '✅'} | Overlaps between 3D parcels": total_parcels_overlaps,
                                                f"{'❌' if total_substractions_overlaps > 0 else '✅'} | Overlaps between substractions": total_substractions_overlaps},
                                         index=[0])
            AddTabularMessage(errors_table)

            current_map: Map = ArcGISProject('current').activeMap

            if total_parcels_overlaps > 0:
                current_map.addDataFromPath(fr'{CNFG.LayerFiles}Overlaps3DParcels.lyrx')
                parcels_overlays_layer: Layer = get_layer("חפיפות בין חלקות תלת-ממדיות")
                new_connection: dict[str, Any] = {'dataset': 'parcels_overlays', 'workspace_factory': 'File Geodatabase', 'connection_info': {'database': parcels_overlays}}
                parcels_overlays_layer.updateConnectionProperties(None, new_connection)

            if total_substractions_overlaps > 0:
                current_map.addDataFromPath(fr'{CNFG.LayerFiles}OverlapsSubstractions.lyrx')
                substractions_overlaps_layer: Layer = get_layer("חפיפות בין גריעות")
                new_connection: dict[str, Any] = {'dataset': 'substractions_overlays', 'workspace_factory': 'File Geodatabase', 'connection_info': {'database': substractions_overlays}}
                substractions_overlaps_layer.updateConnectionProperties(None, new_connection)

        del Parcels3D, parcels_overlays, total_parcels_overlaps, Substractions, substractions_overlays, total_substractions_overlaps, total_errors

    else:
        AddMessage(f"{timestamp()} | ❌ Activate the 3D Analyst extension before tracking volumetric overlaps.")
