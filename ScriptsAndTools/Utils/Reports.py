from Utils.Configs import CNFG
from Utils.TypeHints import *
from Utils.VersionManagement import get_VersionName, layer_is_at_version
from Utils.Helpers import delete_file, timestamp, get_layer, get_RecordGUID, get_ActiveRecord, get_feature_layer_id, AddTabularMessage
from Utils.NewCadasterHelpers import get_RecordGUID_NewCadaster
import pandas as pd
from pandas.io.formats.style import Styler
from os import makedirs
from arcgis import GIS
from arcgis.features._version import VersionManager
from arcgis.features import GeoAccessor, GeoSeriesAccessor
from arcpy import AddMessage, AddError, env as ENV
from arcpy.da import SearchCursor
from arcpy.mp import ArcGISProject
from arcpy.analysis import GenerateNearTable
from arcpy.management import SelectLayerByLocation as SelectByLocation, SelectLayerByAttribute as SelectByAttribute


ENV.overwriteOutput = True


def highlight_conflicts(data: df) -> Styler:
    """
    Apply highlighting to a pandas DataFrame to emphasize conflicts based on a threshold.

    Parameters:
        - data (pd.DataFrame): The DataFrame to be styled.

    Returns:
        - pd.io.formats.style.Styler: A styled version of the input DataFrame.
    """

    def highlight(val: int, hue: str = 'red') -> str:
        conflicts = hue if val > 1 else None
        return f"background-color: {conflicts}"

    styled_df = data.style.applymap(highlight, subset=['דירוג המרחק'])

    return styled_df


def SourcePointsByTask(task_type: TaskType) -> Layer|None:
    """
    Retrieves the layer containing in-process points from the current map in an ArcGIS project based on the specified task.

    Parameters:
        task_type (str): A string indicating the task type for which the layer is needed. Supported values are 'ImproveCurrentCadaster' and 'CreateAndRetireCadaster'.

    Returns:
        Layer or None: The layer containing the in-process points corresponding to the specified task. If the task is not recognized, None is returned.
    """
    if task_type == 'ImproveCurrentCadaster':
        source_points: Layer = get_layer('נקודות ביסוס')

    elif task_type == 'RetireAndCreateCadaster':
        source_points: Layer = get_layer('נקודות לשימור וחדשות')

    elif task_type in ['ImproveNewCadaster', 'CreateNewCadaster']:
        # Making a selection on the main 'in process points' layer due to a bug that causes the script to include
        # all 'in process points' when attempting to access the base points layer.
        # This is likely related to the use of subgroups within the process group layer
        def_query: str = get_layer('נקודות ביסוס').definitionQuery
        source_points: Layer = SelectByAttribute(get_layer('נקודות בתהליך'), 'NEW_SELECTION', def_query).getOutput(0)

    else:
        source_points: None = None
        AddError(f'{timestamp()} | Parameter task must be one of: ImproveCurrentCadaster, RetireAndCreateCadaster, ImproveNewCadaster, CreateNewCadaster')

    return source_points


