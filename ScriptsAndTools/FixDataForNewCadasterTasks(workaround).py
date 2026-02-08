from os import startfile
from Utils.Configs import CNFG
from Utils.Helpers import reopen_map, timestamp
from Utils.NewCadasterHelpers import split_merged_tax_fronts, match_active_tax_blocks_to_active_tax_parcels,match_process_border_to_process_parcels
from Utils.ValidationsNewCadaster import is_process_border_valid
from arcpy import AddMessage, AddError, AddWarning,GetParameterAsText, GetParameter, env as ENV



ENV.preserveGlobalIds = False

def fix_data_for_new_cadaster_tasks(ProcessName: str, split_fronts: bool, update_tax_blocks: bool) -> None:
    ''' 
    Fix data for new cadaster tasks:
    - Split merged tax fronts
    - Update retired tax blocks with active tax parcels
    - Match process border to process parcels contour

    '''

    if split_fronts:
        AddMessage(f'\n ⭕ Checking if there are merged tax fronts to split for process {ProcessName}... \n')
        split_merged_tax_fronts(ProcessName)
        
    if update_tax_blocks:
        AddMessage(f'\n ⭕ Checking if there are retired tax blocks with active tax parcels for process {ProcessName}... \n')
        match_active_tax_blocks_to_active_tax_parcels(ProcessName)
    
    reopen_map()

if __name__ == "__main__":

    ProcessName = GetParameterAsText(0)

    split_fronts = GetParameter(1)

    update_tax_blocks = GetParameter(2)


    fix_data_for_new_cadaster_tasks(ProcessName, split_fronts, update_tax_blocks)


    
