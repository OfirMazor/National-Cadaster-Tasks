import os
import sys


def add_parent_to_sys_path(script_path: str) -> str:
    """Adds the parent directory of the specified script to `sys.path` if it is not already included.

    Parameters:
        script_path (str): The file path of the executing script (typically `__file__`).

    Returns:
        str: The absolute path of the parent directory added to `sys.path`.
    """
    current_dir: str = os.path.dirname(os.path.abspath(script_path))
    parent_dir: str = os.path.dirname(current_dir)

    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    return parent_dir
