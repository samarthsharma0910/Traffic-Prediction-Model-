import { useMemo, useState } from "react";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useNavigate } from "react-router-dom";
import { useApi, useTitle } from "../api.js";
import Icon from "../components/Icon.jsx";
import { CityLink, ErrorBox, LevelBadge, Metric, Panel, RushStatus, Skeleton } from "../components/ui.jsx";
import { LEVELS, LEVEL_COLORS, hh, levelFor } from "../utils.js";

const pct = v => `${(v * 100).toFixed(1)}%`;
const AXIS = { fill: "#64748b", fontSize: 12 };
const hourOf = s => parseInt(s, 10);

function Seg({ value, onChange, options, label }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map(([v, text]) => (
        <button key={v} className={value === v ? "on" : ""} aria-pressed={value === v} onClick={() => onChange(v)}>{text}</button>
      ))}
    </div>
  );
}

function RankTip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="tip">
      <b>{r.name}</b>{r.name !== r.state && <span className="muted"> · {r.state}</span>}
      {r.of ? (
        <div><i className="dot" style={{ background: LEVEL_COLORS[r.level] }} />{r.score} {r.level.toLowerCase()} {r.score === 1 ? "zone" : "zones"} of {r.of}</div>
      ) : (
        <>
          <div><i className="dot" style={{ background: LEVEL_COLORS[r.level] }} />{r.score}/100 · {r.level}</div>
          {r.rush ? <div className="muted"><RushStatus rush={r.rush} /></div> : <div className="muted">Average of {r.n} cities</div>}
        </>
      )}
    </div>
  );
}

