from arcpy import GetParameter, AddError
from Utils.TypeHints import Optional
from Utils.Helpers import get_ActiveRecord, timestamp
from Utils.UpdateAttributes import modify_ParcelsAttributes, modify_CurrentFrontsAttributes, modify_PointsAttributes, modify_BlockAttributes, build_record


def update_attributes(Parcels: Optional[bool] = True,
                      Fronts: Optional[bool] = True,
                      Points: Optional[bool] = True,
                      Build: Optional[bool] = True) -> None:
    """
    Updates various cadastral attributes after point edits in the current task.
    This function runs a sequence of post-edit updates on the active record, performing operations such as:
      - Updating attributes for incoming active parcels (optional).
      - Updating attributes for current and newly created fronts (optional).
      - Updating attributes for points related to the 'ImproveCurrentCadaster' task (optional).
      - Updating block Stated Area attribute.
      - Building the final record geometry and attributes (optional).

    The active record must be activated before running this function. If no
    active record is found, an error message will be added to the ArcGIS
    geoprocessing messages.

    Parameters:
        Parcels: : bool, optional
            Whether to update incoming active parcels attributes. Default is True.
        Fronts : bool, optional
            Whether to update current and new fronts attributes. Default is True.
        Points : bool, optional
            Whether to update point attributes. Default is True.
        Build : bool, optional
            Whether to run the Build Active command after updates. Default is True.
    """
    ProcessName: str|None = get_ActiveRecord()

    if ProcessName:
        if Parcels:
            modify_ParcelsAttributes(ProcessName)
            modify_BlockAttributes(ProcessName)

        if Fronts:
            modify_CurrentFrontsAttributes(ProcessName)

        if Points:
            modify_PointsAttributes(ProcessName, task= 'ImproveCurrentCadaster')

        if Build:
            build_record(ProcessName)

    del ProcessName


if __name__ == "__main__":
    update_attributes(Parcels= GetParameter(0),
                      Fronts= GetParameter(1),
                      Points= GetParameter(2),
                      Build= GetParameter(3))
