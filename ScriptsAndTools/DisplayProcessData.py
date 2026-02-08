from Utils.TypeHints import *
from Utils.Configs import CNFG
from Utils.Validations import process_exist
from Utils.Helpers import get_ProcessType, get_ProcessGUID, refresh_map_view, timestamp, zoom_to_aoi
from arcpy import RefreshLayer, GetParameterAsText, AddMessage
from arcpy.mp import ArcGISProject
from arcpy.da import SearchCursor


def display_process_data(ProcessName: str) -> None:
    """
    Display process-related data layers in the current ArcGIS project map.

    Parameters:
        ProcessName (str): The name of the process for which data is displayed.
    """
    if process_exist(ProcessName) == 'Valid':
        current_map: Map = ArcGISProject("current").activeMap
        process_type: int = get_ProcessType(ProcessName)
        process_guid: str = get_ProcessGUID(ProcessName)
        query_name: str = f'Process {ProcessName}'
        refresh_map_view()

        if process_type != 2:
            current_map.addDataFromPath(fr'{CNFG.LayerFiles}Display2DProcessData_{CNFG.Environment}.lyrx')
            group_layer: Layer = current_map.listLayers('תכנית')[0]
            current_map.moveLayer(current_map.listLayers('בקרת איכות')[0], group_layer, "BEFORE")
            group_layer.name = f'{ProcessName} תכנית'

            process_border: Layer = current_map.listLayers('גבול תכנית')[0]
            process_border.updateDefinitionQueries([{'name': query_name, 'sql': f" ProcessName = '{ProcessName}' ", 'isActive': True}])
            actions_table: Table = current_map.listTables('פעולות בתכנית')[0]
            actions_table.updateDefinitionQueries([{'name': query_name, 'sql': f" CPBUniqueID = '{process_guid}' ", 'isActive': True}])

            layers_name: list[str] = ['נקודות לביטול', 'נקודות לשימור', 'נקודות ביניים', 'נקודות חדשות',
                                      'חזיתות לביטול', 'חזיתות לשימור', 'חזיתות ביניים', 'חזיתות חדשות',
                                      'חלקות לביטול',  'חלקות לשימור', 'חלקות ביניים', 'חלקות חדשות']

            for name in layers_name:
                layer: Layer = current_map.listLayers(name)[0]
                new_query: dict[str, str|bool] = {'name': query_name, 'sql': f" {layer.definitionQuery} And CPBUniqueID = '{process_guid}' ", 'isActive': True}
                layer.updateDefinitionQueries([new_query])
                RefreshLayer(layer)

            del layers_name


        if process_type == 2:

            current_map.addDataFromPath(fr'{CNFG.LayerFiles}Display3DProcessData.lyrx')
            group_layer: Layer = current_map.listLayers('תכנית')[0]
            top_layer: str = 'בקרת איכות' if current_map.name == 'מפת עריכה' else 'קדסטר בתהליך'
            current_map.moveLayer(current_map.listLayers(top_layer)[0], group_layer, "BEFORE")
            group_layer.name = f'{ProcessName} תכנית'

            process_border: Layer = current_map.listLayers('גבול תכנית')[0]
            process_border.updateDefinitionQueries([{'name': query_name, 'sql': f" ProcessName = '{ProcessName}' ", 'isActive': True}])
            actions_table: Table = current_map.listTables('פעולות בתכנית')[0]
            actions_table.updateDefinitionQueries([{'name': query_name, 'sql': f" CPBUniqueID = '{process_guid}' ", 'isActive': True}])
            del process_border, actions_table

            layers_name: list[str] = ['נקודות לביטול', 'נקודות לשימור', 'נקודות ביניים', 'נקודות חדשות',
                                      'חלקות לביטול', 'חלקות לשימור', 'חלקות ביניים', 'חלקות חדשות',
                                      'גריעות לשימור', 'גריעות חדשות']

            for name in layers_name:
                layer: Layer = current_map.listLayers(name)[0]
                new_query: dict[str, str|bool] = {'name': query_name, 'sql': f" {layer.definitionQuery} And CPBUniqueID = '{process_guid}' ", 'isActive': True}
                layer.updateDefinitionQueries([new_query])
                RefreshLayer(layer)


            # Projected layers:
            projected_parcels3D: Layer = current_map.listLayers('היטלי חלקות חדשות')[0]
            guids: str = ','.join([f"'{row[0]}'" for row in SearchCursor(current_map.listLayers('חלקות חדשות')[0], "GlobalID")])
            new_query: dict[str, str|bool] = {'name': query_name, 'sql': f"Parcel3DUniqueID IN ({guids})", 'isActive': True}
            projected_parcels3D.updateDefinitionQueries([new_query])

            projected_substractions: Layer = current_map.listLayers('היטלי גריעות חדשות')[0]
            guids: str = ','.join([f"'{row[0]}'" for row in SearchCursor(current_map.listLayers('גריעות חדשות')[0], "GlobalID")])
            new_query: dict[str, str|bool] = {'name': query_name, 'sql': f"SubstractionUniqueID IN ({guids})", 'isActive': True}
            projected_substractions.updateDefinitionQueries([new_query])

            RefreshLayer([projected_parcels3D, projected_substractions])
            del layers_name, projected_parcels3D, projected_substractions


        zoom_to_aoi()
        refresh_map_view()
        AddMessage(f"{timestamp()} | ✅ Process {ProcessName} is displayed on the active map")
        del process_type, process_guid, query_name

    else:
        AddMessage(f"{timestamp()} | ❌ Process {ProcessName} does not exist")


if __name__ == "__main__":
    display_process_data(ProcessName= GetParameterAsText(0))
