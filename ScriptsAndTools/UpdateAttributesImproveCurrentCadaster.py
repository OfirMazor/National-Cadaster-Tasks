from arcpy import GetParameter
from Utils.Helpers import get_ActiveRecord
from Utils.UpdateAttributes import modify_ParcelsAttributes, modify_CurrentFrontsAttributes, modify_PointsAttributes, \
                                   modify_BlockAttributes



def update_attributes(Parcels: bool = True, Fronts: bool = True, Points: bool = True) -> None:
    """
    Updates various cadastral attributes after point edits in the current task.
    This function runs a sequence of post-edit updates on the active record, performing operations such as:
      - Updating attributes for incoming active parcels (optional).
      - Updating attributes for current and newly created fronts (optional).
      - Updating attributes for points related to the 'ImproveCurrentCadaster' task (optional).
      - Updating block Stated Area attribute.

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
    """
    ProcessName: str|None = get_ActiveRecord()

    if ProcessName:
        if Parcels:
            modify_ParcelsAttributes(ProcessName)

        if Fronts:
            modify_CurrentFrontsAttributes()

        if Points:
            modify_PointsAttributes(ProcessName, task= 'ImproveCurrentCadaster')

    modify_BlockAttributes(ProcessName)
    del ProcessName


if __name__ == "__main__":
    update_attributes(Parcels= GetParameter(0), Fronts= GetParameter(1), Points= GetParameter(2))
