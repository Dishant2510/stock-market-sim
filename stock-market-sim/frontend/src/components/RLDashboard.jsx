/**
 * RLDashboard.jsx
 * ─────────────────────────────────────────────────────────────────────────────
 * Live panel showing the RL Market Maker's state across all tickers.
 *
 * Shows:
 *   - Agent mode badge (RL AGENT vs PASSIVE)
 *   - Aggregate stats: total P&L, avg spread, max inventory exposure
 *   - Per-ticker table: inventory, P&L, spread, imbalance — sortable
 *   - Auto-refreshes every 5s via REST /rl/status
 *
 * Add to App.jsx:
 *   import RLDashboard from "./components/RLDashboard";
 *   // In TABS: { id: "rl", label: "RL AGENT" }
 *   // In render: {tab === "rl" && <RLDashboard onSelectTicker={...} />}
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { useState, useEffect, useCallback, useRef } from "react";

const API = "http://localhost:8000";
const REFRESH_MS = 5000;

const mono = { fontFamily: "var(--mono, monospace)" };

function Badge({ active }) {
  return (
    <span style={{
      ...mono,
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: 1.5,
      padding: "3px 10px",
      borderRadius: 3,
      background: active ? "rgba(63,185,80,0.15)" : "rgba(139,148,158,0.15)",
      color:      active ? "var(--green, #3fb950)"  : "var(--text2, #8b949e)",
      border:     `1px solid ${active ? "var(--green, #3fb950)" : "var(--border, #30363d)"}`,
    }}>
      {active ? "⬡ RL AGENT" : "◈ PASSIVE"}
    </span>
  );
}

function StatCard({ label, value, color }) {
  return (
    <div style={{
      background: "var(--bg2, #161b22)",
      border: "1px solid var(--border, #30363d)",
      borderRadius: 6,
      padding: "12px 18px",
      minWidth: 140,
    }}>
      <div style={{ ...mono, fontSize: 9, color: "var(--text2, #8b949e)", letterSpacing: 1, marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ ...mono, fontSize: 18, fontWeight: 700, color: color || "var(--text, #e6edf3)" }}>
        {value}
      </div>
    </div>
  );
}

const SORT_FIELDS = [
  { key: "ticker",       label: "TICKER" },
  { key: "mm_inventory", label: "INVENTORY" },
  { key: "mm_pnl",       label: "P&L" },
  { key: "spread_bps",   label: "SPREAD" },
  { key: "mm_imbalance", label: "IMBALANCE" },
  { key: "price",        label: "PRICE" },
];

export default function RLDashboard({ onSelectTicker }) {
  const [status, setStatus]     = useState(null);
  const [error, setError]       = useState(null);
  const [loading, setLoading]   = useState(true);
  const [sortKey, setSortKey]   = useState("mm_inventory");
  const [sortDir, setSortDir]   = useState(-1);       // -1 = desc, 1 = asc
  const [filter, setFilter]     = useState("");
  const [lastUpdate, setLastUpdate] = useState(null);
  const intervalRef = useRef(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API}/rl/status`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setStatus(data);
      setError(null);
      setLastUpdate(new Date());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    intervalRef.current = setInterval(fetchStatus, REFRESH_MS);
    return () => clearInterval(intervalRef.current);
  }, [fetchStatus]);

  function toggleSort(key) {
    if (sortKey === key) {
      setSortDir(d => d * -1);
    } else {
      setSortKey(key);
      setSortDir(key === "ticker" ? 1 : -1);
    }
  }

  const tickers = (status?.tickers || [])
    .filter(t => !filter || t.ticker.includes(filter.toUpperCase()))
    .sort((a, b) => {
      const va = sortKey === "mm_inventory" ? Math.abs(a[sortKey]) : a[sortKey];
      const vb = sortKey === "mm_inventory" ? Math.abs(b[sortKey]) : b[sortKey];
      if (va < vb) return sortDir;
      if (va > vb) return -sortDir;
      return 0;
    });

  const pnlColor = (v) => v > 0 ? "var(--green, #3fb950)" : v < 0 ? "var(--red, #f85149)" : "var(--text2)";
  const invColor = (v) => Math.abs(v) > 300 ? "var(--red, #f85149)"
                        : Math.abs(v) > 150  ? "#f0a500"
                        : "var(--text, #e6edf3)";

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--text2)" }}>
      <span style={mono}>Loading RL status...</span>
    </div>
  );

  if (error) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", flexDirection: "column", gap: 10 }}>
      <span style={{ ...mono, color: "var(--red, #f85149)" }}>Error: {error}</span>
      <button onClick={fetchStatus} style={{ ...mono, padding: "6px 14px", background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 4, color: "var(--text2)", cursor: "pointer", fontSize: 11 }}>
        Retry
      </button>
    </div>
  );

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>

      {/* Header */}
      <div style={{
        padding: "14px 20px",
        borderBottom: "1px solid var(--border, #30363d)",
        display: "flex",
        alignItems: "center",
        gap: 16,
        flexShrink: 0,
        background: "var(--bg, #0d1117)",
      }}>
        <div style={{ ...mono, fontSize: 11, fontWeight: 700, letterSpacing: 2, color: "var(--text)" }}>
          RL MARKET MAKER
        </div>
        <Badge active={status?.active} />
        <div style={{ marginLeft: "auto", ...mono, fontSize: 9, color: "var(--text2)" }}>
          {lastUpdate ? `Updated ${lastUpdate.toLocaleTimeString()}` : ""} · {status?.ws_clients ?? 0} WS clients
        </div>
      </div>

      {/* Stat cards */}
      <div style={{
        display: "flex",
        gap: 12,
        padding: "14px 20px",
        borderBottom: "1px solid var(--border)",
        flexShrink: 0,
        flexWrap: "wrap",
      }}>
        <StatCard
          label="TOTAL MM P&L"
          value={`${status?.total_mm_pnl >= 0 ? "+" : ""}$${(status?.total_mm_pnl ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          color={pnlColor(status?.total_mm_pnl)}
        />
        <StatCard
          label="AVG SPREAD"
          value={`${status?.avg_spread_bps ?? 0} bps`}
          color="var(--accent, #58a6ff)"
        />
        <StatCard
          label="MAX INVENTORY"
          value={`${status?.max_inventory ?? 0} sh`}
          color={invColor(status?.max_inventory ?? 0)}
        />
        <StatCard
          label="TICKERS LIVE"
          value={(status?.tickers?.length ?? 0).toString()}
          color="var(--text)"
        />
      </div>

      {/* Info banner when passive */}
      {!status?.active && (
        <div style={{
          margin: "0 20px",
          marginTop: 14,
          padding: "10px 16px",
          background: "rgba(88,166,255,0.08)",
          border: "1px solid rgba(88,166,255,0.3)",
          borderRadius: 6,
          flexShrink: 0,
        }}>
          <div style={{ ...mono, fontSize: 11, color: "var(--accent, #58a6ff)", marginBottom: 4 }}>
            PASSIVE MODE — No trained model found
          </div>
          <div style={{ ...mono, fontSize: 10, color: "var(--text2)", lineHeight: 1.6 }}>
            Train the RL agent in <strong style={{ color: "var(--text)" }}>notebooks/04_rl_market_maker.ipynb</strong>,
            save to <strong style={{ color: "var(--text)" }}>backend/models/rl_mm_policy.pt</strong>,
            then restart the server. The policy will auto-load and replace passive spreads.
          </div>
        </div>
      )}

      {/* Filter + table */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", padding: "14px 20px 0" }}>

        {/* Filter input */}
        <input
          placeholder="Filter ticker..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
          style={{
            ...mono,
            width: 160,
            padding: "5px 10px",
            fontSize: 11,
            background: "var(--bg2)",
            border: "1px solid var(--border)",
            borderRadius: 4,
            color: "var(--text)",
            outline: "none",
            marginBottom: 10,
            flexShrink: 0,
          }}
        />

        {/* Table */}
        <div style={{ flex: 1, overflowY: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", ...mono, fontSize: 11 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", position: "sticky", top: 0, background: "var(--bg, #0d1117)", zIndex: 1 }}>
                {SORT_FIELDS.map(f => (
                  <th
                    key={f.key}
                    onClick={() => toggleSort(f.key)}
                    style={{
                      padding: "6px 10px",
                      textAlign: f.key === "ticker" ? "left" : "right",
                      color: sortKey === f.key ? "var(--accent, #58a6ff)" : "var(--text2)",
                      fontSize: 9,
                      letterSpacing: 1,
                      cursor: "pointer",
                      userSelect: "none",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {f.label} {sortKey === f.key ? (sortDir === -1 ? "↓" : "↑") : ""}
                  </th>
                ))}
                <th style={{ padding: "6px 10px", textAlign: "center", color: "var(--text2)", fontSize: 9, letterSpacing: 1 }}>
                  TIER
                </th>
                <th style={{ padding: "6px 10px", textAlign: "center", color: "var(--text2)", fontSize: 9, letterSpacing: 1 }}>
                  INV BAR
                </th>
              </tr>
            </thead>
            <tbody>
              {tickers.map((t, i) => {
                const invPct = Math.min(Math.abs(t.mm_inventory) / 500 * 100, 100);
                const invBar = t.mm_inventory > 0 ? "▶" : t.mm_inventory < 0 ? "◀" : "·";

                return (
                  <tr
                    key={t.ticker}
                    onClick={() => onSelectTicker?.(t.ticker)}
                    style={{
                      borderBottom: "1px solid var(--border)",
                      cursor: "pointer",
                      background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)",
                      transition: "background 0.1s",
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = "rgba(88,166,255,0.06)"}
                    onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)"}
                  >
                    <td style={{ padding: "5px 10px", color: "var(--accent, #58a6ff)", fontWeight: 700, letterSpacing: 0.5 }}>
                      {t.ticker}
                    </td>
                    <td style={{ padding: "5px 10px", textAlign: "right", color: invColor(t.mm_inventory) }}>
                      {t.mm_inventory > 0 ? "+" : ""}{t.mm_inventory}
                    </td>
                    <td style={{ padding: "5px 10px", textAlign: "right", color: pnlColor(t.mm_pnl) }}>
                      {t.mm_pnl >= 0 ? "+" : ""}${t.mm_pnl.toFixed(2)}
                    </td>
                    <td style={{ padding: "5px 10px", textAlign: "right", color: t.spread_bps > 100 ? "#f0a500" : "var(--text)" }}>
                      {t.spread_bps} bps
                    </td>
                    <td style={{ padding: "5px 10px", textAlign: "right", color: Math.abs(t.mm_imbalance) > 5 ? "#f0a500" : "var(--text2)" }}>
                      {t.mm_imbalance > 0 ? "+" : ""}{t.mm_imbalance.toFixed(2)}
                    </td>
                    <td style={{ padding: "5px 10px", textAlign: "right", color: "var(--text2)" }}>
                      ${t.price.toFixed(2)}
                    </td>
                    <td style={{ padding: "5px 10px", textAlign: "center" }}>
                      <span style={{
                        fontSize: 9,
                        padding: "2px 6px",
                        borderRadius: 3,
                        background: t.cap_tier === "large" ? "rgba(63,185,80,0.12)"
                                  : t.cap_tier === "mid"   ? "rgba(88,166,255,0.12)"
                                  : "rgba(240,165,0,0.12)",
                        color: t.cap_tier === "large" ? "var(--green)" : t.cap_tier === "mid" ? "var(--accent)" : "#f0a500",
                      }}>
                        {t.cap_tier.toUpperCase()}
                      </span>
                    </td>
                    <td style={{ padding: "5px 10px", minWidth: 80 }}>
                      <div style={{ position: "relative", height: 6, background: "var(--bg3, #21262d)", borderRadius: 3, overflow: "hidden" }}>
                        <div style={{
                          position: "absolute",
                          height: "100%",
                          width: `${invPct}%`,
                          left: t.mm_inventory >= 0 ? "50%" : `${50 - invPct/2}%`,
                          background: t.mm_inventory > 0 ? "var(--green, #3fb950)" : "var(--red, #f85149)",
                          borderRadius: 3,
                          transition: "width 0.3s ease",
                          transform: t.mm_inventory > 0 ? "none" : `translateX(-${invPct}%)`,
                        }} />
                        <div style={{ position: "absolute", left: "50%", top: 0, height: "100%", width: 1, background: "var(--border2, #484f58)" }} />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {tickers.length === 0 && (
            <div style={{ textAlign: "center", padding: "40px 0", color: "var(--text2)", ...mono, fontSize: 11 }}>
              No tickers match "{filter}"
            </div>
          )}
        </div>
      </div>

    </div>
  );
}
