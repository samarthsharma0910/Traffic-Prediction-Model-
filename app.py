"""
FastAPI backend - live traffic status, ML forecasts and rush-hour prediction across India.
Also serves the built React app (frontend/dist) so one command runs everything.

Run:  python setup.py   (once: DB + model)   then   python app.py
Dev:  python app.py  +  cd frontend && npm run dev   (Vite proxies /api to :8000)
"""
import os
import sys
from datetime import date as date_cls, datetime
from typing import Any, Optional

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import live_provider
from config import BASE_DIR, now_ist
from service import MAX_DATE, MIN_DATE, TrafficService

DIST = os.path.join(BASE_DIR, "frontend", "dist")

app = FastAPI(title="Traffic Management India", version="2.0")
app.add_middleware(GZipMiddleware, minimum_size=1000)

service = TrafficService()
if not os.environ.get("TRAFFIC_DISABLE_WEATHER"):
    service.start()  # background weather refresh; never blocks requests

WEATHER_CHOICES = {"auto": None, "dry": "dry", "light": "light", "heavy": "heavy"}


# ------------------------------------------------------------------ parsing helpers
def bad(msg):
    return HTTPException(status_code=400, detail=msg)


def parse_date(raw: Optional[str]):
    if not raw:
        return None
    try:
        d = date_cls.fromisoformat(raw)
    except ValueError:
        raise bad("date must be YYYY-MM-DD")
    if not MIN_DATE <= d <= MAX_DATE:
        raise bad(f"date must be between {MIN_DATE} and {MAX_DATE}")
    return d


def parse_datetime(raw: Optional[str]):
    if not raw:
        return now_ist()
    try:
        dt = datetime.fromisoformat(str(raw).replace(" ", "T"))
    except ValueError:
        raise bad("datetime must be YYYY-MM-DDTHH:MM (IST)")
    if dt.tzinfo is not None:
        raise bad("datetime must not include a timezone; it is interpreted as IST")
    if not MIN_DATE <= dt.date() <= MAX_DATE:
        raise bad(f"date must be between {MIN_DATE} and {MAX_DATE}")
    return dt.replace(second=0, microsecond=0)


def parse_weather(raw: Optional[str]):
    raw = (raw or "auto").lower()
    if raw not in WEATHER_CHOICES:
        raise bad("weather must be one of: auto, dry, light, heavy")
    return WEATHER_CHOICES[raw]


def require_city(name: str):
    if name not in service.city_idx:
        raise HTTPException(status_code=404, detail=f"Unknown city '{name}'")
    return name


# ------------------------------------------------------------------ error shape: {"error": "..."}
@app.exception_handler(HTTPException)
async def _http_error(request, exc: HTTPException):
    return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def _validation_error(request, exc: RequestValidationError):
    e = exc.errors()[0]
    where = ".".join(str(p) for p in e["loc"] if p not in ("query", "body", "path"))
    return JSONResponse({"error": f"Invalid {where or 'request'}: {e['msg']}"}, status_code=400)


@app.exception_handler(Exception)
async def _unhandled(request, exc: Exception):
    import logging
    logging.getLogger("uvicorn.error").exception("Unhandled error", exc_info=exc)
    return JSONResponse({"error": "Internal server error"}, status_code=500)


# ------------------------------------------------------------------ API (sync defs run in a threadpool)
@app.get("/api/overview")
@app.get("/api/live-traffic", include_in_schema=False)  # backwards compatibility
def api_overview():
    return {**service.overview(), "live": live_provider.status()}


@app.get("/api/cities")
def api_cities():
    cities = sorted(service.city_meta.values(), key=lambda m: m["city"])
    return [{**m, "zones": [{"id": service.zones[i]["location_id"], "name": service.zones[i]["zone_kind"]}
                            for i in service.city_zones[m["city"]]]} for m in cities]


