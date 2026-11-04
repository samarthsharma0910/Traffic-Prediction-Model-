import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi, useTitle } from "../api.js";
import DayChart from "../components/DayChart.jsx";
import Heatmap from "../components/Heatmap.jsx";
import Icon from "../components/Icon.jsx";
import TrafficMap from "../components/TrafficMap.jsx";
import { ErrorBox, LevelBadge, Metric, Panel, RushStatus, ScoreBar, Skeleton, SourceBadge } from "../components/ui.jsx";
import { hh } from "../utils.js";

const WEATHER = [["auto", "Forecast"], ["dry", "Dry"], ["light", "Light rain"], ["heavy", "Heavy rain"]];

function CityView({ city }) {
  useTitle(`Saarthi — ${city} traffic`);
  const [date, setDate] = useState("");
  const [weather, setWeather] = useState("auto");

  const url = `/api/city/${encodeURIComponent(city)}?weather=${weather}${date ? `&date=${date}` : ""}`;
  const { data: d, error, loading, reload } = useApi(url, { interval: date || weather !== "auto" ? 0 : 60000 });

  const focus = useMemo(() => {
    if (!d || !d.zones.length) return null;
    const lats = d.zones.map(z => z.lat), lons = d.zones.map(z => z.lon);
    return { bounds: [[Math.min(...lats), Math.min(...lons)], [Math.max(...lats), Math.max(...lons)]] };
  }, [d?.city]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error && !d) {
    return (
      <main className="container page">
        <Link to="/" className="crumb"><Icon name="back" /> All India</Link>
        <div className="page-head"><h1>{city}</h1></div>
        <ErrorBox message={error} onRetry={reload} />
      </main>
    );
  }

  const live = d && d.is_today && weather === "auto";
  const nowHour = live ? parseInt(d.as_of.slice(11, 13), 10) : null;
  const w = d?.weather;
  const weatherLine = d && [
    d.is_today && w.temp != null && `${w.temp}°C`,
    d.is_today && w.precip_now > 0 && `raining now (${w.precip_now} mm)`,
    w.override ? `what-if: ${w.override} weather` : w.forecast_known ? `${w.rain_hours} rainy hour(s) forecast` : "weather forecast unavailable for this date (assumed dry)",
    d.holiday && `holiday: ${d.holiday}`,
  ].filter(Boolean).join(" · ");

  return (
    <main className="container page">
      <div>
        <Link to="/" className="crumb"><Icon name="back" /> All India</Link>
        <div className="page-head">
          <div>
            <h1>{city}{d && <small>{d.state}</small>}</h1>
            {d ? (
              <div className="hero-line">
                <LevelBadge level={d.level} big /> <span className="big-score">{d.score}</span>
                <span className="muted">/100 {live ? "now" : "· average of zone peaks"}</span>
              </div>
            ) : <Skeleton h={40} />}
            <p>{weatherLine}</p>
          </div>
          <div className="head-side">
            {d && <SourceBadge source={d.source} weatherLive={d.weather.live} liveEnabled={d.live?.enabled} liveZones={d.zones.filter(z => z.source === "tomtom").length} />}
            <div className="controls">
              <input type="date" className="input sm" value={date || d?.date || ""} min="2023-01-01" max="2031-12-31"
                onChange={e => setDate(e.target.value)} aria-label="Date" />
              <button className="btn btn-secondary btn-sm" onClick={() => setDate("")}>Today</button>
            </div>
            <div className="seg" role="group" aria-label="Weather scenario">
              {WEATHER.map(([v, label]) => (
                <button key={v} className={weather === v ? "on" : ""} onClick={() => setWeather(v)}>{label}</button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {error && d && <ErrorBox message={error} onRetry={reload} />}

      <div className={"fade" + (loading ? " dim" : "")}>
        <div className="grid kpis">
          <Panel title="Predicted rush hours" subtitle={d ? "Hours in the top of the day's congestion range" : undefined}>
            {d ? (d.rush.length ? d.rush.map(r => (
              <div key={r.start} className="rush-item"><span className="rush-pill">{r.label}</span>
                <span className="muted small">peak {hh(r.peak_hour)} · {r.peak_level}</span></div>
            )) : <span className="muted">No distinct rush hour predicted.</span>) : <Skeleton h={50} />}
            {d?.next_rush && <div className="mt"><RushStatus rush={d.next_rush} /></div>}
          </Panel>
          <Metric label="Best time to travel" value={d && <span className="kpi good">{d.best_hour.label}</span>} note={d && `Score ${d.best_hour.score} · 06:00–22:00`} />
          <Metric label="Worst time to travel" value={d && <span className="kpi bad">{d.worst_hour.label}</span>} note={d && `Score ${d.worst_hour.score} · 06:00–22:00`} />
        </div>

        <Panel title="Predicted congestion through the day"
          subtitle="Line is the expected score, the band is the 80% likely range, tinted columns are rush windows"
          right={<span className="tag">Hourly</span>}>
          {d ? <DayChart curve={d.curve} windows={d.rush} nowHour={nowHour} height={320} /> : <Skeleton h={320} />}
        </Panel>

        <div className="grid two">
          <Panel title="Zones" subtitle={live ? "Current status of each zone" : "Each zone's peak for the selected day"} pad={false}>
            {d ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Zone</th><th>Level</th><th>Score (range)</th><th>Speed</th><th /></tr>
                  </thead>
                  <tbody>
                    {d.zones.map(z => (
                      <tr key={z.id}>
                        <td><b>{z.kind}</b>{z.road !== `${z.kind} zone, ${d.city}` && <div className="muted small">{z.road}</div>}</td>
                        <td><LevelBadge level={z.level} /></td>
                        <td>
                          <b>{z.score}</b>{z.source !== "tomtom" && <span className="muted small"> ({z.low}–{z.high})</span>}
                          <ScoreBar score={z.score} level={z.level} />
                        </td>
                        <td>{z.speed_kmph} km/h{z.source !== "tomtom" && <span className="muted small"> est.</span>}</td>
                        <td><Link className="link" to={`/predict?city=${encodeURIComponent(d.city)}&zone=${z.id}`}>Predict</Link></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <Skeleton h={300} />}
          </Panel>
          <Panel title="Zone map" pad={false}>
            {d ? <TrafficMap zones={d.zones.map(z => ({ ...z, name: `${d.city} – ${z.kind}` }))} focus={focus} radius={10} height={380} linkCity={false} liveTiles={!!d.live?.enabled} /> : <Skeleton h={380} />}
          </Panel>
        </div>

        <Panel title="Typical week" subtitle="Average congestion of all zones on a dry, non-holiday day">
          {d ? <Heatmap grid={d.weekly} /> : <Skeleton h={180} />}
        </Panel>
      </div>
    </main>
  );
}

/** Keyed by city so state (date, weather, cached data) resets when navigating between cities. */
export default function City() {
  const { city } = useParams();
  return <CityView key={city} city={city} />;
}