def compute_matching_points_report(ProcessName: str, task: TaskType, distance: int = 5) -> None:
    """
    Computes a report analyzing the spatial relationship between in-process points and active points
    within a specified distance, highlighting conflicts where multiple matches occur.

    Parameters:
        ProcessName (str): The name of the process, used to set the location of the output files.
        task (TaskType): The type of task being processed, which determines the source points layer.
        distance (int, optional): The search radius in meters for matching points. Default is 5 meters.
    """
    AddMessage('\n ⭕ Generating reports \n')
    AddMessage(f'{timestamp()} | 🛠️ Computing the Matching Points Report, please wait...')
    CurrentMap: Map = ArcGISProject("current").activeMap
    CurrentMap.clearSelection()
    CurrentPoints: Layer = CurrentMap.listLayers('נקודות גבול')[0]
    InProcessPoints: Layer = SourcePointsByTask(task)

    CurrentPoints_selection: Layer = SelectByLocation(in_layer= CurrentPoints, select_features= InProcessPoints, overlap_type= 'WITHIN_A_DISTANCE', search_distance= f'{distance} Meters')
    if task == "CreateNewCadaster":
        CurrentPoints_selection: Layer = SelectByAttribute(CurrentPoints_selection, "SUBSET_SELECTION", f"""CreatedByRecord<>'{get_RecordGUID_NewCadaster(ProcessName)}'""").getOutput(0)

    # Compute distances
    shelf: str = ProcessName.replace('/', '_')
    GenerateNearTable(in_features= InProcessPoints, near_features= CurrentPoints_selection, out_table= fr'{CNFG.Library}{shelf}/NearTable.csv',
                      search_radius= distance, location= 'LOCATION', closest= 'ALL', distance_unit= 'Meters')

    # Read distances results and join data
    InProcessPoints_df: df = pd.DataFrame.spatial.from_featureclass(InProcessPoints, fields= ['OBJECTID', 'GlobalID', 'PointName'])
    CurrentPoints_df: df = pd.DataFrame.spatial.from_featureclass(CurrentPoints, fields= ['OBJECTID', 'GlobalID', 'Name'])
    NearTable_df: df = pd.read_csv(fr'{CNFG.Library}{shelf}/NearTable.csv', usecols= ['IN_FID', 'NEAR_FID', 'NEAR_RANK', 'NEAR_DIST', 'FROM_X', 'FROM_Y', 'NEAR_X', 'NEAR_Y'])

    columns_names: dict[str, str] = {'NEAR_DIST' : "מרחק במטרים",
                                     'NEAR_RANK' : "דירוג המרחק",
                                     'FROM_X'    : "קואורדינטה מזרחית בתהליך",
                                     'FROM_Y'    : "קואודינטה צפונית בתהליך",
                                     'NEAR_X'    : "קואורדינטה מזרחית ברצף",
                                     'NEAR_Y'    : "קואורדינטה צפונית ברצף",
                                     'NearGUID'  : "מזהה נקודת רצף",
                                     'Name'      : "שם נקודת רצף",
                                     'GlobalID'  : "מזהה נקודת תהליך",
                                     'PointName' : "שם נקודת תהליך"}

    columns_order: list[str] = ["שם נקודת תהליך",
                                "מזהה נקודת תהליך",
                                "קואורדינטה מזרחית בתהליך",
                                "קואודינטה צפונית בתהליך",
                                "שם נקודת רצף",
                                "מזהה נקודת רצף",
                                "קואורדינטה מזרחית ברצף",
                                "קואורדינטה צפונית ברצף",
                                "מרחק במטרים",
                                "דירוג המרחק"]

    results_df: df = NearTable_df.merge(CurrentPoints_df, left_on= 'NEAR_FID', right_on= 'OBJECTID', how= 'left')\
                                 .drop(columns= 'OBJECTID')\
                                 .rename(columns= {'GlobalID': 'NearGUID'})\
                                 .merge(InProcessPoints_df, left_on= 'IN_FID', right_on= 'OBJECTID', how= 'left')\
                                 .drop(columns= ['OBJECTID', 'NEAR_FID', 'IN_FID', 'SHAPE_x', 'SHAPE_y'])\
                                 .sort_values(["GlobalID", "NEAR_RANK"])\
                                 .rename(columns= columns_names)[columns_order]

    conflicts_count: int = len(results_df[results_df['דירוג המרחק'] > 1])

    if conflicts_count > 0:
        optimal_distance: float = round(results_df[results_df['דירוג המרחק'] == 1]['מרחק במטרים'].max(), 4)
        results_df: Styler = highlight_conflicts(results_df)
        AddMessage(f"{timestamp()} | ⚠️ {conflicts_count} Conflicts found within {distance} meters.")
        AddMessage(f"{timestamp()} | 💡 The optimal matching distance: {optimal_distance} meters")

    elif conflicts_count == 0:
        AddMessage(f"{timestamp()} | ℹ️ No conflicts found within {distance} meters")

    del conflicts_count

    report_path: str = fr'{CNFG.Library}{shelf}/PointsDistanceReport-{shelf}.xlsx'
    results_df.to_excel(report_path, index= False, engine= 'openpyxl', sheet_name= 'קונפליקטים')

    CurrentMap.clearSelection()
    AddMessage(f'{timestamp()} | 💡 Review the report to gain more insights')
    delete_file(fr'{CNFG.Library}{shelf}/NearTable.csv')
    delete_file(fr'{CNFG.Library}{shelf}/NearTable.csv.xml')