@app.get("/api/city/{city_name:path}")
def api_city(city_name: str, date: Optional[str] = None, weather: Optional[str] = None):
    require_city(city_name)
    return {**service.city_detail(city_name, parse_date(date), parse_weather(weather)), "live": live_provider.status()}


@app.get("/api/zone/{zone_id}")
def api_zone(zone_id: int, date: Optional[str] = None, weather: Optional[str] = None):
    out = service.zone_detail(zone_id, parse_date(date), parse_weather(weather))
    if out is None:
        raise HTTPException(status_code=404, detail=f"Unknown zone {zone_id}")
    return out


def _predict(city: Optional[str], zone_id: Any, when: Optional[str], weather: Optional[str]):
    city = (city or "").strip()
    if not city:
        raise bad("city is required")
    require_city(city)
    if zone_id in (None, "", 0):
        zone_id = None
    else:
        try:
            zone_id = int(zone_id)
        except (TypeError, ValueError):
            raise bad("zone_id must be an integer")
        if service.zone_idx.get(zone_id) is None or service.zone_city[service.zone_idx[zone_id]] != city:
            raise bad("zone_id does not belong to that city")
    return service.predict_at(city, zone_id, parse_datetime(when), parse_weather(weather))


@app.get("/api/predict")
def api_predict_get(city: Optional[str] = None, zone_id: Optional[str] = None,
                    datetime: Optional[str] = None, weather: Optional[str] = None):
    return _predict(city, zone_id, datetime, weather)


@app.post("/api/predict")
def api_predict_post(body: dict = Body(...)):
    return _predict(body.get("city"), body.get("zone_id"), body.get("datetime"), body.get("weather"))


@app.post("/api/live/refresh")
def api_live_refresh(body: dict = Body(...)):
    """Fetch measured TomTom speeds for one city (e.g. the visitor's). No-op without a key."""
    city = require_city((body.get("city") or "").strip())
    n = service.refresh_live(city) if live_provider.enabled() else 0
    return {"city": city, "live_zones": n, "live": live_provider.status()}


@app.get("/api/tiles/flow/{z}/{x}/{y}.png")
def api_flow_tile(z: int, x: int, y: int):
    """Live traffic raster tile, proxied so the TomTom key stays on the server."""
    img = live_provider.fetch_tile(z, x, y)
    if img is None:
        return Response(status_code=204)
    return Response(img, media_type="image/png", headers={"Cache-Control": "public, max-age=60"})


@app.get("/api/rush-hours")
def api_rush_hours(date: Optional[str] = None):
    return service.rush_table(parse_date(date))


@app.get("/api/nearest")
def api_nearest(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)):
    hit = service.nearest_zone(lat, lon)
    if hit is None:
        raise HTTPException(status_code=404, detail="No monitored zone within 60 km of that point")
    return hit


@app.get("/api/model-info")
def api_model_info():
    return service.model_info()


@app.get("/healthz")
def healthz():
    return {"status": "ok", "zones": len(service.zones), "weather_live": service.weather.available,
            "live_provider": "tomtom" if live_provider.enabled() else "none (ML-estimated)",
            "live": live_provider.status()}


# ------------------------------------------------------------------ React app (SPA)
if os.path.isdir(os.path.join(DIST, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")

NO_BUILD = """<h2>Frontend not built</h2><p>Run <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code>,
then reload. The API is already available at <a href="/docs">/docs</a>.</p>"""


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse({"error": "Not found"}, status_code=404)
    # serve real files from dist (favicon etc.) - resolved safely inside DIST
    candidate = os.path.realpath(os.path.join(DIST, full_path))
    if full_path and candidate.startswith(os.path.realpath(DIST) + os.sep) and os.path.isfile(candidate):
        return FileResponse(candidate)
    index = os.path.join(DIST, "index.html")
    if os.path.isfile(index):
        return FileResponse(index)
    return HTMLResponse(NO_BUILD, status_code=503)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    print(f"Traffic Management India -> http://127.0.0.1:{port}   (API docs: /docs)")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
