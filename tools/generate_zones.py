"""
One-off generator for data/zones.json: places every monitoring zone ON LAND.

Zones start at a deterministic random bearing/distance from the city centre
(cities.place_zone). Any candidate that is not on land - tested against Natural
Earth 10m land polygons - is re-drawn at a shrinking radius until it is.

Usage (needs `pip install shapely` and the Natural Earth land GeoJSON, e.g.
https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_land.geojson):

    python -I tools/generate_zones.py <path/to/ne_10m_land.geojson>
"""
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from shapely.geometry import Point, box, shape  # noqa: E402
from shapely.ops import unary_union  # noqa: E402
from shapely.prepared import prep  # noqa: E402

from cities import CITIES, ZONE_KINDS, ZONES_FILE, place_zone, zone_record, zones_per_city  # noqa: E402

INDIA_BOX = box(66, 5, 99, 38)
# NE 10m coastlines are generalised to ~1-2 km, so prefer zones well inland of the line (0.02 deg ~ 2 km),
# and only relax the margin for narrow peninsulas/islands (Kochi, Panaji, ...) where nothing fits.
MARGINS = (0.02, 0.01, 0.004)
MIN_SEP = 0.006  # ~650 m between zones of the same city, so markers don't stack


def load_land(path):
    with open(path, encoding="utf-8") as f:
        feats = json.load(f)["features"]
    parts = []
    for ft in feats:
        g = shape(ft["geometry"])
        if g.intersects(INDIA_BOX):
            parts.append(g.intersection(INDIA_BOX))
    return prep(unary_union(parts))


def on_land(land, lat, lon, margin):
    return all(land.contains(Point(lon + dx, lat + dy))
               for dx, dy in ((0, 0), (margin, 0), (-margin, 0), (0, margin), (0, -margin)))


def apart(pos, placed):
    return all(abs(pos[0] - p[0]) > MIN_SEP or abs(pos[1] - p[1]) > MIN_SEP for p in placed)


def main(land_path):
    land = load_land(land_path)
    zones, relaxed, fallbacks = [], [], []
    for city, state, lat, lon, pop in CITIES:
        rng = random.Random(f"zones:{city}")
        placed = []
        for kind in ZONE_KINDS[: zones_per_city(pop)]:
            pos, used = None, None
            for margin in MARGINS:
                cand = place_zone(lat, lon, pop, kind, rng)
                for tries in range(80):
                    if on_land(land, *cand, margin) and apart(cand, placed):
                        pos, used = cand, margin
                        break
                    cand = place_zone(lat, lon, pop, kind, rng, shrink=max(0.15, 0.97 ** (tries + 1)))
                if pos:
                    break
            if pos is None:  # last resort: the centre itself, nudged so markers don't stack exactly
                pos = (round(lat + 0.002 * len(placed), 5), round(lon, 5))
                fallbacks.append(f"{city}/{kind}")
            elif used != MARGINS[0]:
                relaxed.append(f"{city}/{kind}")
            placed.append(pos)
            zones.append(zone_record(city, state, pop, kind, *pos))

    bad = [z["location_name"] for z in zones if not on_land(land, z["latitude"], z["longitude"], 0.0)]
    os.makedirs(os.path.dirname(ZONES_FILE), exist_ok=True)
    with open(ZONES_FILE, "w", encoding="utf-8") as f:
        json.dump(zones, f, indent=1)
    print(f"{len(zones)} zones written to {ZONES_FILE}")
    print(f"{len(relaxed)} placed with a relaxed coastal margin: {relaxed}")
    print(f"{len(fallbacks)} fell back to the city centre: {fallbacks}")
    print(f"{len(bad)} zones not on land at all: {bad}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
