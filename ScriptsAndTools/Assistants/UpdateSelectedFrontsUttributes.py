from set_path import add_parent_to_sys_path
add_parent_to_sys_path(__file__)

from Utils.Configs import CNFG
from Utils.TypeHints import Layer, Result, Scur, Any
from arcpy import AddMessage, env as ENV, AddError, GetParameter
from arcpy.mp import ArcGISProject
from arcpy.da import SearchCursor, UpdateCursor
from arcpy.management import SelectLayerByLocation as SelectByLocation, MakeFeatureLayer as MakeLayer
from Utils.Helpers import timestamp, get_ActiveRecord, layer_selection_info, get_StartPointGUID, get_EndPointGUID, drop_layer, get_layer, AddDefinitionQuery


def update_selected_fronts_attributes(source_fronts: Layer) -> None:
    """
    Updates active fronts attributes that matches (geometry identical) to the selected source fronts.

    Parameters:
        source_fronts (Layer): The lines layer that have the new or improved data from the cadastral plan.
    """

    # Validations:
    RecordGUID: str|None = get_ActiveRecord('GUID')

    selection_info: dict[str, list[int]|None|bool|int] = layer_selection_info(source_fronts)
    if not selection_info['has_selection']:
        AddError(f"{timestamp()} | The source fronts layer must have at least one selected feature")


    if RecordGUID and selection_info['has_selection']:
        # Begin matching and updating:
        AddMessage('\n ⭕ Updating selected fronts attributes: \n ')
        drop_layer('חזיתות לא מתואמות')
        ENV.addOutputsToMap = False

        selected_list: list[int] = selection_info['selection_OIDs']
        total_selected: int = selection_info['selection_count']

        source_fields: list[str] = ['LegalLength', 'Radius', 'LineType']

        active_fronts: Layer = get_layer('חזיתות')
        target_fields: list[str] = ['Distance', 'Radius', 'LineType', 'UpdatedByRecord', 'StartPointUniqueID', 'EndPointUniqueID', 'Shape@', 'OBJECTID', 'CreatedByRecord']

        unmatched_fronts: list[int|None] = []

        for idx, oid in enumerate(selected_list, start=1):
            source_front: Layer = MakeLayer(source_fronts, 'process_front', f"OBJECTID = {oid}")[0]
            matched_front: Result = SelectByLocation(in_layer= active_fronts, select_features= source_front, overlap_type= 'ARE_IDENTICAL_TO')
            count_matches: int = int(matched_front[2])

            if count_matches == 0:
                AddMessage(f"{timestamp()} | {idx}/{total_selected} | ⚠️ The process front {oid} does not match any active front and will not be modified. \n ")
                unmatched_fronts.append(oid)

            if count_matches > 1:
                AddMessage(f"{timestamp()} | {idx}/{total_selected} | ⚠️ The process front {oid} matched with {count_matches} active fronts and will not be modified. \n ")
                unmatched_fronts.append(oid)

            if count_matches == 1:
                source_data: Scur = SearchCursor(source_front, source_fields)
                source_data: dict[str, Any] = [{'LegalLength': i[0], 'Radius': i[1], 'LineType': i[2]} for i in source_data][0]

                active_front = UpdateCursor(matched_front[0], target_fields)
                for row in active_front:
                    prior: dict[str, Any] = {'Distance': row[0], 'Radius': row[1], 'LineType': row[2],
                                             'UpdatedByRecord': row[3], 'CreatedByRecord': row[8],
                                             'StartPointUniqueID': row[4], 'EndPointUniqueID': row[5],
                                             'Shape@': row[6], 'OBJECTID': row[7]}

                    AddMessage(f"{timestamp()} | {idx}/{total_selected} | ✔️ Updates of front with Object ID {prior['OBJECTID']}:")

                    row[2]: int = source_data['LineType']
                    AddMessage(f"{timestamp()} | LineType: {prior['LineType']} --➤➤ {row[2]}")

                    row[0]: float = source_data['LegalLength']
                    AddMessage(f"{timestamp()} | Distance: {prior['Distance']} --➤➤ {row[0]}")

                    row[1]: int = source_data['Radius'] if source_data['LineType'] == 2 else 0
                    AddMessage(f"{timestamp()} | Radius: {prior['Radius']} --➤➤ {row[1]}")

                    row[3]: int = RecordGUID if prior['CreatedByRecord'] != RecordGUID else None
                    AddMessage(f"{timestamp()} | UpdatedByRecord: {prior['UpdatedByRecord']} --➤➤ {row[3]}")

                    row[4]: int = get_StartPointGUID(row[6])
                    AddMessage(f"{timestamp()} | StartPointUniqueID: {prior['StartPointUniqueID']} --➤➤ {row[4]}")

                    row[5]: int = get_EndPointGUID(row[6])
                    AddMessage(f"{timestamp()} | EndPointUniqueID: {prior['EndPointUniqueID']} --➤➤ {row[5]} \n ")

                    active_front.updateRow(row)

                del active_front, source_data

        ENV.addOutputsToMap = True

        # Add an unmatched fronts layer if unmatched fronts found
        total_unmatched: int = len(unmatched_fronts)
        if total_unmatched > 0:
            unmatched_fronts: str = ', '.join([str(oid) for oid in unmatched_fronts])
            query_params: dict[str, Any] = {'name': 'UnmatchedFronts', 'sql': f"OBJECTID IN ({unmatched_fronts})", 'isActive': True}
            ArcGISProject("current").activeMap.addDataFromPath(f"{CNFG.LayerFiles}UnmatchedFronts_{CNFG.Environment}.lyrx")
            AddDefinitionQuery(get_layer('חזיתות לא מתואמות'), query_params)
            AddMessage(f"{timestamp()} | 💡 {total_unmatched} unmatched fronts from the process are displayed on the map")

        AddMessage(f"{timestamp()} | ℹ️ Click the Version-Refresh button to see the updates on the map \n ")


if __name__ == '__main__':
    update_selected_fronts_attributes(source_fronts= GetParameter(0))
