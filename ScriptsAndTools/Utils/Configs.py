# Configurations and variables
from Utils.TypeHints import EnviType


class CNFG:
    """This class holds configuration variables for various project paths and settings."""

    Environment: EnviType = 'Production'
    OwnerName: str = 'PF.'

    # Folders
    SDEFolder: str = "<folder-with-sde's>"
    ParcelFabricFolder: str = "<main-workspace-folder>"
    ScriptsPath: str = f'{ParcelFabricFolder}{Environment}Environment\ScriptsAndTools/'
    TasksPath: str = f'{ParcelFabricFolder}{Environment}Environment\Tasks/'
    Library: str = f'{ParcelFabricFolder}{Environment}Environment\Library/'
    LayerFiles: str = f'{ParcelFabricFolder}{Environment}Environment\Layers/'
    TemplatesPath: str = f'{ParcelFabricFolder}{Environment}Environment\Templates/'


    # Data Sources
    SDE_mapping: dict[EnviType, str] = {"Development": "Dev", "Test": "Test", "Production": "Prod"}
    SDE: str = SDE_mapping[Environment]
    ParcelFabricDatabase: str = f"{SDEFolder}<sde_file_name>"
    ParcelFabricDataset: str = fr'{ParcelFabricDatabase}{OwnerName}<dataset_name>/'


    # Portal variables
    feature_service_mapping: dict[EnviType, list[str]] = {'Development': ['FabricMapDevelopment', 'InProcessMapDevelopment'],
                                                          'Test':        ['FabricMapTest', 'InProcessMapTest'],
                                                          'Production':  ['FabricMapProduction', 'InProcessMapProduction']}

    portal_servers_names: dict[EnviType, str] = {"Development": "<portal_url_development>",
                                                 "Test":        "portal_url_test",
                                                 "Production":  "portal_url_production"}

    portal_mapping: dict[EnviType, str] = {"Development": f"{portal_servers_names[Environment]}/<server>",
                                           "Test":        f"{portal_servers_names[Environment]}/<server>",
                                           "Production":  f"{portal_servers_names[Environment]}/<server>"}


    portal_url: str = fr"https://{portal_mapping[Environment]}/rest/services/"
    FeatureServers: list[str] = feature_service_mapping[Environment]
    ParcelFabricFeatureServer: str = fr"{portal_url}{FeatureServers[0]}/FeatureServer"
    InProcessFeatureServer: str = fr"{portal_url}{FeatureServers[1]}/FeatureServer"
    gis_url: str = fr"https://{portal_servers_names[Environment]}/portal/sharing/rest"
    version_manager_url: str = f"{portal_url}{FeatureServers[0]}/VersionManagementServer"


    # CMS variables
    CMS_url_mapping: dict[EnviType, str] = {"Development": "<cms_api_dev>",
                                            "Test":        "<cms_api_test>",
                                            "Production":  "<cms_api_prod>"}

    CMS_url: str = CMS_url_mapping[Environment]

    # Others
    default_version_guids: dict[EnviType, str] = {"Development": "<development_sde.default_version_guid>",
                                                  "Test": "<test_sde.default_version_guid>"
                                                  "Production": "production_sde.default_version_guid"}

    default_version_guid: str = default_version_guids[Environment]

    domain: str = "<organization_domain>"
