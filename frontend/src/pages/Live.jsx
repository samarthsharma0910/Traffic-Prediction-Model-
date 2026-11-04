import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getJSON, useApi, useTitle, useUserLocation } from "../api.js";
import Icon from "../components/Icon.jsx";
import TrafficMap from "../components/TrafficMap.jsx";
import { CityLink, ErrorBox, LevelBadge, Metric, Panel, RushStatus, ScoreBar, Skeleton, SourceBadge } from "../components/ui.jsx";
import { LEVELS, LEVEL_COLORS } from "../utils.js";

const INDIA = { center: [22.6, 79.5], zoom: 5 };

export default function Live() {
  useTitle("Saarthi — Live traffic across India");
  const { data, error, reload } = useApi("/api/overview", { interval: 60000 });
  const loc = useUserLocation();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("score");
  const [level, setLevel] = useState(null);
  const [focus, setFocus] = useState(null);
  const [layer, setLayer] = useState(true);

  // Default view = the visitor's current location.
  useEffect(() => { loc.locate(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (loc.status === "ok") setFocus({ center: [loc.pos.lat, loc.pos.lon], zoom: 11 });
    else if (loc.status === "error" && loc.pos) setFocus({ ...INDIA });
  }, [loc.status]); // eslint-disable-line react-hooks/exhaustive-deps

  // With a TomTom key: pull measured speeds for the visitor's city now and every 5 min (matches the server cache).
  const liveEnabled = !!data?.live?.enabled;
  const nearCity = loc.near?.city;
  useEffect(() => {
    if (loc.status !== "ok" || !liveEnabled || !nearCity) return undefined;
    let stop = false;
    const pull = () => getJSON("/api/live/refresh", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ city: nearCity }),
    }).then(() => { if (!stop) reload(); }).catch(() => {});
    pull();
    const t = setInterval(() => { if (!document.hidden) pull(); }, 300000);
    return () => { stop = true; clearInterval(t); };
  }, [loc.status, nearCity, liveEnabled]); // eslint-disable-line react-hooks/exhaustive-deps

  const cities = useMemo(() => {
    if (!data) return [];
    const needle = q.trim().toLowerCase();
    const rows = data.cities.filter(c =>
      (!level || c.level === level) && (!needle || c.city.toLowerCase().includes(needle) || c.state.toLowerCase().includes(needle)));
    if (sort === "city") rows.sort((a, b) => a.city.localeCompare(b.city));
    else if (sort === "state") rows.sort((a, b) => a.state.localeCompare(b.state) || a.city.localeCompare(b.city));
    else rows.sort((a, b) => b.score - a.score);
    return rows;
  }, [data, q, sort, level]);

  const zones = useMemo(() => (data ? data.zones.filter(z => !level || z.level === level) : []), [data, level]);

  const here = useMemo(() => {
    if (!data || loc.status !== "ok") return null;
    const z = data.zones.find(x => x.id === loc.near.zone_id);
    const c = data.cities.find(x => x.city === loc.near.city);
    return z && c ? { z, c, km: loc.near.distance_km } : null;
  }, [data, loc.status, loc.near]);

  const n = data?.national;
  return (
    <>
      <section className="hero">
        <div className="container">
          <div className="eyebrow">
            <span className="dot" />
            {data ? `Updated ${data.as_of} IST · refreshes every minute` : "Loading live status…"}
          </div>
          <h1>Live traffic across <span>India</span></h1>
          <p className="hero-lead">
            Current congestion, forecasts and rush-hour windows for {n ? `${n.n_cities} cities and ${n.n_zones} monitoring zones` : "cities across the country"},
            estimated from time of day, location, holidays and live weather.
          </p>
          <div className="hero-actions">
            <button className="btn btn-primary" onClick={loc.locate} disabled={loc.status === "loading"}>
              <Icon name="locate" /> {loc.status === "loading" ? "Locating…" : "Use my location"}
            </button>
            <Link className="btn btn-secondary" to="/dashboard"><Icon name="chart" /> National dashboard</Link>
            {data && <SourceBadge source={data.source} weatherLive={data.weather_live} liveEnabled={liveEnabled} liveZones={n?.live_zones} />}
          </div>

          <div className="metrics">
            <Metric label="National average" value={n && <>{n.avg}<small> /100</small></>} note={n && `${n.level} overall`} />
            <Metric label="Cities in rush hour" value={n?.cities_in_rush} note={n && `of ${n.n_cities} cities`} />
            <Metric label="Severe zones" value={n?.severe_zones} color={LEVEL_COLORS.Severe} note={n && `of ${n.n_zones} zones`} />
            <Metric label="Heavy zones" value={n?.heavy_zones} color={LEVEL_COLORS.Heavy} note="Level 3 of 4" />
          </div>
        </div>
      </section>

      <main className="container page">
        {error && !data && <ErrorBox message={error} onRetry={reload} />}

        {here && (
          <section className="panel here">
            <div>
              <div className="here-label">Your location · nearest zone {here.km} km away</div>
              <div className="here-title"><CityLink city={here.c.city} />, <span className="muted">{here.c.state}</span></div>
              <div className="here-line">
                <span>{here.z.kind}</span> <LevelBadge level={here.z.level} /> <b>{here.z.score}</b><span className="muted">/100</span>
              </div>
            </div>
            <div className="here-side">
              <RushStatus rush={here.c.rush} />
              <Link className="link" to={`/predict?city=${encodeURIComponent(here.c.city)}&zone=${here.z.id}`}>Predict for this zone</Link>
            </div>
          </section>
        )}
        {loc.status === "error" && !here && <div className="notice">{loc.error}</div>}

        <div className="filters" role="group" aria-label="Filter by congestion level">
          <span className="label">Show</span>
          <button className={"filter" + (!level ? " on" : "")} onClick={() => setLevel(null)}>All levels</button>
          {LEVELS.map(l => (
            <button key={l} className={"filter" + (level === l ? " on" : "")} onClick={() => setLevel(level === l ? null : l)}>
              <i style={{ background: LEVEL_COLORS[l] }} /> {l}
            </button>
          ))}
          {liveEnabled && (
            <button className={"filter push" + (layer ? " on" : "")} onClick={() => setLayer(l => !l)} aria-pressed={layer}>
              Live traffic layer
            </button>
          )}
        </div>

        <div className="grid live">
          <Panel title="Zone map" subtitle="Marker colour shows the current congestion level" pad={false}
            right={data && <span className="tag">{zones.length} zones</span>}>
            {data ? <TrafficMap zones={zones} user={loc.status === "ok" ? loc.pos : null} focus={focus} height={560} liveTiles={liveEnabled && layer} /> : <Skeleton h={560} />}
          </Panel>

          <Panel title="Cities" subtitle={data ? `${cities.length} shown` : undefined} pad={false}
            right={
              <select className="input sm" value={sort} onChange={e => setSort(e.target.value)} aria-label="Sort cities">
                <option value="score">Most congested</option>
                <option value="city">City A–Z</option>
                <option value="state">State A–Z</option>
              </select>
            }>
            <div className="list-search">
              <input className="input" placeholder="Search city or state" value={q} onChange={e => setQ(e.target.value)} aria-label="Search cities" />
            </div>
            <div className="city-list">
              {!data && Array.from({ length: 7 }, (_, i) => <Skeleton key={i} h={58} />)}
              {data && cities.length === 0 && <div className="empty">No matching city</div>}
              {cities.map((c, i) => (
                <div key={c.city} className="city-row" role="button" tabIndex={0}
                  onClick={() => setFocus({ center: [c.lat, c.lon], zoom: 11 })}
                  onKeyDown={e => { if (e.key === "Enter") navigate("/city/" + encodeURIComponent(c.city)); }}>
                  <span className="rank">{sort === "score" && !q && !level ? i + 1 : ""}</span>
                  <div>
                    <div className="city-name">{c.city}<span>{c.state}</span></div>
                    <ScoreBar score={c.score} level={c.level} />
                    <div className="city-rush"><RushStatus rush={c.rush} /></div>
                  </div>
                  <div className="city-score"><LevelBadge level={c.level} /><b>{c.score}</b></div>
                  <Link className="city-go" to={"/city/" + encodeURIComponent(c.city)} onClick={e => e.stopPropagation()}
                    aria-label={`${c.city} details`}><Icon name="chevron" /></Link>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </main>
    </>
  );
}
