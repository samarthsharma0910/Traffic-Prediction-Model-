"""
Coverage definition: 110 Indian cities (all 28 states + major UTs) and the
monitoring zones generated for each of them.

Coordinates are city-centre coordinates (approximate, 2 decimals). Zones are
*representative monitoring areas* placed deterministically around the centre -
they are not surveyed junctions. Population (millions) is approximate and is
only used to scale expected congestion.
"""
import json
import math
import os

# (city, state, lat, lon, approx metro population in millions)
CITIES = [
    ("Delhi", "Delhi", 28.61, 77.21, 32.0), ("Mumbai", "Maharashtra", 19.08, 72.88, 21.0),
    ("Bengaluru", "Karnataka", 12.97, 77.59, 13.0), ("Kolkata", "West Bengal", 22.57, 88.36, 15.0),
    ("Chennai", "Tamil Nadu", 13.08, 80.27, 11.0), ("Hyderabad", "Telangana", 17.39, 78.49, 10.5),
    ("Pune", "Maharashtra", 18.52, 73.86, 7.0), ("Ahmedabad", "Gujarat", 23.02, 72.57, 8.0),
    ("Surat", "Gujarat", 21.17, 72.83, 7.5), ("Jaipur", "Rajasthan", 26.91, 75.79, 4.0),
    ("Lucknow", "Uttar Pradesh", 26.85, 80.95, 3.9), ("Kanpur", "Uttar Pradesh", 26.45, 80.35, 3.2),
    ("Nagpur", "Maharashtra", 21.15, 79.09, 2.9), ("Indore", "Madhya Pradesh", 22.72, 75.86, 3.3),
    ("Bhopal", "Madhya Pradesh", 23.26, 77.41, 2.4), ("Visakhapatnam", "Andhra Pradesh", 17.69, 83.22, 2.4),
    ("Patna", "Bihar", 25.59, 85.14, 2.5), ("Vadodara", "Gujarat", 22.31, 73.18, 2.2),
    ("Ghaziabad", "Uttar Pradesh", 28.67, 77.45, 2.8), ("Ludhiana", "Punjab", 30.90, 75.86, 1.9),
    ("Agra", "Uttar Pradesh", 27.18, 78.01, 1.9), ("Nashik", "Maharashtra", 20.00, 73.79, 2.0),
    ("Faridabad", "Haryana", 28.41, 77.31, 1.9), ("Meerut", "Uttar Pradesh", 28.98, 77.71, 1.7),
    ("Rajkot", "Gujarat", 22.30, 70.80, 1.8), ("Varanasi", "Uttar Pradesh", 25.32, 83.01, 1.7),
    ("Srinagar", "Jammu and Kashmir", 34.08, 74.80, 1.5), ("Aurangabad", "Maharashtra", 19.88, 75.34, 1.6),
    ("Dhanbad", "Jharkhand", 23.80, 86.43, 1.3), ("Amritsar", "Punjab", 31.63, 74.87, 1.4),
    ("Prayagraj", "Uttar Pradesh", 25.44, 81.85, 1.5), ("Ranchi", "Jharkhand", 23.34, 85.31, 1.2),
    ("Coimbatore", "Tamil Nadu", 11.02, 76.96, 2.2), ("Jabalpur", "Madhya Pradesh", 23.18, 79.95, 1.4),
    ("Gwalior", "Madhya Pradesh", 26.22, 78.18, 1.4), ("Vijayawada", "Andhra Pradesh", 16.51, 80.65, 1.5),
    ("Jodhpur", "Rajasthan", 26.24, 73.02, 1.3), ("Madurai", "Tamil Nadu", 9.93, 78.12, 1.5),
    ("Raipur", "Chhattisgarh", 21.25, 81.63, 1.4), ("Kota", "Rajasthan", 25.18, 75.83, 1.2),
    ("Guwahati", "Assam", 26.14, 91.74, 1.1), ("Chandigarh", "Chandigarh", 30.73, 76.78, 1.2),
    ("Thiruvananthapuram", "Kerala", 8.52, 76.94, 1.0), ("Solapur", "Maharashtra", 17.66, 75.91, 1.0),
    ("Hubballi", "Karnataka", 15.36, 75.12, 1.0), ("Tiruchirappalli", "Tamil Nadu", 10.79, 78.70, 1.1),
    ("Bareilly", "Uttar Pradesh", 28.37, 79.43, 1.0), ("Mysuru", "Karnataka", 12.30, 76.64, 1.0),
    ("Tiruppur", "Tamil Nadu", 11.11, 77.34, 0.9), ("Gurugram", "Haryana", 28.46, 77.03, 1.5),
    ("Aligarh", "Uttar Pradesh", 27.88, 78.08, 0.9), ("Jalandhar", "Punjab", 31.33, 75.58, 0.9),
    ("Bhubaneswar", "Odisha", 20.30, 85.82, 1.2), ("Salem", "Tamil Nadu", 11.66, 78.15, 0.9),
    ("Warangal", "Telangana", 17.97, 79.59, 0.8), ("Guntur", "Andhra Pradesh", 16.31, 80.44, 0.9),
    ("Gorakhpur", "Uttar Pradesh", 26.76, 83.37, 0.9), ("Bikaner", "Rajasthan", 28.02, 73.31, 0.7),
    ("Amravati", "Maharashtra", 20.93, 77.75, 0.7), ("Noida", "Uttar Pradesh", 28.54, 77.39, 1.0),
    ("Jamshedpur", "Jharkhand", 22.80, 86.20, 1.3), ("Bhilai", "Chhattisgarh", 21.21, 81.38, 1.0),
    ("Cuttack", "Odisha", 20.46, 85.88, 0.7), ("Kochi", "Kerala", 9.93, 76.27, 2.1),
    ("Dehradun", "Uttarakhand", 30.32, 78.03, 0.8), ("Durgapur", "West Bengal", 23.55, 87.32, 0.6),
    ("Asansol", "West Bengal", 23.68, 86.98, 1.2), ("Nanded", "Maharashtra", 19.14, 77.32, 0.6),
    ("Kolhapur", "Maharashtra", 16.70, 74.24, 0.6), ("Ajmer", "Rajasthan", 26.45, 74.64, 0.6),
    ("Kalaburagi", "Karnataka", 17.33, 76.83, 0.6), ("Jamnagar", "Gujarat", 22.47, 70.07, 0.6),
    ("Ujjain", "Madhya Pradesh", 23.18, 75.78, 0.6), ("Siliguri", "West Bengal", 26.73, 88.40, 0.8),
    ("Jhansi", "Uttar Pradesh", 25.45, 78.57, 0.6), ("Mangaluru", "Karnataka", 12.91, 74.86, 0.7),
    ("Belagavi", "Karnataka", 15.85, 74.50, 0.6), ("Udaipur", "Rajasthan", 24.58, 73.68, 0.7),
    ("Shimla", "Himachal Pradesh", 31.10, 77.17, 0.2), ("Panaji", "Goa", 15.50, 73.83, 0.2),
    ("Puducherry", "Puducherry", 11.93, 79.83, 0.9), ("Imphal", "Manipur", 24.82, 93.94, 0.4),
    ("Shillong", "Meghalaya", 25.58, 91.89, 0.4), ("Gangtok", "Sikkim", 27.34, 88.61, 0.1),
    ("Agartala", "Tripura", 23.83, 91.28, 0.5), ("Aizawl", "Mizoram", 23.73, 92.72, 0.3),
    ("Kohima", "Nagaland", 25.67, 94.11, 0.2), ("Itanagar", "Arunachal Pradesh", 27.08, 93.62, 0.1),
    ("Jammu", "Jammu and Kashmir", 32.73, 74.87, 0.7), ("Port Blair", "Andaman and Nicobar", 11.62, 92.73, 0.15),
    ("Thrissur", "Kerala", 10.53, 76.21, 0.6), ("Kozhikode", "Kerala", 11.26, 75.78, 2.0),
    ("Tirupati", "Andhra Pradesh", 13.63, 79.42, 0.5), ("Nellore", "Andhra Pradesh", 14.44, 79.99, 0.6),
    ("Rajahmundry", "Andhra Pradesh", 17.00, 81.78, 0.6), ("Kurnool", "Andhra Pradesh", 15.83, 78.04, 0.6),
    ("Moradabad", "Uttar Pradesh", 28.84, 78.78, 1.0), ("Gaya", "Bihar", 24.80, 85.00, 0.5),
    ("Muzaffarpur", "Bihar", 26.12, 85.39, 0.5), ("Bhagalpur", "Bihar", 25.24, 86.97, 0.5),
    ("Rourkela", "Odisha", 22.26, 84.85, 0.6), ("Sambalpur", "Odisha", 21.47, 83.97, 0.3),
    ("Haridwar", "Uttarakhand", 29.95, 78.16, 0.4), ("Mathura", "Uttar Pradesh", 27.49, 77.67, 0.6),
    ("Rohtak", "Haryana", 28.89, 76.61, 0.5), ("Panipat", "Haryana", 29.39, 76.97, 0.6),
    ("Ambala", "Haryana", 30.38, 76.78, 0.5), ("Bathinda", "Punjab", 30.21, 74.95, 0.4),
    ("Patiala", "Punjab", 30.34, 76.39, 0.5), ("Thane", "Maharashtra", 19.22, 72.98, 2.0),
    ("Bhavnagar", "Gujarat", 21.76, 72.15, 0.7), ("Gandhinagar", "Gujarat", 23.22, 72.65, 0.3),
    ("Kakinada", "Andhra Pradesh", 16.99, 82.25, 0.5), ("Saharanpur", "Uttar Pradesh", 29.97, 77.55, 0.7),
    ("Bilaspur", "Chhattisgarh", 22.08, 82.15, 0.4), ("Dibrugarh", "Assam", 27.48, 94.91, 0.2),
    ("Leh", "Ladakh", 34.15, 77.58, 0.05), ("Silvassa", "Dadra and Nagar Haveli and Daman and Diu", 20.27, 73.01, 0.1),
]

