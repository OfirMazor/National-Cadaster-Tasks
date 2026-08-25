from arcpy import GetParameter
from Utils.TypeHints import Optional
from Utils.Helpers import get_ActiveRecord
from Utils.UpdateAttributes import modify_3DPointsAttributes, modify_BlockAttributes, build_record


def update_attributes(Points3D: Optional[bool] = True, Build: Optional[bool] = True) -> None:
    """
    Updates various cadastral attributes after retiring features and adding new ones in the current task.
    This function runs a sequence of post-edit updates on the active record, performing operations such as:
      - Updating attributes for 3D points related to the 'RetireAndCreateCadaster3D' task (optional).
      - Updating block attributes.
      - Building the final record geometry and attributes (optional).

    The active record must be activated before running this function.
    If no active record is found, an error message will be added to the ArcGIS geoprocessing messages.

    Parameters:
        Points3D : bool, optional
            Whether to update 3D point attributes. Default is True.
        Build : bool, optional
            Whether to run the Build Active command after updates. Default is True.
    """

    ProcessName: str|None = get_ActiveRecord()

    if ProcessName:
        if Points3D:
            modify_3DPointsAttributes(ProcessName)

        modify_BlockAttributes(ProcessName)

        if Build:
            build_record(ProcessName)

    del ProcessName


if __name__ == "__main__":
    update_attributes(Points3D= GetParameter(0), Build= GetParameter(1))
