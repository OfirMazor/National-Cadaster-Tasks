from Utils.VersionManagement import close_version
from Utils.UpdateAttributes import set_as_recorded, update_record_status
from Utils.Reports import compare_and_document_version_changes
from Utils.Helpers import get_ActiveRecord, get_ProcessStatus, reopen_map, respond_to_CMS, get_RecordType
from arcpy import GetParameterAsText, env as ENV

ENV.overwriteOutput = True


def EndTask(user_name: str, password: str) -> None:
    """
    Performs final operations in the task to post edits.

    This function closes the version associated with the given ProcessName.
    if reinitialize_ender is 'true', the function will finalize with reinitialize the active project.
    The reinitialize_ender parameters are assigned via checkbox in the ArcGIS Pro task.

    Parameters:
        user_name (srt): The name of the user in ArcGIS Portal
        password (str): The password for the given user.
    """

    ProcessName: str|None = get_ActiveRecord()

    if ProcessName:
        compare_and_document_version_changes(user_name, password)
        close_version()
        RecordType: int = get_RecordType(ProcessName, 'ActiveMap')

        # Post edits attributes modifications:
        # --- Update Free Edit record status to עריכה הסתיימה

        if RecordType == 16:
            update_record_status(ProcessName, 18)  # עריכה הסתיימה

        # --- Update Recorded field for in-process layers of registered tazars

        if RecordType in [1, 2, 11]:  # [תצ"ר, תצ"ר בשטח לא מוסדר, תמ"ר]
            if get_ProcessStatus(ProcessName, 'MAP') == 5:  # רשומה
                set_as_recorded(ProcessName)


        # Send feedback to CMS
        respond_to_CMS(ProcessName, RecordType)

        reopen_map()

    del ProcessName


if __name__ == "__main__":
    EndTask(user_name= GetParameterAsText(0), password= GetParameterAsText(1))
