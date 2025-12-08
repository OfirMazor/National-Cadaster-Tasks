from os import startfile
from Utils.TypeHints import *
from Utils.Configs import CNFG
from Utils.VersionManagement import open_version
from Utils.Helpers import filter_to_aoi, set_priority, create_shelf, activate_record, get_BlockGUID, zoom_to_aoi, timestamp
from arcpy import AddMessage, GetParameterAsText, GetParameter
from arcpy.da import InsertCursor


def create_free_edit_record(RecordName: str, BlockNumber: int, SubBlockNumber: int = 0) -> None:
    """
    Adds a new record data to CadasterRecordsBorders Table.

    Parameters:
        RecordName (str): The Name of the record.
        BlockNumber (int): The number of the block containing the record borders.
        SubBlockNumber (int): The sub number of the block containing the record borders. Default is 0.

    Returns:
        None
    """

    records_feature_class: str = f'{CNFG.ParcelFabricDataset}PF.CadasterRecordsBorder'

    record_data: dict[str, Any] = {'Name': RecordName,
                                   'RecordType': 16,      # עריכה חופשית
                                   'GeodeticNetwork': 3,  # רשת ישראל התקפה
                                   'Status': 14,          # בביצוע
                                   'DataSource': 0,       # לא ידוע
                                   'BlockUniqueID': get_BlockGUID('BlockName', f'{BlockNumber}/{SubBlockNumber}')}

    records: Icur = InsertCursor(in_table = records_feature_class, field_names = list(record_data.keys()))
    records.insertRow(tuple(record_data.values()))
    del records
    AddMessage(f'{timestamp()} | Record {RecordName} created')


def start_task_FreeEdit(RecordName: str, BlockNumber: int, SubBlockNumber: int = 0) -> None:
    """
    Workflow for starting the Free Editing task.

    Parameters:
        RecordName (str): The Name of the record to be edited.
        BlockNumber (int): The number of the block containing the record borders.
        SubBlockNumber (int): The sub number of the block containing the record borders. Default is 0.

    Returns:
        None
    """

    set_priority()

    shelf: str = create_shelf(RecordName)

    open_version(RecordName)

    startfile(fr'{shelf}')

    create_free_edit_record(RecordName, BlockNumber, SubBlockNumber)

    filter_to_aoi(RecordName)

    activate_record(RecordName)

    zoom_to_aoi()


if __name__ == "__main__":
    RecordName: str = GetParameterAsText(0)
    BlockNumber: int = GetParameter(1)
    SubBlockNumber: int|None = GetParameter(2)

    start_task_FreeEdit(RecordName, BlockNumber, SubBlockNumber)
