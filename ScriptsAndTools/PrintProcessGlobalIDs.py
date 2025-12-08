from Utils.Helpers import get_ProcessGUID, get_RecordGUID, get_ProcessType, get_DomainValue, AddTabularMessage
from arcpy import GetParameterAsText
import pandas as pd


def print_process_id(ProcessName: str) -> None:

    data: dict[str, str|int] = {"שם המפה": ProcessName,
                                "סוג תהליך": get_DomainValue(domain='ProcessType', code= get_ProcessType(ProcessName)),
                                "מזהה תהליך": get_ProcessGUID(ProcessName, 'MAP'),
                                "מזהה רישום": get_RecordGUID(ProcessName, 'MAP')}

    df = pd.DataFrame([data])
    AddTabularMessage(df)



if __name__ == "__main__":
    print_process_id(ProcessName= GetParameterAsText(0))
