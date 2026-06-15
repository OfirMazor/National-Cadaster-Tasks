import numpy as np
from pandas import DataFrame
from Utils.TypeHints import *
from Utils.Configs import CNFG
from Utils.VersionManagement import get_VersionName
from Utils.Helpers import get_layer, timestamp, drop_layer, AddTabularMessage, get_display_extent, get_table, \
                          refresh_map_view, activate_extension
from arcpy import AddMessage, AddError, Exists, EnvManager, env as ENV, Array, Polygon, Point, SpatialReference
from arcpy.mp import ArcGISProject
from arcpy.conversion import ExportFeatures
from arcpy.da import SearchCursor, InsertCursor
from arcpy.ddd import Intersect3D, AddZInformation
from arcpy.parcel import FindGapsAndOverlaps, FindAdjacentParcelPoints, FindDisconnectedParcelPoints
from arcpy.management import Copy, Delete, ValidateTopology, EvaluateRules, SelectLayerByLocation as SelectByLocation, \
                             FeatureVerticesToPoints, MakeFeatureLayer, GetCount


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
        layer.updateConnectionProperties(None, output)
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

    # Report the results if there are any errors found
    if total_errors > 0:
        errors_table: df = DataFrame(data= {"Metric": "Count",
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
        layer.updateConnectionProperties(None, output)

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
        layer.updateConnectionProperties(None, output)
    else:
        AddMessage(f"{timestamp()} | ✅ No disconnected points were found")

    del output, results
    ArcGISProject('current').activeMap.clearSelection()


def track_redundant_vertices() -> None:
    """
    Identifies and extracts redundant vertices from active layers within the given display extent.

    A vertex is considered "redundant" if it exists in the target layers ('גושים', 'חלקות', 'חזיתות')
    but does not spatially intersect with the active border point ('נקודת גבול').

    If redundant vertices are found, they are saved to a 'RedundantVertices' feature class in the
    project's default geodatabase. A summary table is then logged to the geoprocessing messages, and
    a configured layer ('נקודות מפנה מיותרות') is added to the active map.

    Reference:
        https://pro.arcgis.com/en/pro-app/latest/tool-reference/data-management/feature-vertices-to-points.htm

    Note:
        1) The Feature Vertices to Point GP tool requires ArcGIS Pro's Advanced licensing.
        2) To avoid crashes in ArcGIS Pro The active fronts layer is been queried from the feature server with the
        MakeFeature function (specifying the current branch version info) instead of the direct active fronts layer
        from the current ArcGIS Project ('חזיתות').
        Assuming the "Area of Interest" definition query in that layer is leading to the program crash.
        Changing the definition query of the current layer were not helpful.

    """
    AddMessage(f'\n{timestamp()} | Tracking for redundant vertices')

    project: Pro = ArcGISProject('current')
    active_map: Map = project.activeMap
    active_map.clearSelection()
    home_gdb: str = project.defaultGeodatabase
    output: str = fr'{home_gdb}\RedundantVertices'

    if Exists(output):
        Delete(output)
    drop_layer('נקודות מפנה מיותרות')

    redundant_data: list[tuple[str, Point] | None] = []

    summary: dict[str, int] = {'גושים': 0, 'חלקות': 0, 'חזיתות': 0}

    active_border_points: Layer = get_layer('נקודות גבול')

    # Select the features in the chosen extent
    extent: Extent = get_display_extent()
    extent: Polygon = Polygon(Array([Point(extent.XMin, extent.YMin),
                                     Point(extent.XMin, extent.YMax),
                                     Point(extent.XMax, extent.YMax),
                                     Point(extent.XMax, extent.YMin)]),
                              SpatialReference(2039))

    for layer_name in summary.keys():
        if layer_name != 'חזיתות':
            layer: Layer = get_layer(layer_name)
        else:
            # To avoid crash (Note #2)
            layer: Layer = MakeFeatureLayer(fr"{CNFG.ParcelFabricFeatureServer};version={get_VersionName('חזיתות')}/14", 'temp', 'RetiredByRecord IS NULL')[0]

        # Select the features of a layer in the given extent
        features: Layer = SelectByLocation(layer, select_features=extent)[0]

        # Compute all the vertices of the selected features in the layer
        vertices: str = FeatureVerticesToPoints(features, r'memory\Vertices', "ALL")[0]
        vertices: Layer = MakeFeatureLayer(vertices, 'Vertices')[0]
        active_map.clearSelection()
        del features, layer

        # Exclude essential vertices from the results
        redundant: Result = SelectByLocation(vertices, 'ARE_IDENTICAL_TO', active_border_points, invert_spatial_relationship= "INVERT")

        # Collect information if redundant vertices were found in a layer
        if int(redundant[2]) > 0:
            export: str = ExportFeatures(redundant[0], fr"{home_gdb}/redundant_{layer_name}")[0]
            summary[layer_name]: int = int(GetCount(export)[0])
            redundant_data.extend([(f"{layer_name}", row[0]) for row in SearchCursor(export, 'Shape@')])
            Delete(export)

        del redundant
        active_map.clearSelection()

    del active_border_points, extent

    # Report actions if any redundant were found
    if len(redundant_data) > 0:
        # copy an empty template feature class
        Copy(fr'{CNFG.TemplatesPath}Templates.gdb\RedundantVertices', output)

        # Load the vertices data to the template feature class
        insert: Icur = InsertCursor(output, ['ReferencedLayer', 'Shape@'])
        for vertex in redundant_data:
            insert.insertRow(vertex)

        # Log a tabular summary message
        errors_table: df = DataFrame(data= {"Layer": "Redundant Vertices Count",
                                            "גושים": summary['גושים'],
                                            "חלקות": summary['חלקות'],
                                            "חזיתות": summary['חזיתות']}, index= [0])
        AddTabularMessage(errors_table)

        # Add the redundant layer with connection to the collected data
        active_map.addDataFromPath(fr'{CNFG.LayerFiles}RedundantVertices.lyrx')
        layer: Layer = get_layer("נקודות מפנה מיותרות")
        active_map.moveLayer(get_layer("אימות נתונים"), layer, "BEFORE")
        active_map.clearSelection()
        refresh_map_view()
        layer.updateConnectionProperties(None, output)

        del insert, errors_table, active_map, layer

    else:
        AddMessage(f"{timestamp()} | ✅ No redundant vertices were found")


def track_volumetric_overlaps() -> None:
    """
    Computes the intersection of active 3D parcels and active substractions multipatch features to produce closed
    multipatches encompassing the overlapping volumes.

    Reference:
        https://pro.arcgis.com/en/pro-app/latest/tool-reference/3d-analyst/intersect-3d-3d-analyst-.htm
    """
    AddMessage(f'\n{timestamp()} | Tracking for volumetric overlaps between active 3D parcels and substractions')

    # The Intersect3D and the AddZInformation GP tools requires the 3D Analyst extension
    if activate_extension("3D"):

        # Configurations variables
        home_gdb: str = fr"{ArcGISProject('current').defaultGeodatabase}"

        parcels3D_FM: str = fr'ParcelNumber "מספר חלקה" true true false 0 Short 0 0,First,#,רצף קדסטרי\חלקות תלת-ממדיות,ParcelNumber,-1,-1;' + \
                            fr'BlockNumber "מספר גוש" true true false 0 Long 0 0,First,#,רצף קדסטרי\חלקות תלת-ממדיות,BlockNumber,-1,-1;' + \
                            fr'SubBlockNumber "מספר תת-גוש" true true false 0 Short 0 0,First,#,רצף קדסטרי\חלקות תלת-ממדיות,SubBlockNumber,-1,-1;'

        substractions_FM: str = fr'SubstractionNumber "מספר גריעה" true true false 0 Short 0 0,First,#,רצף קדסטרי\גריעות,SubstractionNumber,-1,-1;' + \
                                fr'BlockNumber "מספר גוש" true true false 0 Long 0 0,First,#,רצף קדסטרי\גריעות,BlockNumber,-1,-1;' + \
                                fr'SubBlockNumber "מספר תת-גוש" true true false 0 Short 0 0,First,#,רצף קדסטרי\גריעות,SubBlockNumber,-1,-1'

        params: DataFrame = DataFrame(data= {'source_layer_name': ['חלקות תלת-ממדיות', 'גריעות'],
                                             'results_fc': [fr"{home_gdb}/Parcels3DOverlaps", fr"{home_gdb}/SubstractionsOverlaps"],
                                             'results_layer_name': ['חפיפות בין חלקות תלת-ממדיות', 'חפיפות בין גריעות'],
                                             'results_layer_file': [fr'{CNFG.LayerFiles}Parcels3DOverlaps.lyrx', fr'{CNFG.LayerFiles}SubstractionsOverlaps.lyrx'],
                                             'field_map': [parcels3D_FM, substractions_FM],
                                             'overlap_count': [0, 0]})


        # Iterate the params DataFrame and calculate overlaps
        for idx, source in params.iterrows():

            drop_layer(source['results_layer_name'])

            # The export of multipatch is vital since the Intersect3D tool encounter a BUG error when a feature class contains GlobalID Field.
            # Note: When no overlaps found - the output feature class of Intersect3D will not be created (instead of creating empty feature class)
            export: str = ExportFeatures(get_layer(source['source_layer_name']), r'memory\export', field_mapping= source['field_map'])[0]
            Intersect3D(export, source['results_fc'], output_geometry_type= "SOLID")
            del export

            if Exists(source['results_fc']):
                # Calculate the volume of the overlaps found
                AddZInformation(source['results_fc'], ["VOLUME"])

                # update the params with the total overlaps found for the source
                params.at[idx, 'overlap_count']: int = int(GetCount(source['results_fc'])[0])

                # Add the resulting overlaps to the map
                active_map: Map = ArcGISProject('current').activeMap
                active_map.addDataFromPath(source['results_layer_file'])
                overlay_layer: Layer = get_layer(source['results_layer_name'])
                overlay_layer.updateConnectionProperties(None, source['results_fc'])
                active_map.moveLayer(get_layer("אימות נתונים"), overlay_layer, "BEFORE")
                del active_map, overlay_layer


        # Message the results
        count_parcels3D_overlaps: int = params['overlap_count'].iloc[0]
        count_substractions_overlaps: int = params['overlap_count'].iloc[1]
        total_overlaps: int = params['overlap_count'].sum()

        del params, home_gdb, parcels3D_FM, substractions_FM

        if total_overlaps > 0:
            errors_table: df = DataFrame(data={"Metric": "Count",
                                               f"{'❌' if count_parcels3D_overlaps > 0 else '✅'} | Volumetric overlaps between 3D parcels": count_parcels3D_overlaps,
                                               f"{'❌' if count_substractions_overlaps > 0 else '✅'} | Volumetric overlaps between substractions": count_substractions_overlaps},
                                         index=[0])
            AddTabularMessage(errors_table)
        else:
            AddMessage(f"{timestamp()} | ✅ No volumetric overlaps were found")


    else:
        AddError(f"{timestamp()} | ❌ Activate the 3D Analyst extension before tracking for volumetric overlaps.")
