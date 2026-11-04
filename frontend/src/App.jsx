import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import Live from "./pages/Live.jsx";
import City from "./pages/City.jsx";
import Predict from "./pages/Predict.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import NotFound from "./pages/NotFound.jsx";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Live />} />
        <Route path="/city/:city" element={<City />} />
        <Route path="/predict" element={<Predict />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Layout>
  );
}
