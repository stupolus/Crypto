import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import Layout from "./Layout";
import Overview from "./pages/Overview";
import Agents from "./pages/Agents";
import Trades from "./pages/Trades";
import TradeDetail from "./pages/TradeDetail";
import News from "./pages/News";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Overview />} />
          <Route path="agents" element={<Agents />} />
          <Route path="trades" element={<Trades />} />
          <Route path="trades/:id" element={<TradeDetail />} />
          <Route path="news" element={<News />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
