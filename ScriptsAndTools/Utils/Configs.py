# Configurations and variables
from Utils.TypeHints import EnviType


class CNFG:
    """This class holds configuration variables for various project paths and settings."""

    Environment: EnviType = 'Production'
    OwnerName: str = 'PF.'

    # Folders
    SDEFolder: str = fr"\\mapi_shares\MNCDB\SDE/"
    ParcelFabricFolder: str = fr"\\mapi_shares\MNCDB\Parcel Fabric/"
    ScriptsPath: str = f'{ParcelFabricFolder}{Environment}Environment\ScriptsAndTools/'
    TasksPath: str = f'{ParcelFabricFolder}{Environment}Environment\Tasks/'
    Library: str = f'{ParcelFabricFolder}{Environment}Environment\Library/'
    LayerFiles: str = f'{ParcelFabricFolder}{Environment}Environment\Layers/'
    TemplatesPath: str = f'{ParcelFabricFolder}{Environment}Environment\Templates/'


    # Data Sources
    SDE_mapping: dict[EnviType, str] = {"Development": "Dev", "Test": "Test", "Production": "Prod"}
    SDE: str = SDE_mapping[Environment]
    ParcelFabricDatabase: str = f"{SDEFolder}BankalMod{SDE}(pf).sde/"
    ParcelFabricDataset: str = fr'{ParcelFabricDatabase}{OwnerName}ParcelFabricDataset/'


    # Portal variables
    feature_service_mapping: dict[EnviType, list[str]] = {'Development': ['FabricMapDevelopment', 'InProcessMapDevelopment'],
                                                          'Test':        ['FabricMapTest', 'InProcessMapTest'],
                                                          'Production':  ['FabricMapProduction', 'InProcessMapProduction']}

    portal_servers_names: dict[EnviType, str] = {"Development": "arcgis-srv-p.mapi.co.il",
                                                 "Test":        "arcgis-srv-p.mapi.co.il",
                                                 "Production":  "bnkl3dgisprod.mapi.co.il"}

    portal_mapping: dict[EnviType, str] = {"Development": f"{portal_servers_names[Environment]}/arcgis",
                                           "Test":        f"{portal_servers_names[Environment]}/arcgis",
                                           "Production":  f"{portal_servers_names[Environment]}/server"}


    portal_url: str = fr"https://{portal_mapping[Environment]}/rest/services/"
    FeatureServers: list[str] = feature_service_mapping[Environment]
    ParcelFabricFeatureServer: str = fr"{portal_url}NationalCadasterEditors/{FeatureServers[0]}/FeatureServer"
    InProcessFeatureServer: str = fr"{portal_url}NationalCadasterEditors/{FeatureServers[1]}/FeatureServer"
    gis_url: str = fr"https://{portal_servers_names[Environment]}/portal/sharing/rest"
    version_manager_url: str = f"{portal_url}NationalCadasterEditors/{FeatureServers[0]}/VersionManagementServer"


    # CMS variables
    CMS_url_mapping: dict[EnviType, str] = {"Development": "http://192.168.134.104:7777/manage/api/Httpclientbnklpfapi/upprjstatuspf",
                                            "Test":        "http://192.168.135.129:7777/manage/api/Httpclientbnklpfapi/upprjstatuspf",
                                            "Production":  "http://cmscust-app-prod:7777/manage/api/Httpclientbnklpfapi/upprjstatuspf"}

    CMS_url: str = CMS_url_mapping[Environment]

    # Others
    default_version_guids: dict[EnviType, str] = {"Development": "{BD3F4817-9A00-41AC-B0CC-58F78DBAE0A1}",
                                                  "Test": None,  # TODO
                                                  "Production": "{BD3F4817-9A00-41AC-B0CC-58F78DBAE0A1}"}

    default_version_guid: str = default_version_guids[Environment]

    domain: str = "@mapi.gov.il"
