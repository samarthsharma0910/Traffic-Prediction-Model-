export const LEVELS = ["Low", "Moderate", "Heavy", "Severe"];
// Solid colours for map markers, bars and gauges (badges use the pastel .badge-* classes).
export const LEVEL_COLORS = { Low: "#12a150", Moderate: "#f0a500", Heavy: "#ea6a0a", Severe: "#d92d20" };
export const THRESHOLDS = [30, 55, 75];

export const hh = h => String(h).padStart(2, "0") + ":00";
export const cityUrl = c => "/city/" + encodeURIComponent(c);

export function fmtMin(m) {
  const h = Math.floor(m / 60), r = m % 60;
  return h ? `${h}h ${r}m` : `${r}m`;
}

export function levelFor(score) {
  return score < THRESHOLDS[0] ? "Low" : score < THRESHOLDS[1] ? "Moderate" : score < THRESHOLDS[2] ? "Heavy" : "Severe";
}

export function heatColor(score) {
  return `hsl(${Math.max(0, 135 - 1.35 * score)}, 58%, 62%)`;
}
