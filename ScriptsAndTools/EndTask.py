from ReinitializeProject import reinitialize
from Utils.TypeHints import Optional
from Utils.VersionManagement import close_version
from Utils.UpdateAttributes import set_as_recorded
from Utils.Reports import compare_and_document_version_changes
from Utils.Helpers import get_ActiveRecord, get_ProcessType, get_ProcessStatus, reopen_map, respond_to_CMS
from arcpy import GetParameter, GetParameterAsText, env


env.overwriteOutput = True


def EndTask(user_name: str, password: str, reinitializer: Optional[bool] = False) -> None:
    """
    Performs final operations in the task to post edits.

    This function closes the version associated with the given ProcessName.
    if reinitialize_ender is 'true', the function will finalize with reinitialize the active project.
    The reinitialize_ender parameters are assigned via checkbox in the ArcGIS Pro task.

    Parameters:
        user_name (srt): The name of the user in ArcGIS Portal
        password (str): The password for the given user.
        reinitializer (Optional[bool]): A boolean indicating whether to reinitialize the project or not. Default is False.

    """


    ProcessName: str|None = get_ActiveRecord()

    if ProcessName:
        compare_and_document_version_changes(user_name, password)
        close_version()
        process_type: int = get_ProcessType(ProcessName)
        process_status: int = get_ProcessStatus(ProcessName, 'MAP')

        # Update Recorded field for in-process layers
        if process_type in [1, 11]:
            if process_status in [4, 6, 10]:
                pass
        else:
            set_as_recorded(ProcessName)

        # Send feedback to CMS
        respond_to_CMS(ProcessName, process_type)


        if reinitializer:
            reinitialize()
        else:
            reopen_map()

    del ProcessName


if __name__ == "__main__":
    EndTask(user_name= GetParameterAsText(0), password= GetParameterAsText(1), reinitializer= GetParameter(2))
