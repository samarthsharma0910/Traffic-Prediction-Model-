import { Link } from "react-router-dom";
import { useTitle } from "../api.js";

export default function NotFound() {
  useTitle("Saarthi — Page not found");
  return (
    <main className="container center-page">
      <h1 className="huge">404</h1>
      <p className="muted">That page doesn't exist.</p>
      <Link className="btn btn-primary" to="/">Back to live map</Link>
    </main>
  );
}
