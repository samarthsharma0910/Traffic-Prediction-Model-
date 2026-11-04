import { useEffect } from "react";
import L from "leaflet";
import { CircleMarker, MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import { Link } from "react-router-dom";
import { LEVEL_COLORS } from "../utils.js";
import { LevelBadge } from "./ui.jsx";

// OpenStreetMap tiles need no API key.
const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const userIcon = L.divIcon({ className: "user-dot", html: "<span></span>", iconSize: [16, 16], iconAnchor: [8, 8] });

function Focus({ focus }) {
  const map = useMap();
  useEffect(() => {
    if (!focus) return;
    if (focus.bounds) map.fitBounds(focus.bounds, { padding: [30, 30], maxZoom: 13 });
    else map.flyTo(focus.center, focus.zoom ?? 11, { duration: 0.8 });
  }, [focus, map]);
  useEffect(() => {
    const t = setTimeout(() => map.invalidateSize(), 60);
    return () => clearTimeout(t);
  }, [map]);
  return null;
}

/** zones: [{id,name,kind,city,lat,lon,score,level,speed_kmph,source}] */
export default function TrafficMap({ zones, user, focus, radius = 6, height = 520, linkCity = true, liveTiles = false }) {
  const sorted = [...zones].sort((a, b) => a.score - b.score); // worst drawn last, so on top
  return (
    <div className="map-box" style={{ height }}>
      <MapContainer center={[22.6, 79.5]} zoom={5} preferCanvas style={{ height: "100%", width: "100%" }} worldCopyJump>
        <TileLayer url={TILE_URL} maxZoom={18} attribution="&copy; OpenStreetMap contributors" />
        {liveTiles && <TileLayer url="/api/tiles/flow/{z}/{x}/{y}.png" opacity={0.9} zIndex={5} maxZoom={18} />}
        <Focus focus={focus} />
        {sorted.map(z => (
          <CircleMarker key={z.id} center={[z.lat, z.lon]} radius={radius}
            pathOptions={{ color: "#ffffff", weight: 1.5, fillColor: LEVEL_COLORS[z.level], fillOpacity: 0.95 }}>
            <Popup>
              <div className="pop">
                <b>{z.name}</b>
                <div><LevelBadge level={z.level} /> <span>{z.score}/100</span></div>
                <div className="muted">~{z.speed_kmph} km/h{z.source === "tomtom" ? "" : " (estimated)"}</div>
                {linkCity && <Link to={"/city/" + encodeURIComponent(z.city)}>{z.city} details</Link>}
              </div>
            </Popup>
          </CircleMarker>
        ))}
        {user && <Marker position={[user.lat, user.lon]} icon={userIcon}><Popup>You are here</Popup></Marker>}
      </MapContainer>
    </div>
  );
}
