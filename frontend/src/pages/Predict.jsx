import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getJSON, useApi, useTitle, useUserLocation } from "../api.js";
import DayChart from "../components/DayChart.jsx";
import { ErrorBox, LevelBadge, Panel } from "../components/ui.jsx";
import { LEVEL_COLORS } from "../utils.js";

/** Current IST wall-clock as a datetime-local value. */
const nowIST = () => new Date().toLocaleString("sv-SE", { timeZone: "Asia/Kolkata" }).slice(0, 16).replace(" ", "T");

function Gauge({ score, level }) {
  const r = 54, c = 2 * Math.PI * r, arc = 0.75; // 270° dial
  return (
    <svg viewBox="0 0 140 140" className="gauge" role="img" aria-label={`Congestion ${score} out of 100`}>
      <g transform="rotate(135 70 70)" fill="none" strokeLinecap="round" strokeWidth="11">
        <circle cx="70" cy="70" r={r} stroke="#edf0f4" strokeDasharray={`${c * arc} ${c}`} />
        <circle cx="70" cy="70" r={r} stroke={LEVEL_COLORS[level]} strokeDasharray={`${c * arc * (score / 100)} ${c}`} />
      </g>
      <text x="70" y="72" textAnchor="middle" className="gauge-num">{score}</text>
      <text x="70" y="92" textAnchor="middle" className="gauge-sub">out of 100</text>
    </svg>
  );
}

export default function Predict() {
  useTitle("Saarthi — Predict traffic");
  const [params] = useSearchParams();
  const { data: cities, error: citiesErr } = useApi("/api/cities");
  const loc = useUserLocation();
  const touched = useRef(!!params.get("city"));

  const [city, setCity] = useState(params.get("city") || "");
  const [zone, setZone] = useState(params.get("zone") || "");
  const [when, setWhen] = useState(nowIST());
  const [weather, setWeather] = useState("auto");
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  // Default to the visitor's nearest city unless they (or a link) already chose one.
  useEffect(() => { if (!touched.current) loc.locate(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (loc.status === "ok" && !touched.current) {
      setCity(loc.near.city);
      setZone(String(loc.near.zone_id));
    }
  }, [loc.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const zones = cities?.find(c => c.city === city)?.zones ?? [];

  // Arriving via a link with ?city= (e.g. "Predict for this zone") runs the prediction straight away.
  const autoRan = useRef(false);
  useEffect(() => {
    if (cities && params.get("city") && !autoRan.current) { autoRan.current = true; submit(); }
  }, [cities]); // eslint-disable-line react-hooks/exhaustive-deps

  async function submit(e) {
    e?.preventDefault();
    if (!city) { setErr("Please choose a city."); return; }
    setBusy(true); setErr(null);
    try {
      setRes(await getJSON("/api/predict", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ city, zone_id: zone || null, datetime: when, weather }),
      }));
    } catch (ex) { setErr(ex.message); }
    finally { setBusy(false); }
  }

  const hour = res ? parseInt(res.datetime.slice(11, 13), 10) : null;
  return (
    <main className="container page">
      <div className="page-head">
        <div>
          <h1>Predict traffic</h1>
          <p>Forecast congestion and rush hour for any city or zone at any date and time (IST). The live weather forecast is used
            for about a week ahead; beyond that, dry weather is assumed.</p>
        </div>
      </div>
      {citiesErr && <ErrorBox message={citiesErr} />}

      <div className="grid predict">
        <Panel title="Parameters">
          <form onSubmit={submit} className="form">
            <label>City
              <select className="input" value={city} onChange={e => { touched.current = true; setCity(e.target.value); setZone(""); }}>
                <option value="">Choose a city</option>
                {cities?.map(c => <option key={c.city} value={c.city}>{c.city}, {c.state}</option>)}
              </select>
            </label>
            <label>Zone
              <select className="input" value={zone} onChange={e => setZone(e.target.value)} disabled={!city}>
                <option value="">Whole city (average of zones)</option>
                {zones.map(z => <option key={z.id} value={z.id}>{z.name}</option>)}
              </select>
            </label>
            <label>Date and time
              <div className="row">
                <input type="datetime-local" className="input" value={when} min="2023-01-01T00:00" max="2031-12-31T23:59"
                  onChange={e => setWhen(e.target.value)} required />
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setWhen(nowIST())}>Now</button>
              </div>
            </label>
            <label>Weather
              <select className="input" value={weather} onChange={e => setWeather(e.target.value)}>
                <option value="auto">Auto (live forecast)</option>
                <option value="dry">Assume dry</option>
                <option value="light">Assume light rain</option>
                <option value="heavy">Assume heavy rain</option>
              </select>
            </label>
            <button className="btn btn-primary btn-block" type="submit" disabled={busy}>{busy ? "Predicting…" : "Predict"}</button>
            {loc.status === "loading" && <div className="muted small">Finding your nearest city…</div>}
          </form>
        </Panel>

        <div>
          {err && <ErrorBox message={err} />}
          {!res && !err && (
            <section className="panel placeholder-box">
              <div className="muted">Choose a city and a time, then select <b>Predict</b>.</div>
            </section>
          )}
          {res && (
            <Panel>
              <div className="result-head">
                {res.datetime.replace(" ", " at ")} IST{res.holiday ? ` · ${res.holiday}` : ""}
              </div>
              <div className="result-top">
                <Gauge score={res.score} level={res.level} />
                <div>
                  <LevelBadge level={res.level} big />
                  <div className="range">80% likely range <b>{res.low}–{res.high}</b>
                    <span className="muted"> ({res.low_level === res.high_level ? res.low_level : `${res.low_level} to ${res.high_level}`})</span></div>
                  <div className={"rushflag " + (res.is_rush_hour ? "yes" : "no")}>
                    {res.is_rush_hour ? "Rush hour" : "Not rush hour"}
                    {!res.is_rush_hour && res.nearest_rush && <span className="muted"> · nearest rush {res.nearest_rush}</span>}
                  </div>
                </div>
              </div>
              <div className="grid facts">
                <div><span>Rush windows that day</span><b>{res.rush_windows.length ? res.rush_windows.map(w => w.label).join(", ") : "none"}</b></div>
                <div><span>Weather used</span><b>{res.weather_mode} · {res.precip_mm} mm/h</b></div>
              </div>
              <DayChart curve={res.day_curve} windows={res.rush_windows} nowHour={hour} height={240} />
            </Panel>
          )}
        </div>
      </div>
    </main>
  );
}
