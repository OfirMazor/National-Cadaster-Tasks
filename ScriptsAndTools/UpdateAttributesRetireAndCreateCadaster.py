from arcpy import GetParameter
from Utils.TypeHints import Optional
from Utils.Helpers import get_ActiveRecord
from Utils.UpdateAttributes import modify_CurrentAndNewFrontsAttributes, modify_PointsAttributes, modify_BlockAttributes, build_record


def update_attributes(Fronts: Optional[bool] = True, Points: Optional[bool] = True, Build: Optional[bool] = True) -> None:
    """
    Updates various cadastral attributes after point edits in the current task.
    This function runs a sequence of post-edit updates on the active record, performing operations such as:
      - Updating attributes for current and newly created fronts (optional).
      - Updating attributes for points related to the 'RetireAndCreateCadaster' task (optional).
      - Updating block attributes.
      - Retiring relevant blocks.
      - Building the final record geometry and attributes (optional).

    The active record must be activated before running this function.
    If no active record is found, an error message will be added to the ArcGIS geoprocessing messages.

    Parameters:
        Fronts : bool, optional
            Whether to update current and new fronts attributes. Default is True.
        Points : bool, optional
            Whether to update point attributes. Default is True.
        Build : bool, optional
            Whether to run the Build Active command after updates. Default is True.
    """

    ProcessName: str|None = get_ActiveRecord()

    if ProcessName:
        if Fronts:
            modify_CurrentAndNewFrontsAttributes()

        if Points:
            modify_PointsAttributes(ProcessName, task='RetireAndCreateCadaster')

        modify_BlockAttributes(ProcessName)

        if Build:
            build_record(ProcessName)

    del ProcessName


if __name__ == "__main__":

    update_attributes(Fronts= GetParameter(0),
                      Points= GetParameter(1),
                      Build= GetParameter(2))