def set_date_columns(dataframe: df) -> df:
    """
    """
    date_columns: list[str] = ['created_date', 'last_edited_date', 'RecordedDate', 'SetteledDate']
    for col in date_columns:
        if col in dataframe.columns:
            dataframe[col] = pd.to_datetime(dataframe[col], unit="ms", errors="coerce")

    return dataframe


def compare_and_document_version_changes(user_name: str, password: str) -> None:
    """
    Compares and documents the changes made to specific feature layers in a branched versioned geodatabase.

    This function compares the attributes of feature layers before and after edits in a versioned environment,
    and generates an Excel report detailing the modifications (updates, inserts, deletes). The report includes
    a comparison of the attribute data before and after the edits for each layer.

    The function performs the following steps:
    1. Retrieves the active process name and checks if the layer is versioned.
    2. Connects to a version management server and fetches the branch version of the layer.
    3. Iterates through a predefined list of layer names to document changes.
    4. For each layer:
        - Fetches object IDs of the layer and checks if the layer contains any data.
        - Fetches the differences between the current and previous versions of the layer.
        - Writes the modifications (updates, inserts, deletes) to an Excel file, with separate sheets for each modification type.
        - Adds logs to track the progress of the operation.

    Parameters:
        user_name (str): The username for authenticating to the GIS server (The same user-name for entering the organization VDI).
        password (str): The password associated with the provided username (The same password for entering the organization VDI).
    """

    AddMessage(f"\n ⭕ Comparing and documenting layers attributes before & after the edits: \n ")

    process_name: str|None = get_ActiveRecord('Name')
    is_versioned: bool = layer_is_at_version('גבולות רישומים', error=True)

    if process_name and is_versioned:
        # Connection to version manager and fetch current branch version:
        version_management_server = VersionManager(CNFG.version_manager_url, GIS(CNFG.gis_url, f"{user_name}@MM_NT_MALI", password))
        branch_version_name: str = get_VersionName(name='גבולות רישומים', source='layer')

        # Layers to document:
        layer_names: list[str] = ['גבולות רישומים', 'נקודות גבול תלת-ממדיות', 'נקודות גבול', 'גושים', 'חזיתות', 'גריעות', 'היטלי גריעות', 'חלקות תלת-ממדיות', 'היטלי חלקות תלת-ממדיות', 'חלקות',
                                  'נקודות גבול תלת-ממדיות מבוטלות', 'נקודות גבול מבוטלות', 'גושים מבוטלים', 'גריעות מבוטלות', 'חלקות תלת-ממדיות מבוטלות', 'חזיתות מבוטלות', 'חלקות מבוטלות']

        total: int = len(layer_names)

        # Compare and document loop
        for idx, name in enumerate(layer_names, start=1):

            #  Layer information:
            object_IDs: set[int|None] = {i[0] for i in SearchCursor(get_layer(name), 'OBJECTID')}
            layer_ID: int|None = get_feature_layer_id(name)

            if len(object_IDs) > 0 and layer_ID and branch_version_name:

                # Output paths
                AddMessage(f"{timestamp()} | {idx}/{total} | {name}")
                shelf: str = fr"{CNFG.Library}{process_name.replace('/', '_')}/Modifications/{name}"
                output: str = fr"{shelf}\Differences.xlsx"
                makedirs(shelf, exist_ok=True)
                delete_file(output)

                # Extract layer changes in the version
                after: dict[str, list[dict[str, Any]]] = version_management_server.get(branch_version_name, 'read').differences("features", layers=[layer_ID])
                if 'features' in after.keys():
                    features: list[dict[str, Any]] = after['features']
                    for entry in features:
                        for mod_type in ["updates", "inserts", "delete"]:
                            if mod_type in entry:
                                rows: list[dict[str, dict]] = []
                                for item in entry[mod_type]:
                                    # Only keep attributes, exclude geometry
                                    attrs = item.get("attributes", {}).copy()
                                    if attrs.get("OBJECTID") in object_IDs:
                                        # attrs["layerId"] = entry["layerId"]
                                        attrs["modification"] = mod_type
                                        rows.append(attrs)

                                if rows:
                                    after: df = pd.DataFrame(rows)
                                    after.to_csv(fr"{shelf}/after.csv", index=False)

                                    after_columns: list[str] = after.columns.to_list()
                                    is_area: bool = True if 'Shape.STArea()' in after_columns else False
                                    is_length: bool = True if 'Shape.STLength()' in after_columns else False

                                    # Extract pre changes data:
                                    before_path: str = f"{CNFG.portal_url}/{CNFG.FeatureServers[0]}/FeatureServer;VERSION=sde.DEFAULT;VERSIONGUID='{CNFG.default_version_guid}'/{layer_ID}"

                                    fields: list[str] = [f for f in after_columns if f not in ["Shape.STArea()", "Shape.STLength()", "modification"]]
                                    fields: list[str] = fields + ['Shape__Area'] if is_area else fields
                                    fields: list[str] = fields + ['Shape__Length'] if is_length else fields

                                    object_ids_string: str = ", ".join(str(oid) for oid in sorted(object_IDs))
                                    query: str = f"OBJECTID IN ({object_ids_string})" if name != 'גבולות רישומים' else f"Name = '{process_name}'"

                                    before: df = pd.DataFrame(SearchCursor(before_path, fields, query), columns=fields)\
                                                   .rename(columns= {"Shape__Area": "Shape.STArea()", "Shape__Length": "Shape.STLength()"})

                                    before.to_csv(fr"{shelf}/before.csv", index=False)

                                    del fields, before_path

                                    # Updates:
                                    query: str = "modification == 'updates'" if name != 'גבולות רישומים' else f"modification == 'updates' and Name == '{process_name}'"
                                    updates: df = after.query(query).drop(columns='modification')
                                    updates: df = set_date_columns(updates)

                                    before_updates: df = before[before['GlobalID'].isin(updates['GlobalID'])]
                                    before_updates: df = set_date_columns(before_updates)

                                    before_updates: df = before_updates.set_index('GlobalID').sort_index()
                                    updates: df = updates.set_index('GlobalID').sort_index()

                                    updates: df = before_updates.compare(updates, result_names=('Before', 'After'))
                                    del before_updates

                                    # Inserts:
                                    inserts: df = after.query("modification == 'inserts'").drop(columns='modification')
                                    inserts: df = set_date_columns(inserts)
                                    inserts: df = inserts.set_index('GlobalID')

                                    # Deletions:
                                    deletes: df = after.query("modification == 'delete'").drop(columns='modification')
                                    deletes: df = set_date_columns(deletes)
                                    deletes: df = deletes.set_index('GlobalID')

                                    modifications_df: df = pd.DataFrame(data= {f'{idx}/{total}': f'{name}',
                                                                               'New features': len(inserts),
                                                                               'Updated features': len(updates),
                                                                               'Deleted features': len(deletes)},
                                                                        index= [0])

                                    AddTabularMessage(modifications_df)

                                    with pd.ExcelWriter(output, engine="openpyxl") as writer:
                                        updates.to_excel(writer, sheet_name="Updates", index=True)
                                        inserts.to_excel(writer, sheet_name="Inserts", index=True)
                                        deletes.to_excel(writer, sheet_name="Deletes", index=True)

                else:
                    AddMessage(f"{timestamp()} | No modifications found \n ")

            else:
                AddMessage(f"{timestamp()} | {idx}/{total} | {name}: No features in the area of interest \n ")
                AddMessage(f"{timestamp()} | No features in the area of interest \n ")