export default function Dashboard() {
  useTitle("Saarthi — National dashboard");
  const navigate = useNavigate();
  const { data: ov, error } = useApi("/api/overview", { interval: 60000 });
  const { data: model } = useApi("/api/model-info");

  // Shared, cross-filtering state
  const [level, setLevel] = useState(null);       // congestion level (ranking)
  const [view, setView] = useState("cities");     // ranking by city or by state
  const [order, setOrder] = useState("most");
  const [topN, setTopN] = useState(15);
  const [date, setDate] = useState("");           // rush-hour date
  const [hour, setHour] = useState(null);         // clicked hour on the histogram
  const [q, setQ] = useState("");
  const [sort, setSort] = useState({ key: "peak_score", dir: "desc" });
  const rush = useApi(`/api/rush-hours${date ? `?date=${date}` : ""}`);

  // ---- ranking ----
  const levelCounts = useMemo(() => Object.fromEntries(LEVELS.map(l => [l, ov ? ov.zones.filter(z => z.level === l).length : 0])), [ov]);

  const ranking = useMemo(() => {
    if (!ov) return [];
    if (level) {  // rank by how many zones sit at the selected level
      const key = view === "cities" ? "city" : "state";
      const stateOf = new Map(ov.cities.map(c => [c.city, c.state]));
      const count = new Map(), total = new Map();
      for (const c of ov.cities) {
        const k = view === "cities" ? c.city : c.state;
        total.set(k, (total.get(k) || 0) + c.n_zones);
      }
      for (const z of ov.zones) {
        if (z.level !== level) continue;
        const k = key === "city" ? z.city : stateOf.get(z.city);
        count.set(k, (count.get(k) || 0) + 1);
      }
      const rowsZ = [...count].map(([name, c]) => ({
        name, state: view === "cities" ? stateOf.get(name) : name, score: c, level, of: total.get(name),
      }));
      rowsZ.sort((a, b) => (order === "most" ? b.score - a.score : a.score - b.score));
      return rowsZ.slice(0, topN);
    }
    let base;
    if (view === "cities") {
      base = ov.cities.map(c => ({ name: c.city, state: c.state, score: c.score, level: c.level, rush: c.rush, n: 1 }));
    } else {
      const m = new Map();
      for (const c of ov.cities) {
        const e = m.get(c.state) || { sum: 0, n: 0 };
        e.sum += c.score; e.n += 1; m.set(c.state, e);
      }
      base = [...m].map(([name, e]) => {
        const score = +(e.sum / e.n).toFixed(1);
        return { name, state: name, score, level: levelFor(score), n: e.n };
      });
    }
    base.sort((a, b) => (order === "most" ? b.score - a.score : a.score - b.score));
    return base.slice(0, topN);
  }, [ov, view, level, order, topN]);

  function openRow(r) {
    if (view === "cities") { navigate("/city/" + encodeURIComponent(r.name)); return; }
    setQ(r.name);                                    // state bar: filter the rush table to that state
    document.getElementById("rush-table")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---- rush hours across India ----
  const hist = useMemo(() => {
    const counts = Array.from({ length: 24 }, (_, h) => ({ h, label: hh(h), count: 0 }));
    for (const c of rush.data?.cities ?? []) for (const w of c.windows) for (let h = w.start; h < w.end && h < 24; h++) counts[h].count += 1;
    return counts;
  }, [rush.data]);

  const inRush = (c, h) => c.windows.some(w => w.start <= h && h < w.end);
  const rows = useMemo(() => {
    const n = q.trim().toLowerCase();
    const list = (rush.data?.cities ?? []).filter(r =>
      (!n || r.city.toLowerCase().includes(n) || r.state.toLowerCase().includes(n)) && (hour === null || inRush(r, hour)));
    const val = { city: r => r.city, windows: r => r.windows.length, peak_hour: r => hourOf(r.peak_hour), peak_score: r => r.peak_score }[sort.key];
    list.sort((a, b) => {
      const x = val(a), y = val(b);
      const c = typeof x === "string" ? x.localeCompare(y) : x - y;
      return sort.dir === "asc" ? c : -c;
    });
    return list;
  }, [rush.data, q, hour, sort]);

  const th = (key, text, cls) => (
    <th className={cls} aria-sort={sort.key === key ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}>
      <button className={"th-sort" + (sort.key === key ? " on " + sort.dir : "")}
        onClick={() => setSort(s => ({ key, dir: s.key === key ? (s.dir === "desc" ? "asc" : "desc") : key === "city" ? "asc" : "desc" }))}>{text}</button>
    </th>
  );

  const today = ov?.as_of.slice(0, 10);
  const nowHour = ov && rush.data && rush.data.date === today ? hourOf(ov.as_of.slice(11, 13)) : null;
  const n = ov?.national;
  const worst = ov?.cities[0];
  const peakHour = hist.reduce((a, b) => (b.count > a.count ? b : a), hist[0]);
  const rowH = 30;

  return (
    <main className="container page">
      <div className="page-head">
        <div>
          <h1>National dashboard</h1>
          <p>{ov ? `Updated ${ov.as_of} IST` : "Loading…"} · Select a level, a bar or an hour to filter the views below.</p>
        </div>
      </div>
      {error && !ov && <ErrorBox message={error} />}

      <div className="metrics" style={{ marginTop: 0 }}>
        <Metric label="National average" value={n && <>{n.avg}<small> /100</small></>} note={n && `${n.level} overall`} />
        <Metric label="Cities in rush hour" value={n?.cities_in_rush} note={n && `of ${n.n_cities} cities right now`} />
        <Metric label="Severe zones" value={n?.severe_zones} color={LEVEL_COLORS.Severe} note={n && `${n.heavy_zones} more are heavy`} />
        <Metric label="Most congested" value={worst && <CityLink city={worst.city} />} note={worst && `${worst.score}/100 · ${worst.state}`} />
      </div>

      <div className="grid two-wide">
        <Panel title={level ? `${view === "cities" ? "Cities" : "States"} with most ${level.toLowerCase()} zones` : "Congestion ranking"}
          subtitle={level ? `Number of zones at ${level.toLowerCase()} level · ${ranking.length} shown` : `Average congestion score, ${ranking.length} shown`}
          right={<>
            <Seg value={view} onChange={setView} label="Group by" options={[["cities", "Cities"], ["states", "States"]]} />
            <Seg value={order} onChange={setOrder} label="Order" options={[["most", "Most"], ["least", "Least"]]} />
            <Seg value={topN} onChange={setTopN} label="Rows" options={[[10, "10"], [15, "15"], [25, "25"]]} />
          </>}>
          {!ov ? <Skeleton h={420} /> : ranking.length === 0 ? <div className="empty">Nothing at this level right now.</div> : (
            <div style={{ height: ranking.length * rowH + 36 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={ranking} layout="vertical" margin={{ left: 4, right: 16, top: 0, bottom: 0 }} barCategoryGap={5}>
                  <XAxis type="number" domain={level ? [0, "dataMax"] : [0, 100]} allowDecimals={false} tick={AXIS} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey="name" width={view === "states" ? 150 : 112} interval={0} tick={{ ...AXIS, fill: "#17212b" }} axisLine={false} tickLine={false} />
                  <Tooltip cursor={{ fill: "#f1f5f9" }} content={<RankTip />} />
                  <Bar dataKey="score" radius={[0, 4, 4, 0]} cursor="pointer" isAnimationActive={false} onClick={openRow}>
                    {ranking.map(r => <Cell key={r.name} fill={LEVEL_COLORS[r.level]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
          <div className="muted small mt">{view === "cities" ? "Select a bar to open the city." : "Select a bar to list that state's cities in the table below."}</div>
        </Panel>

        <Panel title="Zones by level" subtitle="Select a level to rank cities by zones at that level"
          right={level && <button className="btn btn-secondary btn-sm" onClick={() => setLevel(null)}>Clear</button>}>
          <div className="levels">
            {LEVELS.map(l => {
              const total = n?.n_zones || 1;
              return (
                <button key={l} className={"lvl-row" + (level === l ? " on" : "") + (level && level !== l ? " dim" : "")}
                  onClick={() => setLevel(level === l ? null : l)} aria-pressed={level === l} disabled={!ov}>
                  <span className="lvl-top">
                    <span><i className="dot" style={{ background: LEVEL_COLORS[l] }} /> {l}</span>
                    <span><b>{levelCounts[l]}</b> <span className="muted small">{ov ? `${Math.round((levelCounts[l] / total) * 100)}%` : ""}</span></span>
                  </span>
                  <span className="lvl-track"><span style={{ width: `${(levelCounts[l] / total) * 100}%`, background: LEVEL_COLORS[l] }} /></span>
                </button>
              );
            })}
          </div>
          <p className="muted small mt">
            {ov ? `${n.n_zones} zones in ${n.n_cities} cities. ` : ""}Thresholds: Low under 30, Moderate under 55, Heavy under 75, Severe 75 and above.
          </p>
        </Panel>
      </div>

      <Panel title="Rush hours across India"
        subtitle={rush.data ? `Cities in a predicted rush window, by hour · ${rush.data.date}${peakHour?.count ? ` · busiest at ${peakHour.label} (${peakHour.count} cities)` : ""}` : "Loading…"}
        right={<>
          {hour !== null && <button className="btn btn-secondary btn-sm" onClick={() => setHour(null)}><Icon name="close" size={13} /> {hh(hour)}</button>}
          <input type="date" className="input sm" value={date || rush.data?.date || ""} min="2023-01-01" max="2031-12-31"
            onChange={e => { setDate(e.target.value); setHour(null); }} aria-label="Date" />
        </>}>
        {rush.error && <ErrorBox message={rush.error} onRetry={rush.reload} />}
        {!rush.data ? <Skeleton h={220} /> : (
          <div style={{ height: 230 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={hist} margin={{ top: 16, right: 8, left: -18, bottom: 0 }} barCategoryGap={3}>
                <XAxis dataKey="label" interval={2} tick={AXIS} axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} tick={AXIS} axisLine={false} tickLine={false} />
                <Tooltip cursor={{ fill: "#f1f5f9" }}
                  content={({ active, payload }) => active && payload?.length
                    ? <div className="tip"><b>{payload[0].payload.label}</b><div>{payload[0].payload.count} cities in rush</div><div className="muted small">Select to list them</div></div> : null} />
                <Bar dataKey="count" radius={[3, 3, 0, 0]} cursor="pointer" isAnimationActive={false} onClick={d => setHour(h => (h === d.h ? null : d.h))}>
                  {hist.map(b => <Cell key={b.h} fill={hour === null || hour === b.h ? "#1f5eff" : "#c9d8ff"} />)}
                </Bar>
                {nowHour !== null && <ReferenceLine x={hh(nowHour)} stroke="#d92d20" strokeWidth={1.5} label={{ value: "Now", fill: "#d92d20", fontSize: 12, position: "top" }} />}
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Panel>

      <Panel title="Rush windows by city" pad={false}
        subtitle={`${rows.length} of ${rush.data?.cities.length ?? "…"} cities${hour !== null ? ` · in rush at ${hh(hour)}` : ""}`}
        right={<input className="input sm" placeholder="Search city or state" value={q} onChange={e => setQ(e.target.value)} aria-label="Search city or state" />}>
        <div id="rush-table" className="table-wrap tall">
          <table>
            <thead>
              <tr>{th("city", "City")}{th("windows", "Rush windows")}{th("peak_hour", "Peak hour")}{th("peak_score", "Peak level")}</tr>
            </thead>
            <tbody>
              {!rush.data && <tr><td colSpan={4}><Skeleton h={80} /></td></tr>}
              {rows.map(r => (
                <tr key={r.city}>
                  <td><CityLink city={r.city} /><div className="muted small">{r.state}</div></td>
                  <td>{r.windows.length ? r.windows.map(w => <span key={w.start} className="rush-pill">{w.label}</span>) : <span className="muted">none</span>}</td>
                  <td>{r.peak_hour}</td>
                  <td><LevelBadge level={r.peak_level} /> <span className="muted small">{r.peak_score}</span></td>
                </tr>
              ))}
              {rush.data && rows.length === 0 && <tr><td colSpan={4} className="empty">No cities match</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="Model quality" subtitle={model ? `Evaluated on the last ${model.test_window_days} days, held out from training` : undefined}>
        {model ? (
          <>
            <div className="metrics" style={{ marginTop: 0 }}>
              <Metric label="Mean absolute error" value={model.mae} note={`vs ${model.baseline_mae} historical average`} />
              <Metric label="Error on rainy hours" value={model.mae_rainy} note={`vs ${model.baseline_mae_rainy} historical average`} />
              <Metric label="Level accuracy" value={pct(model.level_accuracy)} note={`${pct(model.level_within_one)} within one level`} />
              <Metric label="Peak hour within ±1 h" value={pct(model.peak_hour_within_1h)} note={`80% band covers ${pct(model.interval_80_coverage)}`} />
            </div>
            <details className="about">
              <summary>About the model and data</summary>
              <p>
                Gradient-boosted trees using location, hour, weekday, month, Indian public holidays and precipitation; it outputs an
                expected congestion score and an 80% range. Weather and a seven-day forecast come from Open-Meteo.
              </p>
              <p>
                Training history is {model.data_source.replace(/\s*-\s*see README.*/, "")}, so these scores show how well the model learned that
                pattern, not accuracy on real roads. Trained {model.trained_at} on {model.train_rows.toLocaleString()} hourly samples
                from {model.zones} zones in {model.cities} cities.
              </p>
            </details>
          </>
        ) : <Skeleton h={120} />}
      </Panel>
    </main>
  );
}
