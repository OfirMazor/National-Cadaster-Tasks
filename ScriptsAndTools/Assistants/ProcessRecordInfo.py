from set_path import add_parent_to_sys_path
add_parent_to_sys_path(__file__)

from Utils.Helpers import get_ProcessGUID, get_RecordGUID, get_ProcessType, get_DomainValue, AddTabularMessage
from Utils.TypeHints import df
from arcpy import GetParameterAsText
import pandas as pd


def print_process_guids(ProcessName: str) -> None:
    """
    Massages the GUIDs values of a process in the CadasterProcessBorders and CadasterRecordsBorders tables.

    Parameters:
        ProcessName (str): The name of the process.
    """
    data: dict[str, str|int|None] = {"שם המפה": ProcessName,
                                     "סוג תהליך": get_DomainValue(domain='ProcessType', code= get_ProcessType(ProcessName)),
                                     "מזהה תהליך": get_ProcessGUID(ProcessName, 'MAP'),
                                     "מזהה רישום": get_RecordGUID(ProcessName, 'MAP')}

    data: df = pd.DataFrame([data])
    AddTabularMessage(data)


if __name__ == "__main__":
    print_process_guids(ProcessName= GetParameterAsText(0))
