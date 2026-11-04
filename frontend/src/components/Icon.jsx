const PATHS = {
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  locate: (
    <>
      <circle cx="12" cy="12" r="7" />
      <circle cx="12" cy="12" r="2" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
    </>
  ),
  chevron: <path d="m9 6 6 6-6 6" />,
  back: <path d="M19 12H5m6-6-6 6 6 6" />,
  arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
  chart: <path d="M4 20V10m6 10V4m6 16v-7m4 7H2" />,
  close: <path d="M6 6l12 12M18 6 6 18" />,
};

export default function Icon({ name, size = 16 }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {PATHS[name]}
    </svg>
  );
}
