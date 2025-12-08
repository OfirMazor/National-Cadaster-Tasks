from Utils.TypeHints import *
from Utils.VersionManagement import get_VersionName
from Utils.Helpers import deactivate_record, drop_layer, drop_dbtable, reopen_map, timestamp, get_layer, get_table
from arcpy import AddMessage, ListFeatureClasses, ListTables, env
from arcpy.mp import ArcGISProject
from arcpy.management import ChangeVersion, Delete, ClearWorkspaceCache


def reset_definition_queries() -> None:
    """
    Reset the definition query of the current and retired cadaster layers in the ArcGIS project.
    """
    current_map: Map = ArcGISProject('current').activeMap

    active_layers: list[str] = ['חלקות', 'גושים', 'חזיתות', 'נקודות גבול', 'חלקות תלת-ממדיות', 'גריעות', 'נקודות גבול תלת-ממדיות']
    current_base_query: list[dict[str, Any]] = [{'name': 'Base', 'sql': 'RetiredByRecord IS NULL', 'isActive': True}]
    for name in active_layers:
        layer: Layer = current_map.listLayers(name)[0]
        layer.updateDefinitionQueries(current_base_query)

    retired_layer: list[str] = ['נקודות גבול מבוטלות', 'חזיתות מבוטלות', 'חלקות מבוטלות', 'גושים מבוטלים',
                                'נקודות גבול תלת-ממדיות מבוטלות', 'חלקות תלת-ממדיות מבוטלות', 'גריעות מבוטלות']
    retired_base_query: list[dict[str, Any]] = [{'name': 'Base', 'sql': 'RetiredByRecord IS NOT NULL', 'isActive': True}]
    for name in retired_layer:
        layer: Layer = current_map.listLayers(name)[0]
        layer.updateDefinitionQueries(retired_base_query)

    background_layers: list[str] = ['נקודות בקרה', 'היטלי חלקות תלת-ממדיות', 'היטלי גריעות']
    query: list[dict[str, Any]] = [{'name': 'Base', 'sql': 'OBJECTID <> -1', 'isActive': True}]
    for name in background_layers:
        layer: Layer = current_map.listLayers(name)[0]
        if layer:
            layer.updateDefinitionQueries(query)

    qa_names: list[str] = ['קווי אימות' , 'נקודות אימות', 'שגיאות מסוג פוליגון' , 'שגיאות מסוג קו' , 'שגיאות מסוג נקודה' , 'אזורים לא חוקיים' , 'שטחי אימות']
    for name in qa_names:
        layer: Layer = current_map.listLayers(name)[0]
        layer.updateDefinitionQueries(None)

    AddMessage(f'{timestamp()} | ✔️ layers definition queries reset')


def drop_intermediate_layers() -> None:
    """
    Removes layer and tables created during a task from the content panel.
    """

    # Drop unwanted layers
    layers: list[Layer] = [layer for layer in ArcGISProject('current').activeMap.listLayers()]
    to_remove: list[str] = [layer.name for layer in layers
                            if
                            layer.name in ['נקודות סמוכות', 'חורים וחפיפות', 'קונפליקטים']
                            or
                            (any(substring in layer.name for substring in [' תכנית', 'תכנית ']) and layer.isGroupLayer)]

    for layer in to_remove:
        drop_layer(layer)
        AddMessage(f"{timestamp()} | ✔️ Layer {layer} dropped")
    del layers, to_remove

    # Drop unwanted table
    tables: list[Table] = [table for table in ArcGISProject('current').activeMap.listTables()]
    to_remove: list[str] = [table.name for table in tables if table.name not in ['טבלת אימות', 'סדר פעולות']]

    for table in to_remove:
        drop_dbtable(table)
        AddMessage(f"{timestamp()} | ✔️ Table {table} dropped")


def return_to_default_version() -> None:
    """Changing the project layers back to sde.DEFAULT version if they are set on other version."""

    layers: list[str] = ['רישומים', 'גריעות', 'גריעות מבוטלות', 'חלקות תלת-ממדיות', 'חלקות תלת-ממדיות מבוטלות',
                         'חלקות תלת-ממדיות מבוטלות', 'נקודות גבול תלת-ממדיות', 'נקודות גבול תלת-ממדיות מבוטלות',
                         'היטלי חלקות תלת-ממדיות', 'היטלי גריעות']
    for name in layers:
        if get_VersionName(name, source='layer') != 'sde.DEFAULT':
            layer: Layer = get_layer(name)
            ChangeVersion(layer, "BRANCH", 'sde.DEFAULT', include_participating= "INCLUDE" if name == 'רישומים' else "EXCLUDE")

    AddMessage(f"{timestamp()} | ✔️ Layers returned to default version")

    if get_VersionName('טבלת אימות', source='table') != 'sde.DEFAULT':
        error_table: Table = get_table('טבלת אימות')
        ChangeVersion(error_table, "BRANCH", 'sde.DEFAULT')
        AddMessage(f"{timestamp()} | ✔️ Error layers returned to default version")


def clear_project_gdb() -> None:
    """Deletes all tables and feature classes created during a task in the project home gdb."""
    env.workspace = fr"{ArcGISProject('current').homeFolder}\Project.gdb"
    data: list[str] = ListFeatureClasses() + ListTables()
    if data:
        for item in data:
            Delete(item)
        AddMessage(f"{timestamp()} | ✔️ Home geodatabase cleared")


def reinitialize() -> None:
    """
    Reinitialize the project by:
    - Resetting definition queries
    - Removing layers and tables created during a task
    - Returning layer versions to default.
    - Deleting any table of feature class created during a task.
    - Finally, reopens the map object.
    """
    AddMessage(f'\n ⭕ Reinitializing project')
    reset_definition_queries()
    deactivate_record()
    drop_intermediate_layers()
    return_to_default_version()
    clear_project_gdb()
    ArcGISProject('current').activeMap.clearSelection()
    reopen_map()
    ClearWorkspaceCache()


if __name__ == "__main__":
    reinitialize()
