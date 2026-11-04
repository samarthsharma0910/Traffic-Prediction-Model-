import { Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { LEVEL_COLORS, THRESHOLDS, hh, levelFor } from "../utils.js";

const AXIS = { fill: "#64748b", fontSize: 12 };

function Tip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0].payload;
  return (
    <div className="tip">
      <b>{p.label}</b>
      <div><i className="dot" style={{ background: LEVEL_COLORS[levelFor(p.mean)] }} />{p.mean}/100 · {levelFor(p.mean)}</div>
      <div className="muted">80% range {p.lo}–{p.hi}</div>
    </div>
  );
}

/** 24h forecast: line = expected, shaded band = 80% interval, tinted columns = rush windows. */
export default function DayChart({ curve, windows = [], nowHour = null, height = 300 }) {
  const data = curve.mean.map((m, h) => ({
    h, label: hh(h), mean: m, lo: curve.lo[h], hi: curve.hi[h], range: +(curve.hi[h] - curve.lo[h]).toFixed(1),
  }));
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 22, right: 12, left: -12, bottom: 0 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          {windows.map(w => (
            <ReferenceArea key={w.start} x1={hh(w.start)} x2={hh(Math.min(23, w.end - 1))}
              fill="#d92d20" fillOpacity={0.07} strokeOpacity={0} />
          ))}
          {THRESHOLDS.map(t => (
            <ReferenceLine key={t} y={t} stroke="#98a2b3" strokeDasharray="3 5" strokeOpacity={0.7} />
          ))}
          <XAxis dataKey="label" interval={2} tick={AXIS} tickLine={false} axisLine={false} />
          <YAxis domain={[0, 100]} ticks={[0, 30, 55, 75, 100]} tick={AXIS} tickLine={false} axisLine={false} />
          <Tooltip content={<Tip />} cursor={{ stroke: "#98a2b3", strokeOpacity: 0.6 }} />
          <Area dataKey="lo" stackId="b" stroke="none" fill="transparent" isAnimationActive={false} />
          <Area dataKey="range" stackId="b" stroke="none" fill="#1f5eff" fillOpacity={0.12} isAnimationActive={false} />
          <Line dataKey="mean" stroke="#1f5eff" strokeWidth={2.5} dot={false} activeDot={{ r: 5 }} isAnimationActive={false} />
          {nowHour !== null && (
            <ReferenceLine x={hh(nowHour)} stroke="#d92d20" strokeWidth={1.5}
              label={{ value: "Now", fill: "#d92d20", fontSize: 12, position: "top" }} />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
