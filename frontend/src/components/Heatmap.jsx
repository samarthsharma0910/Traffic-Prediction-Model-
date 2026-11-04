import { heatColor, hh } from "../utils.js";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function Heatmap({ grid }) {
  return (
    <div className="heat-wrap">
      <div className="heat">
        <div />
        {Array.from({ length: 24 }, (_, i) => (
          <div key={i} className="heat-h">{i % 3 === 0 ? String(i).padStart(2, "0") : ""}</div>
        ))}
        {grid.map((row, d) => (
          <div key={d} style={{ display: "contents" }}>
            <div className="heat-d">{DAYS[d]}</div>
            {row.map((v, i) => (
              <div key={i} className="heat-c" style={{ background: heatColor(v) }} title={`${DAYS[d]} ${hh(i)} · ${v}/100`} />
            ))}
          </div>
        ))}
      </div>
      <div className="heat-legend"><span>Free</span><i /><span>Jammed</span></div>
    </div>
  );
}
