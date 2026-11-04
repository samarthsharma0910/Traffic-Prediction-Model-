import { useCallback, useEffect, useRef, useState } from "react";

export async function getJSON(url, opts) {
  const r = await fetch(url, opts);
  let body = null;
  try { body = await r.json(); } catch { /* non-JSON error page */ }
  if (!r.ok) throw new Error((body && body.error) || `Request failed (${r.status})`);
  return body;
}

/** Fetch `url` (skip when null); keeps stale data while reloading; optional polling. */
export function useApi(url, { interval = 0 } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: !!url });
  const seq = useRef(0);

  const load = useCallback(async () => {
    if (!url) return;
    const mine = ++seq.current;
    setState(s => ({ ...s, loading: true }));
    try {
      const data = await getJSON(url);
      if (mine === seq.current) setState({ data, error: null, loading: false });
    } catch (e) {
      if (mine === seq.current) setState(s => ({ data: s.data, error: e.message, loading: false }));
    }
  }, [url]);

  useEffect(() => {
    setState(s => ({ ...s, error: null, loading: !!url }));
    load();
    if (!interval) return undefined;
    const t = setInterval(() => { if (!document.hidden) load(); }, interval);
    return () => clearInterval(t);
  }, [load, interval, url]);

  return { ...state, reload: load };
}

/** Browser geolocation + nearest monitored zone from the API. */
export function useUserLocation() {
  const [st, setSt] = useState({ status: "idle", pos: null, near: null, error: null });

  const locate = useCallback(() => {
    if (!navigator.geolocation) {
      setSt({ status: "error", pos: null, near: null, error: "Location is not supported by this browser." });
      return;
    }
    setSt(s => ({ ...s, status: "loading", error: null }));
    navigator.geolocation.getCurrentPosition(
      async p => {
        const pos = { lat: p.coords.latitude, lon: p.coords.longitude };
        try {
          const near = await getJSON(`/api/nearest?lat=${pos.lat}&lon=${pos.lon}`);
          setSt({ status: "ok", pos, near, error: null });
        } catch (e) {
          setSt({ status: "error", pos, near: null, error: `${e.message}.` });
        }
      },
      e => setSt({ status: "error", pos: null, near: null,
        error: e.code === 1 ? "Location permission denied - showing all India." : "Could not get your location - showing all India." }),
      { timeout: 8000, maximumAge: 300000 });
  }, []);

  return { ...st, locate };
}

/** Sets the browser tab title for the current page. */
export function useTitle(title) {
  useEffect(() => { document.title = title; }, [title]);
}
