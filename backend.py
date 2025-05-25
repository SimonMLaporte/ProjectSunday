import requests
import json
from utilities.area_calculation import calculate_polygon_area_in_sqm
from shapely.geometry import Point, Polygon, mapping
from geopy.distance import geodesic
import googlemaps
from flask import Flask, jsonify, request
from flask_cors import CORS



app = Flask(__name__)
CORS(app)

def get_closest_building_geometry(target_lat, target_lon, search_radius_meters=100):
    """
    Finds the closest building to a given latitude and longitude and returns its geometry.

    Args:
        target_lat (float): The latitude of the reference point.
        target_lon (float): The longitude of the reference point.
        search_radius_meters (int): The radius in meters to search for buildings around the point.

    Returns:
        dict: A dictionary containing information about the closest building,
              including its geometry (list of {'lat': ..., 'lon': ...}),
              distance, and OSM tags. Returns None if no building is found.
    """
    # 1. Query for buildings around the target location
    buildings_data = query_overpass_api_buildings(target_lat, target_lon, search_radius_meters)

    if not buildings_data or "elements" not in buildings_data:
        print(f"No building data found within {search_radius_meters}m radius.")
        return None
    closest_building = None
    min_distance = float('inf')

    for element in buildings_data["elements"]:
        if element.get("type") == "way" and element.get("geometry"):
            # Ensure it's a valid polygon (at least 3 points)
            if len(element["geometry"]) < 3:
                continue

            # Shapely Polygon expects (lon, lat) tuples
            polygon_coords_shapely = [(p['lon'], p['lat']) for p in element["geometry"]]
            try:
                building_polygon = Polygon(polygon_coords_shapely)
            except Exception as e:
                print(f"Could not create Shapely Polygon for building ID {element.get('id')}: {e}")
                continue

            # Calculate the centroid of the building polygon for distance calculation
            # For complex shapes, this is a good approximation.
            # Alternatively, you could use building_polygon.exterior.distance(target_point)
            # but that requires projecting to a local coordinate system for meters.
            # geodesic is more robust for lat/lon directly.
            centroid_lon, centroid_lat = building_polygon.centroid.x, building_polygon.centroid.y

            # Calculate geodesic distance between target point and building's centroid
            distance = geodesic((target_lat, target_lon), (centroid_lat, centroid_lon)).meters

            if distance < min_distance:
                min_distance = distance
                shape = mapping(building_polygon)
                solar_potential = calculate_solar_potential(target_lat, target_lon,shape)
                area = calculate_polygon_area_in_sqm(building_polygon)
                closest_building = {
                    "id": element.get("id"),
                    "type": element.get("type"),
                    "tags": element.get("tags", {}),
                    "shape": shape,
                    "distance_meters": distance,
                    "centroid_lat": centroid_lat,
                    "centroid_lon": centroid_lon,
                    "area": area,
                    "solarPotential": solar_potential * area * 0.21 * 0.85 /1000
                }
    return closest_building
def query_overpass_api_buildings(latitude, longitude, radius_meters=100):
    """
    Queries Overpass API specifically for building ways around a given point.
    Returns elements that are primarily 'ways' (polygons) representing buildings.
    """
    overpass_url = "https://overpass-api.de/api/interpreter"

    # Query only for 'way' elements with 'building' tag
    # We focus on ways because buildings are usually polygons
    overpass_query = f"""
    [out:json][timeout:25];
    (
      way(around:{radius_meters},{latitude},{longitude})["building"];
    );
    out body geom;
    """

    print(f"\nSending Overpass building query:\n{overpass_query}")
    try:
        response = requests.post(overpass_url, data=overpass_query.encode('utf-8'))
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        print(f"Overpass API Error during building query: {e}")
        if response and hasattr(response, 'text'):
            print(f"Overpass Error Response: {response.text}")
        return None
    except json.JSONDecodeError as e:
        print(f"Overpass JSON Decode Error: {e} - Response was not valid JSON.")
        print(f"Faulty Response: {response.text}")
        return None
def calculate_solar_potential(latitude, longitude,shape):
     # NASA POWER API endpoint for daily climatology data (long-term average)
    # Using the RE (Renewable Energy) community and ALLSKY_SFC_SW_DWN (all-sky shortwave radiation incident on the surface)
    # You could also look into 'PVP' if available for your community/timeframe

    # We want long-term average, so we'll use climatology service or a very long date range
    # For a rough daily average, a broad time range like 20 years is good.
    start_date = "20190101" # YYYYMMDD
    end_date = "20201231"   # YYYYMMDD (Adjust as needed, longer span gives better average)

    # NASA POWER API URL for daily point data
    api_url = (
        f"https://power.larc.nasa.gov/api/temporal/daily/point?"
        f"parameters=ALLSKY_SFC_SW_DWN&community=RE&"
        f"longitude={longitude}&latitude={latitude}&"
        f"start={start_date}&end={end_date}&format=JSON"
    )

    try:
        response = requests.get(api_url)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        data = response.json()

        # Extract the data. ALLSKY_SFC_SW_DWN is typically in Wh/m^2/day
        # The data structure might be nested under 'properties' -> 'parameter' -> 'ALLSKY_SFC_SW_DWN'

        # For daily average over the period:
        solar_data = data.get('properties', {}).get('parameter', {}).get('ALLSKY_SFC_SW_DWN', {})

        if not solar_data:
            print(f"No solar data found for {latitude}, {longitude} in specified range.")
            return None

        # Calculate the average daily Wh/m^2 over the period
        total_daily_irradiance = 0
        count = 0
        for date_key, value in solar_data.items():
            try:
                # Values might be None or specific error codes for missing days, filter them
                if value is not None and isinstance(value, (int, float)):
                    total_daily_irradiance += value
                    count += 1
            except (TypeError, ValueError):
                # Handle cases where value might not be a number
                continue

        if count == 0:
            print("No valid numerical solar data found for averaging.")
            return None

        average_daily_kWh_perM2 = total_daily_irradiance / count


        print(f"Rough solar potential for {latitude}, {longitude}: {average_daily_kWh_perM2:.2f} kWh/m2/day")
        return average_daily_kWh_perM2*365

    except requests.exceptions.HTTPError as errh:
        print(f"HTTP Error: {errh}")
        return None
    except requests.exceptions.ConnectionError as errc:
        print(f"Error Connecting: {errc}")
        return None
    except requests.exceptions.Timeout as errt:
        print(f"Timeout Error: {errt}")
        return None
    except requests.exceptions.RequestException as err:
        print(f"Opaque Error: {err}")
        return None
    except json.JSONDecodeError:
        print("Failed to decode JSON from NASA POWER response.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

@app.route('/data', methods=['POST'])
def endpoint():
    req_data = request.get_json()
    latitude = req_data.get('latitude')
    longitude = req_data.get('longitude')
    building_geometry = get_closest_building_geometry(latitude,longitude)
    return jsonify(building_geometry)

if __name__ == "__main__":
    #debug branch
   app.run(debug=True, host='127.0.0.1', port=5000)
""" latitude, longitude = 3.139407102489938, 101.66599036129782
    building_geometry = get_closest_building_geometry(latitude,longitude)
    with open("building.json", 'w', encoding='utf-8') as file:
        json.dump(building_geometry, file, ensure_ascii=False, indent=4) """