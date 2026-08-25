# Configurations and variables — TEMPLATE
#
# Configs.py is git-ignored because it holds internal host names, IP addresses and
# share paths. To set up a working copy:
#   1. Copy this file to Utils/Configs.py
#   2. Fill in every <placeholder> with the values for your deployment
#   3. Set Environment to the environment this copy serves
# Keep this template in sync whenever a new configuration key is added to Configs.py.
from Utils.TypeHints import EnviType


class CNFG:
    """This class holds configuration variables for various project paths and settings."""

    Environment: EnviType = '<EnviType>'
    OwnerName: str = '<OwnerName>'

    # Folders
    SDEFolder: str = fr"\\<file-server>\<share>\SDE/"
    ParcelFabricFolder: str = fr"\\<file-server>\<share>\Parcel Fabric/"
    ScriptsPath: str = f'{ParcelFabricFolder}{Environment}Environment\ScriptsAndTools/'
    TasksPath: str = f'{ParcelFabricFolder}{Environment}Environment\Tasks/'
    Library: str = f'{ParcelFabricFolder}{Environment}Environment\Library/'
    LayerFiles: str = f'{ParcelFabricFolder}{Environment}Environment\Layers/'
    TemplatesPath: str = f'{ParcelFabricFolder}{Environment}Environment\Templates/'


    # Data Sources
    SDE_mapping: dict[EnviType, str] = {"Development": "Dev", "Test": "Test", "Production": "Prod"}
    SDE: str = SDE_mapping[Environment]
    ParcelFabricDatabase: str = f"{SDEFolder}<sde-connection-file-prefix>{SDE}(pf).sde/"
    ParcelFabricDataset: str = fr'{ParcelFabricDatabase}{OwnerName}ParcelFabricDataset/'


    # Portal variables
    feature_service_mapping: dict[EnviType, list[str]] = {'Development': ['<FabricMapDev>', '<InProcessMapDev>'],
                                                          'Test':        ['<FabricMapTest>', '<InProcessMapTest>'],
                                                          'Production':  ['<FabricMapProd>', '<InProcessMapProd>']}

    portal_servers_names: dict[EnviType, str] = {"Development": "<dev-portal-host>",
                                                 "Test":        "<test-portal-host>",
                                                 "Production":  "<prod-portal-host>"}

    portal_mapping: dict[EnviType, str] = {"Development": f"{portal_servers_names[Environment]}/arcgis",
                                           "Test":        f"{portal_servers_names[Environment]}/arcgis",
                                           "Production":  f"{portal_servers_names[Environment]}/server"}


    portal_url: str = fr"https://{portal_mapping[Environment]}/rest/services/"
    FeatureServers: list[str] = feature_service_mapping[Environment]
    ParcelFabricFeatureServer: str = fr"{portal_url}<ServiceFolder>/{FeatureServers[0]}/FeatureServer"
    InProcessFeatureServer: str = fr"{portal_url}<ServiceFolder>/{FeatureServers[1]}/FeatureServer"
    gis_url: str = fr"https://{portal_servers_names[Environment]}/portal/sharing/rest"
    version_manager_url: str = f"{portal_url}<ServiceFolder>/{FeatureServers[0]}/VersionManagementServer"


    # CMS variables
    CMS_url_mapping: dict[EnviType, str] = {"Development": "http://<dev-cms-host>:<port>/manage/api/<endpoint>",
                                            "Test":        "http://<test-cms-host>:<port>/manage/api/<endpoint>",
                                            "Production":  "http://<prod-cms-host>:<port>/manage/api/<endpoint>"}

    CMS_url: str = CMS_url_mapping[Environment]

    # Others
    default_version_guids: dict[EnviType, str] = {"Development": "{<default-version-guid>}",
                                                  "Test": None,  # TODO
                                                  "Production": "{<default-version-guid>}"}

    default_version_guid: str = default_version_guids[Environment]

    domain: str = "@<organization-domain>"
