import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "./api/client";
import Login from "./components/Login";
import TickerTape from "./components/TickerTape";
import StockGrid from "./components/StockGrid";
import TradePanel from "./components/TradePanel";
import Portfolio from "./components/Portfolio";
import NewsFeed from "./components/NewsFeed";
import Leaderboard from "./components/Leaderboard";

const POLL_MS = 2500;

const TABS = [
  { id: "market",      label: "MARKET" },
  { id: "portfolio",   label: "PORTFOLIO" },
  { id: "leaderboard", label: "LEADERBOARD" },
];

export default function App() {
  const [user, setUser]               = useState(() => {
    try { return JSON.parse(localStorage.getItem("sim_user")); } catch { return null; }
  });
  const [prices, setPrices]           = useState({});
  const [selected, setSelected]       = useState("AAPL");
  const [portfolio, setPortfolio]     = useState(null);
  const [news, setNews]               = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [tab, setTab]                 = useState("market");
  const [tick, setTick]               = useState(0);
  const [connected, setConnected]     = useState(false);
  const pollRef                       = useRef(null);

  // ── Fetch prices ───────────────────────────────────────────────────────────
  const fetchPrices = useCallback(async () => {
    try {
      const data = await api.getAllPrices();
      setPrices(data);
      setTick(t => t + 1);
      setConnected(true);
    } catch { setConnected(false); }
  }, []);

  // ── Fetch portfolio ────────────────────────────────────────────────────────
  const fetchPortfolio = useCallback(async () => {
    if (!user) return;
    try {
      const data = await api.getPortfolio(user.id);
      setPortfolio(data);
      // Keep user.cash in sync
      setUser(u => ({ ...u, cash: data.cash }));
    } catch {}
  }, [user]);

  // ── Fetch news ─────────────────────────────────────────────────────────────
  const fetchNews = useCallback(async () => {
    try { setNews((await api.getNews(30)).news); } catch {}
  }, []);

  // ── Fetch leaderboard ──────────────────────────────────────────────────────
  const fetchLeaderboard = useCallback(async () => {
    try { setLeaderboard((await api.getLeaderboard(20)).leaderboard); } catch {}
  }, []);

  // ── Start polling ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!user) return;
    fetchPrices();
    fetchPortfolio();
    fetchNews();
    fetchLeaderboard();

    pollRef.current = setInterval(() => {
      fetchPrices();
      if (tick % 5 === 0)  fetchPortfolio();
      if (tick % 8 === 0)  fetchNews();
      if (tick % 15 === 0) fetchLeaderboard();
    }, POLL_MS);

    return () => clearInterval(pollRef.current);
  }, [user]);  // eslint-disable-line

  // ── Trade success ──────────────────────────────────────────────────────────
  const onTradeSuccess = useCallback(() => {
    fetchPortfolio();
    fetchPrices();
  }, [fetchPortfolio, fetchPrices]);

  // ── Logout ─────────────────────────────────────────────────────────────────
  function logout() {
    localStorage.removeItem("sim_user");
    setUser(null);
    setPrices({});
    setPortfolio(null);
  }

  // ── Not logged in ──────────────────────────────────────────────────────────
  if (!user) return <Login onLogin={u => setUser(u)} />;

  const selectedPrice = prices[selected];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden" }}>

      {/* Top nav */}
      <div style={{ display: "flex", alignItems: "center", padding: "0 20px", height: 46, background: "var(--bg2)", borderBottom: "1px solid var(--border)", flexShrink: 0, gap: 24 }}>
        <div style={{ fontFamily: "var(--mono)", fontSize: 14, fontWeight: 700, color: "var(--text)", letterSpacing: 2 }}>MARKETSIM</div>

        {/* Status */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: connected ? "var(--green)" : "var(--red)", display: "inline-block", animation: connected ? "pulse 2s infinite" : "none" }} />
          <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: connected ? "var(--green)" : "var(--red)" }}>
            {connected ? `LIVE · TICK ${tick}` : "DISCONNECTED"}
          </span>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 2, marginLeft: 8 }}>
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              padding: "6px 14px", borderRadius: 4, fontSize: 11, letterSpacing: 1, fontFamily: "var(--mono)",
              background: tab === t.id ? "var(--bg3)" : "transparent",
              color: tab === t.id ? "var(--text)" : "var(--text2)",
              border: `1px solid ${tab === t.id ? "var(--border2)" : "transparent"}`,
            }}>{t.label}</button>
          ))}
        </div>

        {/* User info */}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text2)" }}>{user.username}</div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--accent)" }}>
              ${(portfolio?.cash ?? user?.cash ?? 100000).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>
          <button onClick={logout} style={{ padding: "5px 10px", background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 4, color: "var(--text2)", fontSize: 10, letterSpacing: 1 }}>
            EXIT
          </button>
        </div>
      </div>

      {/* Ticker tape */}
      {Object.keys(prices).length > 0 && <TickerTape prices={prices} />}

      {/* MARKET TAB */}
      {tab === "market" && (
        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "320px 1fr 300px", overflow: "hidden", minHeight: 0 }}>

          {/* Left: stock grid */}
          <div style={{ borderRight: "1px solid var(--border)", overflow: "hidden", display: "flex", flexDirection: "column" }}>
            <StockGrid prices={prices} selected={selected} onSelect={setSelected} />
          </div>

          {/* Center: trade panel */}
          <div style={{ borderRight: "1px solid var(--border)", overflow: "hidden", display: "flex", flexDirection: "column" }}>
            {selectedPrice ? (
              <TradePanel
                ticker={selected}
                priceData={selectedPrice}
                user={{ ...user, cash: portfolio?.cash ?? user?.cash ?? 100000 }}
                portfolio={portfolio}
                onTradeSuccess={onTradeSuccess}
              />
            ) : (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--text2)" }}>
                Select a ticker to trade
              </div>
            )}
          </div>

          {/* Right: news feed */}
          <div style={{ overflow: "hidden" }}>
            <NewsFeed news={news} onSelectTicker={t => { setSelected(t); }} />
          </div>
        </div>
      )}

      {/* PORTFOLIO TAB */}
      {tab === "portfolio" && (
        <div style={{ flex: 1, overflow: "hidden" }}>
          <Portfolio portfolio={portfolio} onSelectTicker={t => { setSelected(t); setTab("market"); }} />
        </div>
      )}

      {/* LEADERBOARD TAB */}
      {tab === "leaderboard" && (
        <div style={{ flex: 1, overflow: "hidden" }}>
          <Leaderboard leaderboard={leaderboard} currentUserId={user?.id} />
        </div>
      )}
    </div>
  );
}