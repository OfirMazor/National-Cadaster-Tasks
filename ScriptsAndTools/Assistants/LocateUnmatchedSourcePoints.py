from set_path import add_parent_to_sys_path
add_parent_to_sys_path(__file__)

from Utils.Configs import CNFG
from Utils.TypeHints import Layer, Scur, Point, Map
from Utils.Helpers import get_layer, timestamp, drop_layer, AddDefinitionQuery
from arcpy import AddMessage, GetParameter
from arcpy.da import SearchCursor
from arcpy.mp import ArcGISProject


def locate_unmatched_source_points(source_points_layer: Layer) -> None:
    """
    Identifies source points that are not (yet) matched with the active points.
    If unmatched points are found, adds a visualization layer ('נקודות לא מתואמות')
    to the active map and applies a definition query filtering for those specific Object IDs.

    Parameters
        source_points_layer (Layer): The source point layer to check against active points.
    """

    AddMessage(f'\n{timestamp()} | Tracking for unmatched source points')

    drop_layer('נקודות לא מתואמות')
    total_unmatched: int = 0
    unmatched_OIDs: list[str] = []

    active_points: list[Point] = [shape[0] for shape in SearchCursor(get_layer('נקודות גבול'), 'Shape')]

    source_points_coord: Scur = SearchCursor(source_points_layer, ['ObjectID', 'Shape'])

    for point in source_points_coord:
        if point[1] not in active_points:
            unmatched_OIDs.append(point[0])
            total_unmatched += 1

    del source_points_coord, active_points

    if total_unmatched > 0:
        # Add an output layer to the active map
        active_map: Map = ArcGISProject('current').activeMap
        active_map.addDataFromPath(f"{CNFG.LayerFiles}UnmatchedPoints_{CNFG.Environment}.lyrx")
        layer: Layer = get_layer("נקודות לא מתואמות")
        active_map.moveLayer(get_layer("בקרת איכות"), layer, "BEFORE")

        query_params: dict[str, str|bool] = {'name': 'UnmatchedSourcePoints', 'sql': f"OBJECTID IN ({','.join([str(i) for i in unmatched_OIDs])})", 'isActive': True}
        AddDefinitionQuery(layer, query_params)
        AddMessage(f"{timestamp()} | 💡 {total_unmatched} Unmatched points from the process are displayed on the map")

    else:
        AddMessage(f"{timestamp()} | ✅ All source points are matched with the active points")


if __name__ == "__main__":
    locate_unmatched_source_points(source_points_layer= GetParameter(0))
