from Utils.TypeHints import *
from Utils.VersionManagement import layer_is_at_version
from Utils.Helpers import get_RecordGUID, get_ActiveRecord, refresh_map_view, timestamp, get_layer
from arcpy import GetParameter, GetParameterAsText, AddMessage, AddError, RefreshLayer
from arcpy.management import CalculateField


def retire_features(input_layer: Literal['נקודות גבול', 'נקודות גבול תלת-ממדיות', 'חזיתות'], record_name: Optional[str]) -> None:
    """
    Retiring active features (fronts or points) in a Parcel Fabric layer by associating them with a retirement record.

    This function assigns a retirement record to the features within the specified layer. It ensures that:
    - The input layer has selected features to avoid retiring all features in the layer.
    - The layer is under a branch version before editing.
    - A valid record ID is available to retire the features.

    If these conditions are met, the function updates the 'RetiredByRecord' field with the corresponding record ID
    and refreshes the map view.

    Parameters:
        input_layer (Layer): The Parcel Fabric layer to be processed. Must be one of: חזיתות, נקודות גבול, נקודות גבול תלת-ממדיות, חזיתות גושים.
        record_name (str or None): The name of the record associated with the retirement. If None, the active record will be used.
    """
    layer: Layer = get_layer(input_layer)
    selection: set[int]|None = layer.getSelectionSet()

    is_versioned: bool = layer_is_at_version(input_layer)
    has_selection: bool = True if selection else False
    record_guid: str|None = get_RecordGUID(record_name, 'MAP') if record_name else get_ActiveRecord('GUID')
    record_name: str = record_name if record_name else get_ActiveRecord('Name')

    if not is_versioned:
        AddError(f'{timestamp()} | Input layer must be under a branch version before editing')

    if not has_selection:
        AddError(f'{timestamp()} | The layer must have selected features')

    if record_guid and has_selection and is_versioned:
        CalculateField(in_table= layer, field= 'RetiredByRecord', expression= f"'{record_guid}'", expression_type='PYTHON3')
        AddMessage(f'{timestamp()} | {len(selection)} Selected features at {input_layer} retired by the record {record_name} \n           Record ID: {record_guid}')
        RefreshLayer(layer)
        refresh_map_view()


if __name__ == "__main__":
    retire_features(input_layer= GetParameter(0), record_name= GetParameterAsText(1))
