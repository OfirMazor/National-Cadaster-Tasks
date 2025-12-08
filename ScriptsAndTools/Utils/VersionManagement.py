import os, csv
from shutil import copy as copyfile
from Utils.TypeHints import *
from Utils.Configs import CNFG
from Utils.Helpers import timestamp, get_layer, get_table, get_active_user, get_ActiveRecord
from arcpy import AddMessage, AddError, ListVersions
from arcpy.mp import ArcGISProject
from arcpy.management import CreateVersion, ChangeVersion, ReconcileVersions


def generate_version_name(ProcessName: str) -> str:
    """
    Generates a new version name based on the provided process name.

    Parameters:
        ProcessName (str): The name of the process for which the version is being generated.

    Returns:
        str: The generated version name.

    This function generates a new version name by appending the user's name and a version number to the provided process name.
    It retrieves existing versions from the ParcelFabricDatabase, extracts the version numbers, and selects the maximum
    version number for the provided process name. Then, it increments this number by one to generate a new version name.
    If no existing versions are found for the given process name, it starts the version number from 0.
    """

    user: str|None = get_active_user()
    versions_list: list[str] = [v.split('.')[-1] for v in ListVersions(CNFG.ParcelFabricDatabase)]     # Splitting the full name such as 'PF_EDIT_BANKALMODDEV.ofir@MM_NT_MALI.1637/2023_ofir_0' into 1637/2023_ofir_0
    versions: list[int] = [int(v.split('_')[-1]) for v in versions_list if v.startswith(ProcessName)]  # Splitting the name such as ['1637/2023_ofir_0', '1637/2023_ofir_1', '1637/2023_ofir_2'] into [0,1,2...]

    if versions:
        last: int = max(versions)
        new_version: str = f'{ProcessName}_{user}_{last + 1}'
    else:
        last: int = 0
        new_version: str = f'{ProcessName}_{user}_{last}'

    return new_version


def get_VersionGUID(layer_name: str) -> str:
    """Returns the Global ID of a Version from a layer in the currently active map"""

    layer: Layer = ArcGISProject("current").activeMap.listLayers(layer_name)[0]
    connection_properties: dict[str, Any] = layer.connectionProperties
    VersionGUID: str = connection_properties['connection_info']['versionguid']
    return VersionGUID


def get_VersionName(name: str, source: Literal['layer', 'table'] = 'layer') -> str | None:
    """
    Returns the name of a version from a layer in the currently active map

    Parameters:
        name (str): The name of the layer or table in the active map.
        source (Literal['layer', 'table']): the source of the object name to look for in the function. Default is 'layer'.
    """

    obj: Layer|Table|None = get_layer(name) if source == 'layer' else get_table(name)
    if obj:
        connection_properties: dict[str, Any] = obj.connectionProperties
        VersionName: str = connection_properties['connection_info']['version']
        return VersionName
    else:
        return None


def layer_is_at_version(name: str, error: bool = False) -> bool:
    """
    Check if a layer is at a specific version or at the default version.

    Parameters:
        name (str): The name of the layer to check.
        error (bool): Whether to log error message if layer is currently not under branch version. default is False.

    Returns:
        bool: True if the layer is at a specific version (not default),
              False if the layer is at the default version ("sde.DEFAULT").
    """
    if get_VersionName(name) != "sde.DEFAULT":
        return True

    else:
        if error:
            AddError(f"{timestamp()} | Layer {name} must be under the relevant branch version")
        return False


def open_version(ProcessName: str) -> None:
    """
    Creates a new version in a geodatabase and transfer the Dataset layers their error layers to the new version created.
    The new version name will be appended to a csv file in the process library.

    Parameters:
        ProcessName (str): The name of the process for which the version will be created.
    """
    AddMessage(f'\n ⭕ Creating environment:')

    user: str|None = get_active_user()
    version_name: str = generate_version_name(ProcessName)
    version_full_name: str = f'{user}@MM_NT_MALI.{version_name}'
    version_suffix: str = version_name.split('_')[-1]
    CreateVersion(in_workspace= CNFG.ParcelFabricFeatureServer, parent_version= "sde.DEFAULT", version_name= version_name, access_permission= 'PUBLIC')

    # Document the version in a CSV file
    shelf: str = f'{CNFG.Library}{ProcessName.replace("/", "_")}'
    if not os.path.exists(fr'{shelf}\Versions.csv'):
        copyfile(fr'{CNFG.TemplatesPath}Versions.csv', fr'{shelf}\Versions.csv')
    with open(fr'{shelf}\Versions.csv', mode='a', newline='') as version_csv:
        writer = csv.writer(version_csv)
        writer.writerow([user, version_name, version_full_name, version_suffix])

    # Change layers version
    layers: list[str] = ['רישומים', 'גריעות', 'גריעות מבוטלות', 'חלקות תלת-ממדיות', 'חלקות תלת-ממדיות מבוטלות',
                         'נקודות גבול תלת-ממדיות', 'נקודות גבול תלת-ממדיות מבוטלות', 'היטלי חלקות תלת-ממדיות', 'היטלי גריעות']
    for name in layers:
        ChangeVersion(in_features= get_layer(name),
                      version_type= 'BRANCH',
                      version_name= version_full_name,
                      include_participating= "INCLUDE" if name == 'רישומים' else "EXCLUDE")

    ChangeVersion(in_features= get_table('טבלת אימות'), version_type= "BRANCH", version_name= version_full_name)

    AddMessage(f'{timestamp()} | ✨ New edit version created: {version_name} ')


def close_version() -> None:
    """
    Reconcile and post changes from the current branch version to the "sde.DEFAULT" version in an ArcGIS geodatabase.
    A record must be activated in order to retrieve the process library.
    """

    ProcessName: str|None = get_ActiveRecord('Name')

    AddMessage(f'\n ⭕ Reconciling & posting edits: \n ')

    if ProcessName:
        shelf: str = fr'{CNFG.Library}{ProcessName}'
        version: str = get_VersionName('רישומים')
        log_file: str = fr'{shelf}\ReconcileAndPostLog_{version}.txt'

        AddMessage(f'{timestamp()} | 💡 Version {version} will be reconciled')
        results: Result = ReconcileVersions(input_database = CNFG.ParcelFabricFeatureServer,
                                            reconcile_mode = "ALL_VERSIONS",  # For branch workspace - the only valid option is all versions.
                                            target_version = "sde.DEFAULT",
                                            edit_versions = version,
                                            acquire_locks = "NO_LOCK_ACQUIRED",  # For branch workspace - locks are not acquired during the reconcile process.
                                            abort_if_conflicts = "NO_ABORT",
                                            conflict_definition = "BY_OBJECT",
                                            conflict_resolution = "FAVOR_EDIT_VERSION",
                                            with_post = "POST",
                                            with_delete = "KEEP_VERSION",
                                            out_log = log_file,
                                            proceed_if_conflicts_not_reviewed = "PROCEED",
                                            reconcile_checkout_versions = "DO_NOT_RECONCILE")  # This parameter is not applicable to branch versioning.

        log_results: str = results.getMessages(1)
        if "Error" not in log_results:
            AddMessage(f'{timestamp()} | ✔️ Version {version} posted')
        else:
            AddError(f'{timestamp()} | ❌ Version {version} was not posted. Review the log file.')
            AddMessage(f'{timestamp()} | Message: {log_results}')
            os.startfile(log_file)

        del results, log_results, log_file, version, shelf