# Zone kinds in the order they are assigned (bigger cities get more zones).
ZONE_KINDS = [
    "CBD", "Railway Station", "Market Area", "Ring Road", "Highway Bypass",
    "Residential Arterial", "IT / Business Park", "Airport Corridor",
    "Old City", "University / Hospital",
]


def zones_per_city(pop_m):
    if pop_m >= 10:
        return 10
    if pop_m >= 3:
        return 8
    if pop_m >= 1.5:
        return 6
    return 5


ZONES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "zones.json")

# How far from the centre each zone kind sits, as a fraction of the city radius.
FAR = {"CBD": 0.15, "Old City": 0.25, "Railway Station": 0.3, "Market Area": 0.35,
       "University / Hospital": 0.5, "Residential Arterial": 0.55, "Ring Road": 0.7,
       "IT / Business Park": 0.75, "Airport Corridor": 0.9, "Highway Bypass": 1.0}


def place_zone(lat, lon, pop_m, kind, rng, shrink=1.0):
    """One candidate (lat, lon) for a zone: random bearing, kind-dependent distance from the centre."""
    radius_km = 3.0 + 2.2 * math.sqrt(pop_m)  # bigger cities spread wider
    r = radius_km * FAR[kind] * rng.uniform(0.85, 1.15) * shrink
    theta = rng.uniform(0, 2 * math.pi)
    dlat = (r * math.cos(theta)) / 111.0
    dlon = (r * math.sin(theta)) / (111.0 * math.cos(math.radians(lat)))
    return round(lat + dlat, 5), round(lon + dlon, 5)


def zone_record(city, state, pop, kind, lat, lon):
    return {
        "city": city, "state": state, "population_m": pop, "zone_kind": kind,
        "location_name": f"{city} - {kind}",
        "road_name": {"Ring Road": f"{city} Ring Road", "Highway Bypass": f"{city} Bypass (NH)",
                      "Airport Corridor": f"{city} Airport Road"}.get(kind, f"{kind} zone, {city}"),
        "latitude": lat, "longitude": lon,
    }


def build_zones():
    """
    Zones as generated by tools/generate_zones.py, which places every zone on land
    (checked against Natural Earth coastlines) so coastal cities have no zones in the sea.
    """
    with open(ZONES_FILE, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    z = build_zones()
    print(len(CITIES), "cities,", len(z), "zones,", len({s for _, s, *_ in CITIES}), "states/UTs")
