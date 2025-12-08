import arcpy
from pandas import DataFrame, Series
from typing import Any, Literal, Optional, Callable


# General types
Any = Any
Literal = Literal
Optional = Optional
Callable = Callable
df = DataFrame
series = Series

# Arcpy types
Pro = arcpy._mp.ArcGISProject
Map = arcpy._mp.Map
Layer = arcpy._mp.Layer
Table = arcpy._mp.Table
parcelCIM = arcpy.cim.CIMVectorLayers.CIMParcelLayer
Extent = arcpy.Extent
Scur = arcpy.da.SearchCursor
Icur = arcpy.da.InsertCursor
Ucur = arcpy.da.UpdateCursor
Domain = arcpy.da.Domain
Editor = arcpy.da.Editor
Point = arcpy.Point
Line = arcpy.Polyline
Polygon = arcpy.Polygon
Result = arcpy.Result

# Custom types
EnviType = Literal["Development", "Test", "Production"]
MapType = Literal["מפת עריכה", "סצנת עריכה", "Active map"]
Validation = Literal["Valid", "Invalid"]
TaskType = Literal['ImproveCurrentCadaster', 'RetireAndCreateCadaster', 'ImproveNewCadaster', 'CreateNewCadaster', 'RetireAndCreateCadaster3D', 'FreeEdit']
