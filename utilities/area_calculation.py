from shapely.geometry import Polygon
from pyproj import CRS, Transformer
from shapely.ops import transform
import math

def calculate_polygon_area_in_sqm(polygon: Polygon) -> float:
    """
    Calculates the area of a Shapely Polygon in square meters (m²)
    by transforming it to a suitable local UTM projection.

    Args:
        polygon (shapely.geometry.Polygon): The input polygon with geographic coordinates (lon, lat).

    Returns:
        float: The area of the polygon in square meters.
    """
    if polygon.is_empty:
        return 0.0

    # Get the centroid of the polygon to determine the appropriate UTM zone
    # Shapely coordinates are typically (x, y) which means (longitude, latitude)
    centroid_lon, centroid_lat = polygon.centroid.x, polygon.centroid.y

    # Determine UTM zone (EPSG code) based on longitude and hemisphere
    # UTM zones are 6 degrees wide.
    # Northern Hemisphere: EPSG:326xx (e.g., 32648 for zone 48N)
    # Southern Hemisphere: EPSG:327xx (e.g., 32748 for zone 48S)

    utm_zone = int(math.floor((centroid_lon + 180) / 6) % 60) + 1

    if centroid_lat >= 0:
        utm_epsg = 32600 + utm_zone  # Northern Hemisphere
    else:
        utm_epsg = 32700 + utm_zone  # Southern Hemisphere

    # Define the source CRS (WGS84 geographic) and the target CRS (UTM projected)
    # Use CRS objects directly instead of string initials for pyproj > 2.0
    crs_wgs84 = CRS("EPSG:4326")
    crs_utm = CRS(f"EPSG:{utm_epsg}")

    # Create a transformer from WGS84 to the calculated UTM zone
    # always_xy=True ensures output is (x, y) i.e. (lon, lat) for WGS84
    # and (easting, northing) for UTM, matching Shapely's (x, y) convention.
    project = Transformer.from_crs(crs_wgs84, crs_utm, always_xy=True).transform

    # Transform the polygon
    transformed_polygon = transform(project, polygon)

    # The area of the transformed polygon is now in square meters
    return transformed_polygon.area

# Example Usage:
# Let's use a sample polygon (e.g., a small square near Kuala Lumpur)
# Kuala Lumpur is around 3.14 N, 101.69 E
# This is in UTM Zone 48N
sample_coords = [
    (101.68, 3.13),
    (101.70, 3.13),
    (101.70, 3.15),
    (101.68, 3.15),
    (101.68, 3.13) # Close the polygon
]
sample_polygon = Polygon(sample_coords)

print(f"Original polygon area in square degrees: {sample_polygon.area}")

area_in_sqm = calculate_polygon_area_in_sqm(sample_polygon)
print(f"Polygon area in square meters: {area_in_sqm:.2f} m²")