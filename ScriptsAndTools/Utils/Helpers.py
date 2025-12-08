import os
import re
from os.path import exists
import requests
import subprocess
import datetime as dt
from pandas import DataFrame
from Utils.TypeHints import *
from Utils.Configs import CNFG
from arcpy import AddMessage, AddError, PointGeometry, Point, SpatialReference, RefreshLayer, Extent, env as ENV
from arcpy.mp import ArcGISProject
from arcpy.da import SearchCursor, UpdateCursor, InsertCursor, Editor, ListDomains
from arcpy.management import SelectLayerByLocation as SelectByLocation, Append, Dissolve


def timestamp() -> str:
    """Returns the current time"""
    current_time: str = str(dt.datetime.now().strftime("%H:%M:%S"))
    return current_time


def set_priority(priority: Literal['Realtime', 'High', 'Above Normal', 'Normal', 'Below Normal', 'Low', 'Idle'] = 'High') -> None:
    """
    Set the priority of the current process.

    Parameters:
        priority (str, optional): The priority level to set. Default is 'High'.
    """
    # Mapping string priority to WMIC integer value
    priority_map: dict[str, int] = {'Idle': 64,
                                    'BelowNormal': 16384,
                                    'Normal': 32,
                                    'AboveNormal': 32768,
                                    'High': 128,  # Default
                                    'RealTime': 256}

    # Get the process ID
    pid: str = str(os.getpid())
    # Get the corresponding integer priority
    priority_code = priority_map.get(priority, 128)
    # Construct the command
    command = f'wmic process where processid="{pid}" CALL setpriority {priority_code}'
    # Run the command
    subprocess.run(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cursor_length(cursor: Scur|Ucur) -> int:
    """Counts the rows in a cursor"""
    cursor.reset()
    count: int = len([row[0] for row in cursor])
    cursor.reset()

    return count


def drop_layer(layer_name: str) -> None:
    """ Remove a layer from a map in a project. """
    current_map: Map = ArcGISProject('current').activeMap
    layer_list: list[Layer|None] = current_map.listLayers(layer_name)
    if layer_list:
        current_map.removeLayer(layer_list[0])


def drop_dbtable(table_name: str) -> None:
    """ Remove a table from a map in a project. """
    current_map: Map = ArcGISProject('current').activeMap
    table_list: list[Table|None] = current_map.listTables(table_name)
    if table_list:
        current_map.removeTable(table_list[0])


def create_shelf(ProcessName: str) -> str:
    """
    Create a shelf (directory) based on the provided process name.

    Parameters:
    - ProcessName (str): The name of the process used to create the shelf.
      This name will be sanitized by replacing '/' with '_' to ensure valid directory naming.
    """

    shelf: str = ProcessName.replace('/', '_')
    folder_path: str = os.path.join(os.getcwd(), f'{CNFG.Library}{shelf}')

    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    return folder_path


def AddTabularMessage(table: df):
    """
    Convert a Pandas DataFrame into a custom JSON string format and print it as a tabular message.
    The printer table will always be a 2 columns table.

    Parameters:
        table (df): Pandas DataFrame object
    """

    from json import dumps
    first_row = table.iloc[0]

    # Build the "data" array: [[col, value], ...]
    data_part = [[col, str(first_row[col])] for col in table.columns]

    # Example elementProps (static, can be extended dynamically if needed)
    element_props = {"striped": "true",
                     "0": {"align": "center", "pad": "30px"},
                     "1": {"align": "center", "pad": "30px"}}

    # Build the full structure
    result = {"element": "table",
              "data": data_part,
              "elementProps": element_props}

    # Convert to string with prefix "json:"
    json_message: str = "json:" + dumps([result], ensure_ascii=False)

    AddMessage(json_message)


def get_active_user(mode: Literal['short', 'long'] = 'short') -> str|None:
    """
    Retrieves the username of the currently signed-in ArcGIS Pro user.
    This function connects to the active ArcGIS Pro session using the ArcGIS API for Python
    and returns the username of the authenticated portal user. The returned format depends
    on the selected mode:

    - short: Returns the username without the domain or email suffix (@MM_NT_MALI).
    - long: Returns the full username as stored in the portal.

    Parameters:
        mode (Literal['short', 'long'], optional): Determines the format of the returned username. Defaults to `'short'`.

    Returns:
        str | None: The username of the active user if available, otherwise `None`.
    """
    from arcgis.gis import GIS, User
    user: User = GIS("pro").users.me
    if user:
        if mode == 'short':
            return user.username.split('@')[0]
        elif mode == 'long':
            return user.username


def get_layer(layer_name: str, map_name: MapType = 'Active map') -> Layer | None:
    """ Returns a layer object from the active map in a project.

        Parameters:
            layer_name (str): The name of the layer in the content pane.
            map_name (MapType): The name of the map containing the layer. Default to the current active map.

        Return:
            The Layer object unless the layer name was not found in the map.
    """
    if map_name == 'Active map':
        layer: Layer|None = ArcGISProject("current").activeMap.listLayers(layer_name)[0]
    else:
        layer: Layer|None = ArcGISProject("current").listMaps(map_name)[0].listLayers(layer_name)[0]

    if layer:
        return layer
    else:
        AddMessage(f' {map_name} does not contain the layer {layer_name}')
        return None


def get_table(table_name: str, map_name: MapType = 'Active map') -> Table | None:
    """ Returns a table from the active map in a project.

        Parameters:
            table_name (str): The name of the table in the content pane.
            map_name (MapType): The name of the map containing the table. Default to the current active map.

        Return:
            The Table object unless the table name was not found in the map.
    """
    if map_name == 'Active map':
        table: Table|None = ArcGISProject("current").activeMap.listTables(table_name)[0]
    else:
        table: Table|None = ArcGISProject("current").listMaps(map_name)[0].listTables(table_name)[0]

    if table:
        return table
    else:
        AddMessage(f' {map_name} does not contain the table {table_name}')
        return None


def get_feature_layer_id(layer_name: str) -> int|None:
    """
    Return the ID number of the feature service layer.
    Parameters:
        layer_name (str): The name of the layer in the active map.
    """
    feature_layer_id: int|None = int(get_layer(layer_name).connectionProperties['dataset'])
    return feature_layer_id


def get_feature_table_id(table_name: str) -> int|None:
    """
    Return the ID number of the feature service table.
    Parameters:
        table_name (str): The name of the table in the active map.
    """
    feature_table_id: int|None = int(get_table(table_name).connectionProperties['dataset'])
    return feature_table_id


def refresh_map_view(scale: Optional[float] = 0.1) -> None:
    """Refresh the map view by changing the map scale

        Parameters:
            scale (Optional[float]): the scale (in meters) that will be added to the active map camera view. Default is  0.1 meters.
    """
    view = ArcGISProject("current").activeView
    if view:
        view.camera.scale = view.camera.scale + scale


def reopen_map(map_name: MapType = 'Active map') -> None:
    """Close and reopen the active map in the current ArcGIS project object.
       Use for refreshing the changes on the map after actions has been implemented to the objects in the map.

        Parameters:
            map_name (MapType): The name of the map the close and reopen. Default is current active map.
    """

    current_project: Pro = ArcGISProject('current')
    if map_name == 'Active map':
        map_object: Map = current_project.activeMap
    else:
        map_object: Map = current_project.listMaps(map_name)[0]
    if map_object:
        current_project.save()
        current_project.closeViews('MAPS')
        map_object.openView()


def start_editing(workspace: str) -> Editor:
    """
    Start editing in a geodatabase workspace using the arcpy.da.Editor class.

    Parameters:
        workspace (str): The path to the geodatabase workspace.
    """

    editor: Editor = Editor(workspace=workspace, multiuser_mode=True)
    editor.startEditing(with_undo=True, multiuser_mode=True)
    editor.startOperation()
    return editor


def stop_editing(editor: Editor, save: bool = True) -> None:
    """
    Stop editing in a geodatabase workspace using the arcpy.da.Editor class.

    Parameters:
        editor (Editor): The current active editor object.
        save (bool): True to save the edits (This is the default), False to discard changes.
    """
    editor.stopOperation()
    editor.stopEditing(save_changes = save)


def get_DomainValue(domain: str, code: int) -> str:
    """
    Retrieve the domain value associated with a given domain and code.

    Parameters:
        domain (str): The name of the domain from which to retrieve the value.
        code (int): The code corresponding to the value within the specified domain.

    Returns:
        str: The text associated with the provided code in the specified domain.
    """

    domains_list:  list[Domain] = ListDomains(CNFG.ParcelFabricDatabase)
    domain_object: Domain = [i for i in domains_list if i.name == domain][0]
    value: str = domain_object.codedValues[code]

    return value


def get_ProcessType(ProcessName: str) -> int:
    """Returns the type of cadastral process border by an input process name"""

    table: str = f'{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}CadasterProcessBorders'
    query: str = f"ProcessName = '{ProcessName}'"
    search: Scur = SearchCursor(table, 'ProcessType', query)
    ProcessType: int = int([row[0] for row in search][0])
    del search

    return ProcessType


def get_ProcessStatus(ProcessName: str, source: Literal['MAP', 'SDE'] = 'SDE') -> int | None:
    """Returns the current status of a cadastral process border by an input process name"""

    if source == 'SDE':
        table: str = f'{CNFG.ParcelFabricDataset}{CNFG.OwnerName}CadasterProcessBorders'
    elif source == 'MAP':
        table: Layer = get_layer('גבולות תהליכי קדסטר')
    else:
        table: None = None
        AddError("source parameter must be on of ['SDE', 'MAP']")


    Scursor: Scur = SearchCursor(table, 'Status', f""" ProcessName = '{ProcessName}' """)
    Scursor_len: int = cursor_length(Scursor)

    if Scursor_len == 1:
        ProcessStatus: int = int([row[0] for row in Scursor][0])
        return ProcessStatus
    if Scursor_len == 0:
        AddMessage(f'{timestamp()} |  ⚠️ Process {ProcessName} Not found')
        return None
    if Scursor_len > 1:
        AddMessage(f'{timestamp()} |  ⚠️ Found {Scursor_len} processes named {ProcessName}')
        return None

    del table, Scursor, Scursor_len


def get_ProcessGUID(ProcessName: str, source: Literal['MAP', 'SDE'] = 'SDE') -> str | None:
    """Returns the Global ID of a cadastral process border by an input process name"""

    if source == 'SDE':
        table: str = f'{CNFG.ParcelFabricDataset}{CNFG.OwnerName}CadasterProcessBorders'
    elif source == 'MAP':
        table: Layer = get_layer('גבולות תהליכי קדסטר')
    else:
        table: None = None
        AddError("source parameter must be on of ['SDE', 'MAP']")

    Scursor: Scur = SearchCursor(table, 'GlobalID', f""" ProcessName = '{ProcessName}' """)
    Scursor_len: int = cursor_length(Scursor)

    if Scursor_len == 1:
        ProcessGUID: str = [row[0] for row in Scursor][0]
        return ProcessGUID
    if Scursor_len == 0:
        AddMessage(f'{timestamp()} |  ⚠️ Process {ProcessName} Not found')
        return None
    if Scursor_len > 1:
        AddMessage(f'{timestamp()} |  ⚠️ Found {Scursor_len} processes named {ProcessName}')
        return None

    del table, Scursor, Scursor_len


def get_RecordGUID(ProcessName: str, source: Literal['MAP', 'SDE', 'SHELF'] = 'SDE', warnings: bool = True) -> str|None:
    """Returns the Global ID of a cadastral record border by an input process name"""

    if source == 'SHELF':
        txt_file: str = fr"{CNFG.Library}{ProcessName.replace('/', '_')}/RecordGUID.txt"
        if exists(txt_file):
            RecordGUID: str = open(txt_file, "r").read().strip()
            return RecordGUID
        else:
            if warnings: AddError(f'{timestamp()} | Text file {txt_file} not exists')
            return None

    if source in ['SDE', 'MAP']:
        source_dict: dict[str, str|Layer] = {'SDE': f'{CNFG.ParcelFabricDataset}{CNFG.OwnerName}CadasterRecordsBorders',
                                             'MAP': get_layer('גבולות רישומים')}

        Scursor: Scur = SearchCursor(source_dict[source], 'GlobalID', f"Name = '{ProcessName}'")
        Scursor_len: int = cursor_length(Scursor)

        if Scursor_len == 1:
            RecordGUID: str = Scursor.next()[0]
            return RecordGUID
        if Scursor_len == 0:
            if warnings: AddMessage(f'{timestamp()} | ⚠️ Record {ProcessName} Not found')
            return None
        if Scursor_len > 1:
            if warnings: AddMessage(f'{timestamp()} | ⚠️ Found {Scursor_len} records named {ProcessName}')
            return None

        del source_dict, Scursor, Scursor_len

    else:
        AddError(f"{timestamp()} | source parameter must be on of ['SDE', 'MAP', 'SHELF]")



def get_process_shape(ProcessName: str) -> Polygon|None:
    """

    """
    cpb_path: str = f"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}CadasterProcessBorders"
    search: Scur = SearchCursor(cpb_path, "Shape@", f"ProcessName = '{ProcessName}'")
    if cursor_length(search) == 1:
        shape: Polygon = search.next()[0]
        return shape
    else:
        AddMessage(f"{timestamp()} | Process {ProcessName} not exist or duplicated")


def get_BlockGUID(by: Literal['ProcessName', 'BlockName'], name: str) -> str | None:
    """
    Returns the Global ID of a block based on the provided criteria.

    Parameters:
    by (str): The criteria to search for the block. Can be either 'ProcessName' or 'BlockName'.
    name (str): The name of the process or block to search for.

    Returns:
    str|None: The Global ID of the block if found, otherwise None.
    """

    BlockGUID: str | None = None

    if by == 'ProcessName':
        table: str = f'{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}CadasterProcessBorders'
        Scursor: Scur = SearchCursor(table, 'BlockUniqueID', f"ProcessName = '{name}'")
        BlockGUID: str = [row[0] for row in Scursor][0]
        del Scursor

    elif by == 'BlockName':
        table: str = f'{CNFG.ParcelFabricDataset}{CNFG.OwnerName}Blocks'
        Scursor: Scur = SearchCursor(table, 'GlobalID', f"Name = '{name}'")
        BlockGUID: str = [row[0] for row in Scursor][0]
        del Scursor

    if not BlockGUID:
        AddMessage('Block Global ID returned as None')

    return BlockGUID


def get_BlockName(guid: str) -> str | None:
    """
    Returns the Name of a block based on the block Global ID.

    Parameters:
    guid (str): The block's Global ID to search for.

    Returns:
    str|None: The Name of the block if found, otherwise None.
    """

    table: str = f'{CNFG.ParcelFabricDataset}{CNFG.OwnerName}Blocks'
    Scursor: Scur = SearchCursor(table, 'Name', f""" GlobalID = '{guid}' """)
    if cursor_length(Scursor) == 1:
        Name: str = Scursor.next()[0]
    else:
        Name: None = None
        AddMessage('Block Name returned as None')

    del Scursor, table
    return Name


def get_BlockStatus(by: Literal['Name', 'GlobalID'], value: str) -> int | None:
    """
    Returns the status of a block based on the provided criteria.

    Parameters:
    by (str): The criteria to search for the block. Can be either 'Name' or 'GlobalID'.
    value (str): The value of the criteria to search for.

    Returns:
    int|None: The status code of the block if found, otherwise None.
    """

    status: int|None = None
    table: str = f'{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}Blocks'

    if by == 'Name':
        status: int = SearchCursor(table, 'BlockStatus', f"Name = '{value}' AND RetiredByRecord IS NULL").next()[0]

    elif by == 'GlobalID':
        status: int = SearchCursor(table, 'BlockStatus', f"GlobalID = '{value}' AND RetiredByRecord IS NULL").next()[0]

    if not status:
        AddMessage('Block status returned as None')
    else:
        return status


def get_ActiveParcel2DGUID(name: str, source: Literal['MAP', 'SDE'] = 'MAP') -> str | None:
    """
    Returns the Global ID of an active 2D parcel on it's provided name.

    Parameters:
    name (str): The name of the 2D parcel.
    source (str): The source of the 2D parcels table.

    Returns:
        str|None: The Global ID value if found, otherwise None.
    """

    if source == 'SDE':
        table: str = f'{CNFG.ParcelFabricDataset}{CNFG.OwnerName}Parcels2D'
    elif source == 'MAP':
        table: Layer = get_layer('חלקות')
    else:
        table: None = None
        AddError("Parameter ️'source' must be on of ['SDE', 'MAP']")

    if table:
        Scursor: Scur = SearchCursor(table, 'GlobalID', f""" Name = '{name}' AND RetiredByRecord IS NULL""")
        Scursor_len: int = cursor_length(Scursor)

        if Scursor_len == 1:
            ParcelGUID: str = Scursor.next()[0]
            return ParcelGUID
        if Scursor_len == 0:
            AddMessage(f'{timestamp()} | ⚠️ Parcel {name} does not exist or not active')
            return None
        if Scursor_len > 1:
            AddMessage(f'{timestamp()} | ⚠️ Found {Scursor_len} parcels named {name}')
            return None

        del Scursor, Scursor_len
    del table


def get_ActiveParcel3DGUID(name: str, source: Literal['MAP', 'SDE'] = 'MAP') -> str | None:
    """
    Returns the Global ID of an active 3D parcel on it's provided name.

    Parameters:
    name (str): The name of the 3D parcel.
    source (str): The source of the 3D parcels table.

    Returns:
        str|None: The Global ID value if found, otherwise None.
    """

    if source == 'SDE':
        table: str = f'{CNFG.ParcelFabricDataset}{CNFG.OwnerName}Parcels3D'
    elif source == 'MAP':
        table: Layer = get_layer('חלקות תלת-ממדיות')
    else:
        table: None = None
        AddError(f"{timestamp()} | Parameter ️'source' must be on of ['SDE', 'MAP']")

    if table:
        Scursor: Scur = SearchCursor(table, 'GlobalID', f""" Name = '{name}' AND RetiredByRecord IS NULL""")
        Scursor_len: int = cursor_length(Scursor)

        if Scursor_len == 1:
            ParcelGUID: str = Scursor.next()[0]
            return ParcelGUID
        if Scursor_len == 0:
            AddMessage(f'{timestamp()} | ⚠️ Parcel {name} does not exist or not active')
            return None
        if Scursor_len > 1:
            AddMessage(f'{timestamp()} | ⚠️ Found {Scursor_len} parcels named {name}')
            return None

        del Scursor, Scursor_len
    del table


def get_FinalParcel(temp_number: int, block_number: int, subblock_number: int = 0, process_guid: str|None = None) -> int|None:
    """
    Retrieves the final parcel number based on the temporary parcel number, block number, and subblock number.
    The search is referencing the filter sequence actions of the specific process ('פעולות בתכנית').

    Parameters:
        temp_number (int): The temporary parcel number.
        block_number (int): The block number.
        subblock_number (int, optional): The subblock number. Default is 0.
        process_guid (str or None): The process border Global ID to filter by.
                                    Relevant when searching in non-filtered SequenceAction table.
                                    Default is None.

    Returns:
        int: The final parcel number.
    """

    source_temp_name: str = f'{temp_number}/{block_number}/{subblock_number}'
    fields: list[str] = ['FromParcelFinal', 'FromParcelTemp', 'ToParcelTemp', 'ToParcelFinal', 'BlockNumber', 'SubBlockNumber', 'ToBlockNumber', 'ToSubBlockNumber', 'ActionType']

    if process_guid:
        pairs: df = DataFrame(SearchCursor(fr"{CNFG.ParcelFabricDatabase}SequenceActions", fields, f"CPBUniqueID = '{process_guid}'"), columns=fields)
    else:
        pairs: df = DataFrame(SearchCursor(get_table('פעולות בתכנית'), fields), columns=fields)

    # Preprocess actions table:
    pairs['FinalBlock'] = pairs['ToBlockNumber'].fillna(pairs['BlockNumber'])
    pairs['FinalSubBlock'] = pairs['ToSubBlockNumber'].fillna(pairs['SubBlockNumber'])
    pairs = pairs.astype('Int64')
    pairs['FinalBlockName'] = pairs['FinalBlock'].astype(str) + '/' + pairs['FinalSubBlock'].astype(str)

    pairs['TemporaryParcelName'] = pairs['ToParcelTemp'].astype(str) + '/' + pairs['FinalBlockName']

    pairs['FinaParcelName'] = pairs['ToParcelFinal'].astype(str) + '/' + pairs['FinalBlockName']

    # Filter to the input temporary parcel row
    pairs = pairs[pairs['TemporaryParcelName'] == source_temp_name]

    # Retrieve the final parcel number according to the action type:
    if len(pairs) > 0:
        parcel_action_type: int = int(pairs['ActionType'].unique()[0])

        if parcel_action_type == 2:  # merge action
            final_number: int = int(pairs['FinaParcelName'].unique().item().split('/')[0])

        elif parcel_action_type in [1, 3, 5]:  # Divide, Transfer, Create actions
            final_number: int = int(pairs['FinaParcelName'].item().split('/')[0])

        else:
            AddMessage(f'{timestamp()} | Source parcel {source_temp_name} is not included in the process actions')
            final_number: None = None

        return final_number

    del pairs, fields, source_temp_name


def get_StartPointGUID(line_geometry: Line, tolerance: float = 0.01) -> str | None:
    """
    Retrieves the Global ID of the start point of a given line geometry (Shape@) from the current border points layer.

    Parameters:
        line_geometry (Line): The line geometry for which to find the start point's Global ID.
        tolerance (float): The distance for the line starting point to find it's matched border point. Default is 0.01 meters.

    Returns:
        str | None: The Global ID of the start border point if found in the points layer, otherwise None.
    """

    first_x, first_y = line_geometry.firstPoint.X, line_geometry.firstPoint.Y
    reference_point: Polygon = PointGeometry(inputs = Point(first_x, first_y), spatial_reference = SpatialReference(2039)).buffer(tolerance)
    selection: Result = SelectByLocation(in_layer = get_layer('נקודות גבול'), overlap_type = 'INTERSECT', select_features = reference_point, search_distance = tolerance, selection_type = 'NEW_SELECTION')
    count: int = int(selection.getOutput(2))

    if count == 1:
        guid: str = SearchCursor(selection.getOutput(0), 'GlobalID').next()[0]
        return guid
    if count > 1:
        AddMessage(f'{timestamp()} |  ⚠️ Start point ({first_x}, {first_y}) matched multiple border points')
        return None
    if count == 0:
        AddMessage(f'{timestamp()} |  ⚠️ Start point ({first_x}, {first_y}) is not matching any border point')
        return None


def get_EndPointGUID(line_geometry: Line,  tolerance: float = 0.01) -> str | None:
    """
    Retrieves the Global ID of the start point of a given line geometry (Shape@) from the current border points layer.

    Parameters:
        line_geometry (Line): The line geometry for which to find the start point's Global ID.
        tolerance (float): The distance for the line starting point to find it's matched border point. Default is 0.01 meters.

    Returns:
        str | None: The Global ID of the end border point if found in the points layer, otherwise None.
    """

    last_x, last_y = line_geometry.lastPoint.X, line_geometry.lastPoint.Y
    reference_point: Polygon = PointGeometry(inputs = Point(last_x, last_y), spatial_reference = SpatialReference(2039)).buffer(tolerance)
    selection: Result = SelectByLocation(in_layer = get_layer('נקודות גבול'), overlap_type = 'INTERSECT', select_features = reference_point, search_distance = tolerance, selection_type = 'NEW_SELECTION')
    count: int = int(selection.getOutput(2))

    if count == 1:
        guid: str = SearchCursor(selection.getOutput(0), 'GlobalID').next()[0]
        return guid
    if count > 1:
        AddMessage(f'{timestamp()} |  ⚠️ Start point ({last_x}, {last_y}) matched multiple border points')
        return None
    if count == 0:
        AddMessage(f'{timestamp()} |  ⚠️ Start point ({last_x}, {last_y}) is not matching any border point')
        return None


def process_will_retire_its_block(ProcessName: str) -> bool|None:
    """
    Check whether a process resulting in retiring the block it is modifying by counting the active parcels remaining after the incoming parcels of the process will retire.
    Note: this check is not relevant for 3D cadastral processes or process that improve the active cadaster since they are not allowed to retire a block.

    Parameters:
        ProcessName (str): The name of the process to verify whether it's block will be retired.
    """

    # Get the retiring parcels of the process as a unified text to use in a query
    InProcessParcels2D: str = fr"{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessParcels2D"
    query: str = f"CPBUniqueID = '{get_ProcessGUID(ProcessName)}' And ParcelRole = 1"
    fields: list[str] = ['ParcelNumber', 'BlockNumber', 'SubBlockNumber']
    retired_parcel_of_process: Scur = SearchCursor(InProcessParcels2D, fields, query)

    # If the process has parcels to retire:
    if cursor_length(retired_parcel_of_process) > 0:
        retired_parcel_as_text: str = ",".join([f"'{i[0]}/{i[1]}/{i[2]}'" for i in retired_parcel_of_process])

        # Query the for active parcels of the block, excluding the retiring parcels pf the process
        Parcels2D: str = fr"{CNFG.ParcelFabricDataset}{CNFG.OwnerName}Parcels2D"
        query: str = f"""BlockUniqueID = '{get_BlockGUID("ProcessName", ProcessName)}' And RetiredByRecord Is Null And Name Not In ({retired_parcel_as_text})"""
        active_2D_Parcels: Scur = SearchCursor(Parcels2D, 'Name', query)
        active_2D_Parcels_count: int = cursor_length(active_2D_Parcels)

        del retired_parcel_of_process, active_2D_Parcels

        if active_2D_Parcels_count == 0:
            return True
        else:
            return False

    else:
        del retired_parcel_of_process
        return False





    #     # Validate against text file of retired 2D parcels
    #     active_2D_Parcels: set[str] = set(sorted([i[0] for i in active_2D_Parcels]))  # --> {'1/123/0', '2/123/0', ...}
    #     AddMessage(f"{active_2D_Parcels=}")
    #     txt_file: str = fr"{CNFG.Library}{ProcessName.replace('/', '_')}/RetiredParcels2D.txt"
    #     if exists(txt_file):
    #         retired_2D_parcels: str = open(txt_file, "r").read().strip('"')
    #         AddMessage(f"{retired_2D_parcels=}")
    #         retired_2D_parcels: set[str] = {i for i in retired_2D_parcels.replace("'", "").split(', ')}  # --> {'1/123/0', '2/123/0', ...}
    #         AddMessage(f"{retired_2D_parcels=}")
    #         if retired_2D_parcels == active_2D_Parcels:
    #             return False
    #         else:
    #             return True
    #     else:
    #         AddError(f'{timestamp()} | RetiredParcels2D.txt file in library was not found')
    #
    # else:
    #     return False



def process_is_transferring(ProcessName: str, source: Literal['MAP', 'SDE'] = 'MAP') -> bool:
    """
    Check if a process includes transfer action.

    Parameters:
        ProcessName (str): The name of the process to check.
        source (str): The source of the table to query. Must be either 'MAP' or 'SDE'.
    """
    table: Table|str = get_table('פעולות בתכנית') if source == 'MAP' else fr'{CNFG.ParcelFabricDatabase}\{CNFG.OwnerName}.SequenceActions'
    query: str = "ActionType = 3" if source == 'MAP' else f"ActionType = 3 AND CPBUniqueID = '{get_ProcessGUID(ProcessName, source)}'"

    Actions: Scur = SearchCursor(table, 'ActionType', query)
    count: int = cursor_length(Actions)
    del Actions

    if count > 0:
        return True
    else:
        return False


def process_only_creates(ProcessName: str) -> bool:
    """
    Check if a (Tamar) process includes only creation action.

    Parameters:
        ProcessName (str): The name of the (Tamar) process to check.
    """

    table: str = fr'{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}SequenceActions'
    table: Scur = SearchCursor(table, 'ActionType', f"CPBUniqueID = '{get_ProcessGUID(ProcessName)}'")
    action_types: set[int] = {a[0] for a in table}
    del table

    if action_types == {5}:  # Create action type
        return True
    else:
        return False


def process_is_establish_block(ProcessName: str, source: Literal['MAP', 'SDE'] = 'MAP') -> bool|None:
    """
    Check whether a process with a transfer action leads to preplanned block to establish
    Note: this check is not relevant for 3D cadastral processes since they are not allowed to create a block.
    """
    if process_is_transferring(ProcessName, source):
        ProcessGUID: str = get_ProcessGUID(ProcessName, source)
        InProcessParcels2D: str = f'{CNFG.ParcelFabricDatabase}{CNFG.OwnerName}InProcessParcels2D'
        blocks_search = SearchCursor(InProcessParcels2D, 'BlockUniqueID', f""" CPBUniqueID = '{ProcessGUID}' AND ParcelRole = 2 """)
        blocks_guids: list[str] = [row[0] for row in blocks_search]
        blocks_statuses: list[int] = [get_BlockStatus('GlobalID', guid) for guid in blocks_guids]
        del ProcessGUID, blocks_search, blocks_guids, InProcessParcels2D

        if 13 in blocks_statuses:
            return True
        else:
            return False


def get_AbsorbingBlockGUIDs() -> list[str] | None:
    """
    Retrieves the Global IDs for blocks that absorb new parcels following a transfer action (3) in the currently edited process.
    If there is only one unique block, the function returns a list containing the GUID for that block.
    If there are multiple unique blocks, the function returns a list of GUIDs for all unique blocks.

    Returns:
        list[str]: A list of unique Global IDs for the resulting  blocks.
    """

    process_actions: Table = get_table('פעולות בתכנית')
    block_cols: list[str] = ['ToBlockNumber', 'ToSubBlockNumber']
    blocks_df: df = DataFrame(data = SearchCursor(process_actions, block_cols, 'ActionType = 3'), columns = block_cols).astype(int)
    blocks_df['Name'] = blocks_df['ToBlockNumber'].astype(str) + '/' + blocks_df['ToSubBlockNumber'].astype(str)
    names: list[str] = blocks_df['Name'].unique().tolist()
    total: int = len(names)

    if total == 1:
        guids: str = get_BlockGUID(by= 'BlockName', name = names[0])
        return [guids]

    if total > 1:
        guids: list[str] = []
        for name in names:
            guids.append(get_BlockGUID(by= 'BlockName', name = name))
        return guids

    if total < 1:
        AddError('No absorbing Blocks found for the transfer action')
        return None


def remove_intermediate_vertices(layer: Layer) -> None:
    """
    Removes intermediate vertices from multiline geometries in the specified layer,
    ensuring each line contains only two vertices of start & end.

    Parameters:
    - layer (str): The name or path of the input feature layer or feature class containing multiline geometries.

    """
    vertices_cursor: Ucur = UpdateCursor(layer, ['GlobalID', 'SHAPE@WKT'])

    for row in vertices_cursor:
        line_ID: str = row[0]
        line_geometry: str = row[1]

        vertices: list = line_geometry.split(',')
        vertices_count: int = len(vertices)

        if vertices_count > 2:
            AddMessage(f'{timestamp()} | ⚠️ Front {line_ID} contains {vertices_count} vertices when 2 are allowed. \n ' +\
                       'Removing intermediate vertices...')
            match: list[str] = re.search(r'\(\((.*?)\)\)', line_geometry).group(1).split(',')
            start_coord, end_coord = match[0], match[-1]
            row[1]: str = f'MULTILINESTRING (({start_coord}, {end_coord}))'
            vertices_cursor.updateRow(row)

    del vertices_cursor


def delete_file(file_path: str) -> None:
    """Deletes a file if exist"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        AddMessage(f"An error occurred: {str(e)}")


def load_to_records_(ProcessName: str) -> None:
    """
     -- DEPRECATED --
    Copies an input process border and it's attributes from CadasterProcessBorders layer to CadasterRecordsBorder layer.
    The CadasterRecordsBorder layer here should be under version.

    Parameters:
        ProcessName (str): The name of the process border to load into Records.
    """
    current_map: Map = ArcGISProject('current').activeMap
    processes_layer: Layer = current_map.listLayers('גבולות תהליכי קדסטר')[0]
    records_layer: Layer = current_map.listLayers('גבולות רישומים')[0]    # -->> At this moment the record layer is under new edit version
    del current_map

    field_mapping: str = fr'Name "שם מפה" true true true 255 Text 0 0,First,#,{processes_layer.name},ProcessName,0,100;' + \
                         fr'RecordType "סוג תהליך" true true true 4 Long 0 0,First,#,{processes_layer.name},ProcessType,-1,-1;' + \
                         fr'GeodeticNetwork "רשת בקרה" true true false 2 Short 0 0,First,#,{processes_layer.name},GeodeticNetwork,-1,-1;' + \
                         fr'Status "סטטוס" true true false 2 Short 0 0,First,#,{processes_layer.name},Status,-1,-1;' + \
                         fr'SurveyorLicenseID "רשיון מודד" true true false 2 Short 0 0,First,#,{processes_layer.name},SurveyorLicenseID,-1,-1;' + \
                         fr'DataSource "מקור הנתונים" true true false 2 Short 0 0,First,#,{processes_layer.name},DataSource,-1,-1;' + \
                         fr'PlanName "תכנית מפורטת" true true false 255 Text 0 0,First,#,{processes_layer.name},PlanName,0,255;' + \
                         fr'BlockUniqueID "מזהה גוש" true true false 38 Guid 0 0,First,#,{processes_layer.name},BlockUniqueID,-1,-1'

    Append(processes_layer, records_layer, "NO_TEST", field_mapping, expression= f"ProcessName = '{ProcessName}'", feature_service_mode= 'USE_FEATURE_SERVICE_MODE')


    del processes_layer, field_mapping
    AddMessage(f'{timestamp()} | ⚡ Process {ProcessName} loaded as a new record')
    reopen_map()
    RefreshLayer(records_layer)


def load_to_records(ProcessName: str) -> None:
    """
    Copies an input process border and it's attributes from CadasterProcessBorders layer to CadasterRecordsBorder layer.
    The CadasterRecordsBorder layer here should be under version.

    Parameters:
        ProcessName (str): The name of the process border to load into Records.
    """

    process_fields: list[str] = ['ProcessName', 'ProcessType', 'GeodeticNetwork', 'Status', 'SurveyorLicenseID', 'DataSource', 'PlanName', 'BlockUniqueID', 'Shape@']
    process_data: Scur = SearchCursor(get_layer('גבולות תהליכי קדסטר'), process_fields, f"ProcessName = '{ProcessName}'")

    record_fields: list[str] = ['Name', 'RecordType', 'GeodeticNetwork', 'Status', 'SurveyorLicenseID', 'DataSource', 'PlanName', 'BlockUniqueID', 'Shape@']
    target_table: Icur = InsertCursor(get_layer('גבולות רישומים'), record_fields)
    if cursor_length(process_data) == 1:
        for row in process_data:
            target_table.insertRow(row)

    del process_fields, process_data, target_table
    AddMessage(f'{timestamp()} | ⚡ Process {ProcessName} loaded as a new record')
    reopen_map()
    refresh_map_view()

    # Save the new record Global ID in a text file
    new_guid: str = SearchCursor(get_layer('גבולות רישומים'), 'GlobalID', f"Name = '{ProcessName}'").next()[0]
    text_file: str = fr"{CNFG.Library}{ProcessName.replace('/', '_')}/RecordGUID.txt"
    delete_file(text_file)
    with open(text_file, "w") as f:
        f.write(new_guid)


def rewrite_record_data(ProcessName: str) -> None:
    """
    Updates record data in the CadasterRecordBorders layer based on (newer) data from the CadastreProcessBorders layer.

    This function retrieves specific fields from the cadastre process boundaries layer
    and updates corresponding records in the record borders layer where `ProcessName` matches.

    Parameters:
        ProcessName (str):  The name of the process used as a filter to identify relevant records.
    """
    fields_to_update: list[str] = ['BlockUniqueID', 'GeodeticNetwork', 'SurveyorLicenseID', 'DataSource', 'PlanName', 'Shape@']
    new_data: tuple[Any, ...] = SearchCursor(get_layer('גבולות תהליכי קדסטר'), fields_to_update, f" ProcessName = '{ProcessName}' ").next()

    editor: Editor = start_editing(ENV.workspace)
    records_layer = get_layer('גבולות רישומים')
    record_data: Ucur = UpdateCursor(records_layer, fields_to_update, f" Name = '{ProcessName}' ")
    for row in record_data:
        row = new_data
        record_data.updateRow(row)

    stop_editing(editor); RefreshLayer(records_layer); reopen_map('מפת עריכה');

    del new_data, record_data, records_layer, editor
    AddMessage(f'{timestamp()} | ⚡ Record {ProcessName} data updated')


def activate_record(ProcessName: str, map_name: MapType = 'Active map') -> None:
    """
    Activate a record in an ArcGIS Pro map.
    This function retrieves the GlobalID (RecordGUID) of the specified process  from either the "MAP" or "SHELF" sources.
    After a valid RecordGUID is found, it sets the record as the active record in the parcel fabric of the specified map.
    The function also updates the project, closes map views, reopens the map, and logs a status message.

    Parameters:
        ProcessName (str): The name of the process whose record should be activated.
        map_name (MapType, optional): The name of the map in which to activate the record.
                                      Defaults to "Active map".
    """

    RecordGUID: str|None = get_RecordGUID(ProcessName, source="MAP")

    if not RecordGUID:
        RecordGUID: str = get_RecordGUID(ProcessName, source="SHELF")

    current_project: Pro = ArcGISProject('current')
    map_object: Map = current_project.activeMap if map_name == 'Active map' else current_project.listMaps(map_name)[0]
    pf_layer: Layer = map_object.listLayers('רישומים')[0]
    CIM: parcelCIM = pf_layer.getDefinition('V3')
    CIM.parcelFabricActiveRecord.activeRecord = RecordGUID
    CIM.parcelFabricActiveRecord.enabled = True
    pf_layer.setDefinition(CIM)

    current_project.save(); current_project.closeViews('MAPS'); map_object.openView();

    AddMessage(f'{timestamp()} | ✔️ Record {ProcessName} activated')


def deactivate_record(map_name: MapType = 'Active map') -> None:
    """Deactivate the current active record """

    current_project: Pro = ArcGISProject('current')
    map_object: Map = current_project.activeMap if map_name == 'Active map' else current_project.listMaps(map_name)[0]
    records: Layer = map_object.listLayers('רישומים')[0]
    CIM: parcelCIM = records.getDefinition('V3')
    current_active: str|None = CIM.parcelFabricActiveRecord.activeRecord

    if current_active:
        CIM.parcelFabricActiveRecord.enabled = False
        records.setDefinition(CIM)
        current_project.save(); current_project.closeViews('MAPS'); map_object.openView(); refresh_map_view();
        AddMessage(f'{timestamp()} | ✔️ Record deactivated')
    else:
        AddMessage(f'{timestamp()} | ⚠️ No record is currently active')


def get_ActiveRecord(value: Literal['Name', 'GUID'] = 'Name') -> str|None:
    """
    Retrieves the active record's name or GUID from the records layer in the Parcel Fabric.
    This function accesses the records layer, identifies the currently active record in the Parcel Fabric, and returns either its GUID or its Name field value,
    depending on the requested output.

    Parameters:
        value (Literal['Name', 'GUID']): Specifies the type of information to return.
                                         - 'GUID': Returns the GlobalID of the active record.
                                         - 'Name': Returns the Name of the active record. This is the default.

    Returns:
        str|None:
            The requested information (Name or GUID) if an active record exists; otherwise, None.

    """

    active_record: parcelCIM = get_layer('רישומים').getDefinition('V3').parcelFabricActiveRecord
    active_record_guid: str|None = active_record.activeRecord

    if active_record.enabled:

        if value == 'GUID':
            return active_record_guid
        elif value == 'Name':
            Name: str|None = SearchCursor(get_layer('גבולות רישומים'), 'Name', f"GlobalID = '{active_record_guid}'").next()[0]
            return Name
    else:
        AddError(f"{timestamp()} | Activate the relevant record before running this step")
        return None

    del active_record, active_record_guid


def Type2CreateType(Type: int) -> int | None:
    """ Convert ProcessType domain value to it's CreateProcessType domain value """

    mapping: dict[int, int] = {1: 1,    # Tazar
                               2: 5,    # Tamar
                               3: 2,    # Judgement
                               9: 3,    # BlockRegulation
                               11: 4,   # UnregisteredTazar
                               16: 16}  # FreeEdit

    if Type not in mapping.keys():
        AddError(f'ProcessType {Type} must be on of {list(mapping.keys())}')
        return None
    else:
        create_type: int = mapping[Type]
        return create_type


def Type2CancelType(Type: int) -> int | None:
    """ Convert ProcessType domain value to it's CancelProcessType domain value """

    mapping: dict[int, int] = {1: 1,    # Tazar
                               2: 4,    # Tamar
                               3: 2,    # Judgement
                               9: 5,    # BlockRegulation
                               11: 3,   # UnregisteredTazar
                               16: 16}  # FreeEdit

    if Type not in mapping.keys():
        AddError(f'ProcessType {Type} must be on of {list(mapping.keys())}')
        return None
    else:
        cancel_type: int = mapping[Type]
        return cancel_type


def zoom_to_aoi(map_name: MapType = 'Active map') -> None:
    """ Zoom-in the canvas camera view to the area of interest (the process border feature) """

    current_camera = ArcGISProject('current').activeView.camera
    aoi_layer: Layer = get_layer('*גבול תכנית', map_name)
    aoi_extent: Extent = SearchCursor(aoi_layer, 'SHAPE@').next()[0].extent

    if aoi_extent:
        current_camera.setExtent(aoi_extent)
        del aoi_extent
    else:
        AddError('No extent to zoom-in')


def zoom_to_layer(layer_name: str) -> None:
    """
    Zoom-in the active map camera view to the layer by a given layer name

    Parameters:
        layer_name(str): The name of the layer in the active map to zoom-in.
    """

    current_camera = ArcGISProject('current').activeView.camera
    extent = get_LayerExtent(layer_name)

    if extent:
        current_camera.setExtent(extent)
        del extent, current_camera
    else:
        AddError('No extent to zoom-in')
        del current_camera


def get_LayerExtent(layer_name: str) -> Extent|None:
    """
    Returns an Extent object of a layer, in the currently active map

    Parameters:
        layer_name(str): The name of the layer in the active map.
    """
    extent_list: list[Extent] = [geom[0].extent for geom in SearchCursor(get_layer(layer_name), 'SHAPE@') if geom[0]]

    if extent_list:
        min_x = min(ext.XMin for ext in extent_list)
        max_x = max(ext.XMax for ext in extent_list)
        min_y = min(ext.YMin for ext in extent_list)
        max_y = max(ext.YMax for ext in extent_list)

        layer_extent: Extent = Extent(min_x, min_y, max_x, max_y)
        return layer_extent


def get_AOIExtent() -> Extent:
    """
    Returns the area of interest Extent object
    """
    zoom_to_aoi()
    aoi_extent: Extent = ArcGISProject("current").activeView.camera.getExtent()

    return aoi_extent


def get_display_extent() -> Extent:
    """Returns the current extent of the active map"""
    current_extent: Extent = ArcGISProject('current').activeView.camera.getExtent()
    return current_extent


def AddDefinitionQuery(layer, query: dict) -> None:
    """ Adds a single definition query """
    queries: list[dict[str, Any]] = layer.listDefinitionQueries()

    if query['isActive']:
        for q in queries:
            q['isActive'] = False

    queries.append(query)
    layer.updateDefinitionQueries(queries)


def filter_to_aoi(ProcessName: str, map_name: MapType = 'Active map') -> None:
    """
    Reduces the display view by filtering the cadastral layers based on the regions of all blocks
    borders intersecting the process.

    Parameters:
        ProcessName (str): The name of the process to filter by.
        map_name (MapType): The name of the map object to use.  Default is the currently active map view ("Active map").
    """

    aoi_map: Map = ArcGISProject("current").activeMap if map_name == 'Active map' else ArcGISProject("current").listMaps(map_name)[0]
    process_layer: Layer = aoi_map.listLayers('גבול תכנית')[0]
    blocks_layer: Layer = aoi_map.listLayers('גושים')[0]
    name: str = 'Area of Interest'

    RecordGUID: str|None = get_RecordGUID(ProcessName, 'SDE', False)
    if not RecordGUID:
        RecordGUID: str = get_RecordGUID(ProcessName, 'SHELF', False)


    # Get blocks guids:
    aoi_blocks_layer: Layer = SelectByLocation(in_layer= blocks_layer, select_features= process_layer, overlap_type= 'INTERSECT', search_distance="1 Meter")
    aoi_blocks: Scur = SearchCursor(aoi_blocks_layer, 'GlobalID', "RetiredByRecord IS NULL")
    aoi_blocks: str = ', '.join(["'" + row[0] + "'" for row in aoi_blocks])
    del process_layer, aoi_blocks_layer

    if get_ProcessType(ProcessName) not in [9, 15]:  # תנאי לתהליכים מסוג הסדר מקרקעין ותת"ג להסדר מקרקעין משום שאין להם פעולות בטבלת סדר פעולות
        if process_is_establish_block(ProcessName):
            AbsorbingBlocks: str = ', '.join(["'" + guid + "'" for guid in get_AbsorbingBlockGUIDs()])
            aoi_blocks: str = f'{aoi_blocks}, {AbsorbingBlocks}'
            del AbsorbingBlocks

    aoi_map.clearSelection()

    # Filter active blocks layer
    query_params: dict[str, Any] = {'name': name, 'sql': f"RetiredByRecord IS NULL AND GlobalID IN ({aoi_blocks})", 'isActive': True}
    AddDefinitionQuery(blocks_layer, query_params)
    RefreshLayer(blocks_layer)

    # Get aoi polygon geometry from filtered blocks layer:
    Dissolve(blocks_layer, r"memory\aoi")
    aoi_blocks_geom: Polygon = SearchCursor(r"memory\aoi", "Shape@").next()[0]
    spatial_clause: list[dict[str, Polygon]] = [{'geometry': aoi_blocks_geom}]
    del blocks_layer


    # Filter active 2D parcels, 3D parcels and substractions layers
    query_params: dict[str, Any] = {'name': name, 'sql': f"RetiredByRecord IS NULL AND BlockUniqueID IN ({aoi_blocks})", 'isActive': True}
    for layer_name in ['חלקות', 'חלקות תלת-ממדיות', 'גריעות']:
        layer: Layer = aoi_map.listLayers(layer_name)[0]
        AddDefinitionQuery(layer, query_params)


    # Filter active 2D points, active 3D points, and active fronts layers
    query_params: dict[str, Any] = {'name': name, 'sql': f"RetiredByRecord IS NULL OR CreatedByRecord = '{RecordGUID}'", 'spatialClause': spatial_clause, 'isActive': True}

    for layer_name in ['נקודות גבול', 'נקודות גבול תלת-ממדיות', 'חזיתות']:
        layer: Layer = aoi_map.listLayers(layer_name)[0]
        AddDefinitionQuery(layer, query_params)


    # Filter control points
    control_points_layer: Layer = aoi_map.listLayers('נקודות בקרה')[0]
    query_params: dict[str, Any] = {'name': name, 'spatialClause': spatial_clause, 'isActive': True}
    AddDefinitionQuery(control_points_layer, query_params)
    del control_points_layer


    # Filter QA layers
    validation_names: list[str] = ['קווי אימות' , 'נקודות אימות', 'שטחי אימות']
    topology_names: list[str] = ['שגיאות מסוג פוליגון' , 'שגיאות מסוג קו' , 'שגיאות מסוג נקודה' , 'אזורים לא חוקיים']
    qa_names: list[str] = validation_names + topology_names
    qa_layers: list[Layer] = [layer for layer in aoi_map.listLayers() if layer.name in qa_names]
    query_params: dict[str, Any] = {'name': name, 'spatialClause': spatial_clause, 'isActive': True}
    for layer in qa_layers:
        AddDefinitionQuery(layer, query_params)
    del validation_names, topology_names, qa_names, qa_layers


    # Filter Retired Cadastral layers:
    query_params: dict[str, Any] = {'name': name, 'sql': "RetiredByRecord IS NOT NULL", 'spatialClause': spatial_clause, 'isActive': True}
    for layer_name in ['גושים מבוטלים', 'חלקות מבוטלות', 'חלקות תלת-ממדיות מבוטלות', 'גריעות מבוטלות', 'נקודות גבול מבוטלות', 'נקודות גבול תלת-ממדיות מבוטלות', 'חזיתות מבוטלות']:
        layer: Layer = aoi_map.listLayers(layer_name)[0]
        AddDefinitionQuery(layer, query_params)


    # Filter active projected 3D parcels and projected substractions (scene map)
    query_params: dict[str, Any] = {'name': name, 'spatialClause': spatial_clause, 'isActive': True}
    for layer_name in ['היטלי חלקות תלת-ממדיות', 'היטלי גריעות']:
        layer: Layer = aoi_map.listLayers(layer_name)[0]
        AddDefinitionQuery(layer, query_params)

    del query_params, spatial_clause, aoi_map, RecordGUID, aoi_blocks


def respond_to_CMS(ProcessName: str, ProcessType: int, ProjectStatus: Optional[int] = 1) -> None:
    """
    Responds to the Cadaster Management System (CMS) by constructing a URL based on the provided parameters
    and making a GET request to that URL. The function handles different types of processes, and it logs
    the outcome or any errors encountered during the request.

    Parameters:
        ProcessName (str): A string representing the name of the process.
                           It should be in the format "BlockNumber/SubBlockNumber" for ProcessType 5 or 9, and "ProcessNumber/ProcessYear" for other ProcessTypes.
        ProcessType (int): An integer representing the type of the process.
                           Special handling is applied for ProcessType 5 and 9.
        ProjectStatus (int, optional): An integer representing the status of the project.
                                       Value of 1 will assign the project as Editing Completed, This is the default.
                                       Any other value will assign the project as Completed With No Edits.

    Raises:
    - requests.exceptions.HTTPError:
        If the GET request results in an HTTP error (4xx or 5xx status codes).
    - Exception:
        For any other exceptions that occur during the execution of the function.
    """
    AddMessage(f'\n ⭕ Sending feedback to CMS \n')

    if ProcessType in [5, 9]:  # -> Block regulation or Coordinates based cadastre
        SubBlockNumber: str = ProcessName.split("/")[1]
        SubBlockNumber: str = '0' + SubBlockNumber if len(SubBlockNumber) == 1 else SubBlockNumber

        BlockNumber: str = ProcessName.split("/")[0]
        to_pad: int = 8 - len(BlockNumber)  # -> 8 is total 10 characters minus 2 characters of SubBlockNumber
        if to_pad > 0:
            BlockNumber: str = '0' * to_pad + BlockNumber

        ProcessNumber: str = f'{BlockNumber}{SubBlockNumber}'
        ProcessYear: str = '0'
    else:
        ProcessNumber: str = ProcessName.split("/")[0]
        ProcessYear: str = ProcessName.split("/")[1]

    url: str = f'{CNFG.CMS_url}{ProcessNumber}/{ProcessYear}/{ProcessType}/{ProjectStatus}'

    try:
        r = requests.get(url)
        r.raise_for_status()    # Raises an HTTPError for bad responses (4xx and 5xx)
        AddMessage(f'{timestamp()} | ✅ Responded to CMS')

    except requests.exceptions.HTTPError as e:
        if r.status_code == 404:
            AddMessage(f"{timestamp()} | ❌ Error: The URL {url} was not found or not valid")
        else:
            AddMessage(f"{timestamp()} | ❌ Error: HTTP error occurred: {e}")
            AddMessage(f"{timestamp()} | ❌ Error url: {url}")

    except Exception as e:
        AddMessage(f"{timestamp()} | ❌ Error: An error occurred: {e}")
        AddMessage(f"{timestamp()} | ❌ Error url: {url}")


def get_aprx_name(aprx_path: str = 'current') -> str:
    """
    Returns the name of the aprx file, replacing the '-' character with '/' to align with a process name convection
    used to automatically get the process name that the aprx file was meant for.

    Parameters:
        aprx_path (str, Optional): The path to the aprx file.
    """

    aprx_name: str = ArcGISProject(aprx_path).filePath\
                                             .split("\\")[-1]\
                                             .split(".")[0]\
                                             .replace("_", "/")

    return aprx_name
