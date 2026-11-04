import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import Icon from "./Icon.jsx";

export default function Layout({ children }) {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => { setOpen(false); window.scrollTo(0, 0); }, [pathname]);

  const link = ({ isActive }) => (isActive ? "active" : undefined);
  return (
    <>
      <header className="site-header">
        <div className="container header-inner">
          <NavLink to="/" className="brand">
            <div className="brand-mark">S</div>
            <div>
              <div className="brand-name">Saarthi</div>
              <span className="brand-sub">Traffic intelligence · India</span>
            </div>
          </NavLink>

          <button className="menu-btn" aria-label="Menu" aria-expanded={open} onClick={() => setOpen(o => !o)}>
            <Icon name="menu" size={20} />
          </button>
          <nav className={"nav" + (open ? " open" : "")} aria-label="Main">
            <NavLink to="/" end className={link}>Live map</NavLink>
            <NavLink to="/predict" className={link}>Predict</NavLink>
            <NavLink to="/dashboard" className={link}>Dashboard</NavLink>
          </nav>
          <NavLink to="/predict" className="header-action">Predict traffic</NavLink>
        </div>
      </header>

      {children}

      <footer>
        <div className="container footer-inner">
          <span>© {new Date().getFullYear()} Saarthi · Times in IST · Weather by Open-Meteo</span>
          <span>Status is ML-estimated unless a live provider is configured · Training history is simulated</span>
        </div>
      </footer>
    </>
  );
}
