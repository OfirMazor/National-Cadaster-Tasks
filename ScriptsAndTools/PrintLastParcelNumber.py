from Utils.TypeHints import Scur
from Utils.Configs import CNFG
from Utils.Helpers import cursor_length, timestamp
from arcpy import AddMessage, AddError, GetParameter
from arcpy.da import SearchCursor


def print_last_parcel_number(block_number: int, sub_block_number: int = 0) -> None:
    """
    Prints the last active parcel number in the specified block.

    This function queries the Parcels2D and Parcels3D feature classes within the configured parcel fabric dataset,
    filtering only active parcels (i.e., those not retired).
    It then determines the highest parcel number in each class for the given block and sub-block, and prints the maximum of the two.

    Parameters:
        block_number (int): The block number to search within.
        sub_block_number (int, optional): The sub-block number to search within. Defaults to 0.
    """
    query: str = f"RetiredByRecord IS NULL AND BlockNumber = {block_number} AND SubBlockNumber = {sub_block_number}"
    Parcels2D: Scur = SearchCursor(fr"{CNFG.ParcelFabricDataset}{CNFG.OwnerName}Parcels2D", 'ParcelNumber', query)
    Parcels3D: Scur = SearchCursor(fr"{CNFG.ParcelFabricDataset}{CNFG.OwnerName}Parcels3D", 'ParcelNumber', query)

    if cursor_length(Parcels2D) > 0:
        Parcels2D: int = max([row[0] for row in Parcels2D])

        if cursor_length(Parcels3D) > 0:
            Parcels3D: int = max([row[0] for row in Parcels3D])
        else:
            Parcels3D: int = 0

        last_parcel: int = max(Parcels2D, Parcels3D)
        Message: str = fr"Last active parcel at block {block_number}/{sub_block_number} is {last_parcel}"
        AddMessage(Message)

    else:
        AddError(f"{timestamp()} | Block {block_number}/{sub_block_number} not found")

    del Parcels2D, Parcels3D, query



if __name__ == "__main__":

    print_last_parcel_number(block_number= GetParameter(0), sub_block_number= GetParameter(1))
