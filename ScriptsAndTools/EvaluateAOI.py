from Utils.TypeHints import Literal, Optional, Extent
from Utils.Helpers import get_LayerExtent, zoom_to_layer, get_ActiveRecord, timestamp
from Utils.QA import track_deviated_parcel_areas, track_adjacent_points, track_gaps_overlaps, track_disconnected_points, eval_topology_rules, eval_validation_rules
from arcpy import AddMessage, env as ENV, GetParameter, GetParameterAsText
from arcpy.mp import ArcGISProject


def EvaluateAOI(qa_extent: Literal['Full map', 'Record', 'Current display'] = 'Full',
                validate_validation: Optional[bool] = True,
                validate_topology: Optional[bool] = True,
                validate_gaps_overlaps: Optional[bool] = True,
                max_width: Optional[float] = 2.0,
                validate_adjacent_points: Optional[bool] = True,
                tolerance: Optional[float] = 0.1,
                validate_disconnected_points: Optional[bool] = True,
                validate_deviated_areas: Optional[bool] = True) -> None:
    """
    Performs quality assurance (QA) checks on parcel fabric data within the area of interest (AOI).
    The function validates topology rules, detects gaps and overlaps between parcels and identifies adjacent parcel points.
    The results help ensure the integrity of the parcel fabric dataset in the AOI after being edited.

    Parameters:
        qa_extent (Literal['Full Map', 'Record', 'Current display']): Map extent for QA checks.
                                                                      'Full Map' validates the entire map area.
                                                                      'Record' validates features inside and near the record border.
                                                                      'Current display' validates features inside current map display.
                                                                      Default is 'Full Map'.

        validate_validation (bool, optional): If True, evaluate validation rules. Defaults to True.

        validate_topology (bool, optional): If True, validates topology rules. Defaults to True.

        validate_gaps_overlaps (bool, optional): If True, detects gaps and overlaps between parcel features. Defaults to True.

        max_width (float, optional): The maximum width a gap or an overlap can be for it to be considered a gap or
                                     an overlap. Only gaps and overlaps that are smaller than the specified width
                                     will be included in the output feature class.
                                     The default width is 2 meters.

        validate_adjacent_points (bool, optional): If True, identifies adjacent parcel points. Defaults to True.

        tolerance (float, optional): The distance within which a point is considered adjacent to another point.
                                     If a point is closer to another point than the specified tolerance, the point will
                                     be considered an adjacent point and will be copied to the output feature class.
                                     The default tolerance of 0.1 meters will find stacked points that lie directly on
                                     top of each other or within 10 centimeters from each other.

        validate_disconnected_points: If True, identifies disconnected active points. Defaults to True.

        validate_deviated_areas (bool, optional): If True, calculates the deviations areas for ant parcel in the AOI. Defaults to True.
    """
    original_overwrite: bool = ENV.overwriteOutput
    original_extent: str|Extent|None = ENV.extent

    if get_ActiveRecord():

        AddMessage('\n ⭕ Evaluating edits in area of interest')

        # modify environment settings:
        ENV.overwriteOutput = True
        if qa_extent == 'Full map':
            zoom_to_layer('גושים')
            ENV.extent = get_LayerExtent('גושים')
        if qa_extent == 'Record':
            zoom_to_layer('גבול תכנית')
            ENV.extent = get_LayerExtent('גבול תכנית')
        if qa_extent == 'Current display':
            ENV.extent = ArcGISProject("current").activeView.camera.getExtent()


        # Evaluations:
        if validate_validation:
            pass
            AddMessage(f"{timestamp()} | ⚠️ Currently evaluate validations rules is not available, use the Error Inspector to evaluate")
            # eval_validation_rules()

        if validate_topology:
            eval_topology_rules()

        if validate_gaps_overlaps:
            track_gaps_overlaps(max_width)

        if validate_adjacent_points:
            track_adjacent_points(tolerance)

        if validate_disconnected_points:
            track_disconnected_points()

        if validate_deviated_areas:
            track_deviated_parcel_areas()

        # Return to original environment settings:
        ENV.extent = original_extent
        ENV.overwriteOutput = original_overwrite
        del original_extent, original_overwrite


if __name__ == "__main__":

    EvaluateAOI(qa_extent= GetParameterAsText(0),
                validate_validation= GetParameter(1),
                validate_topology= GetParameter(2),
                validate_gaps_overlaps= GetParameter(3),
                max_width= GetParameter(4),
                validate_adjacent_points= GetParameter(5),
                tolerance= GetParameter(6),
                validate_disconnected_points= GetParameter(7),
                validate_deviated_areas= GetParameter(8))
