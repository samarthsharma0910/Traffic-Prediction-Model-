import { Link } from "react-router-dom";
import { LEVEL_COLORS, fmtMin } from "../utils.js";

export const LevelBadge = ({ level, big }) => (
  <span className={`badge badge-${level}` + (big ? " badge-lg" : "")}>{level}</span>
);

export function SourceBadge({ source, weatherLive, liveEnabled, liveZones }) {
  const live = source === "tomtom+ml";
  const text = live
    ? (liveZones ? `TomTom live · ${liveZones} zones measured` : "Live traffic · TomTom")
    : liveEnabled ? "ML-estimated · TomTom on demand" : "ML-estimated · live weather";
  return (
    <span className={"tag " + (live ? "tag-live" : "tag-ml")}>
      <i className="dot" style={{ background: "currentColor" }} />
      {text}
      {weatherLive === false && " · weather offline"}
    </span>
  );
}

export function Metric({ label, value, note, color }) {
  return (
    <div className="metric">
      <p className="metric-label">{label}</p>
      <p className="metric-value" style={color ? { color } : undefined}>{value ?? "–"}</p>
      {note && <p className="metric-note">{note}</p>}
    </div>
  );
}

export function ScoreBar({ score, level }) {
  return (
    <div className="scorebar">
      <span style={{ width: `${Math.max(2, Math.min(100, score))}%`, background: LEVEL_COLORS[level] }} />
    </div>
  );
}

export function RushStatus({ rush }) {
  if (!rush || rush.state === "none") return <span className="muted">No distinct rush</span>;
  if (rush.state === "in_rush") return <span className="rush-now">In rush hour until {rush.until}</span>;
  return <span>Next rush {rush.label} <span className="muted">(in {fmtMin(rush.minutes)})</span></span>;
}

export function Panel({ title, subtitle, right, children, className = "", pad = true }) {
  return (
    <section className={"panel " + className}>
      {(title || right) && (
        <div className="panel-header">
          <div><h3>{title}</h3>{subtitle && <p>{subtitle}</p>}</div>
          {right && <div className="controls">{right}</div>}
        </div>
      )}
      <div className={pad ? "panel-body" : ""}>{children}</div>
    </section>
  );
}

export const ErrorBox = ({ message, onRetry }) => (
  <div className="error-box" role="alert">
    <span><b>Something went wrong.</b> {message}</span>
    {onRetry && <button className="btn btn-secondary btn-sm" onClick={onRetry}>Retry</button>}
  </div>
);

export const Skeleton = ({ h = 120 }) => <div className="skeleton" style={{ height: h }} />;

export const CityLink = ({ city, children }) => (
  <Link className="link" to={"/city/" + encodeURIComponent(city)}>{children ?? city}</Link>
);
