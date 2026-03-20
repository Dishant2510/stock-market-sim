import { useState, useMemo } from "react";
import { LineChart, Line, ResponsiveContainer, YAxis } from "recharts";

const fmt2 = n => (n ?? 0).toFixed(2);

function MiniChart({ history, up }) {
  const data = (history || []).slice(-30).map((p, i) => ({ i, p }));
  return (
    <ResponsiveContainer width="100%" height={36}>
      <LineChart data={data}>
        <Line type="monotone" dataKey="p" stroke={up ? "#3fb950" : "#f85149"} strokeWidth={1.2} dot={false} />
        <YAxis domain={["auto","auto"]} hide />
      </LineChart>
    </ResponsiveContainer>
  );
}

const TIERS = ["all", "large", "mid", "small"];
const TIER_LABELS = { large: "LARGE CAP", mid: "MID CAP", small: "SMALL CAP" };

export default function StockGrid({ prices, selected, onSelect }) {
  const [search, setSearch] = useState("");
  const [tier, setTier]     = useState("all");

  const tickers = useMemo(() => {
    return Object.entries(prices)
      .filter(([t, s]) => {
        if (tier !== "all" && s.cap_tier !== tier) return false;
        if (search && !t.toLowerCase().includes(search.toLowerCase())) return false;
        return true;
      })
      .sort((a, b) => a[0].localeCompare(b[0]));
  }, [prices, tier, search]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Filters */}
      <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
        <input
          type="text" placeholder="Search ticker..." value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ flex: 1, background: "var(--bg3)", border: "1px solid var(--border2)", borderRadius: 4, color: "var(--text)", fontSize: 12, padding: "6px 10px" }}
        />
        <div style={{ display: "flex", gap: 4, background: "var(--bg3)", borderRadius: 6, padding: 3 }}>
          {TIERS.map(t => {
            const COLORS = { large: "#58a6ff", mid: "#f0e68c", small: "#f85149", all: "var(--text)" };
            const active = tier === t;
            return (
              <button key={t} onClick={() => setTier(t)} style={{
                padding: "5px 12px", borderRadius: 4, fontSize: 10, letterSpacing: 1.5, fontFamily: "var(--mono)",
                background: active ? "var(--bg2)" : "transparent",
                color: active ? COLORS[t] : "var(--text3)",
                border: active ? `1px solid ${COLORS[t]}44` : "1px solid transparent",
                transition: "all 0.15s",
              }}>
                {t === "all" ? "ALL" : t === "large" ? "LARGE" : t === "mid" ? "MID" : "SMALL"}
              </button>
            );
          })}
        </div>
      </div>

      {/* Count */}
      <div style={{ padding: "6px 16px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <span className="label">{tickers.length} TICKERS</span>
      </div>

      {/* Grid */}
      <div style={{ flex: 1, overflowY: "auto", padding: 12 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 8 }}>
          {tickers.map(([ticker, s]) => {
            const h    = s.history || [];
            const chg  = h.length >= 2 ? (s.price - h[0]) / h[0] : 0;
            const up   = chg >= 0;
            const isSel = ticker === selected;
            return (
              <div
                key={ticker}
                onClick={() => onSelect(ticker)}
                style={{
                  background: isSel ? (up ? "var(--green-bg)" : "var(--red-bg)") : "var(--bg2)",
                  border: `1px solid ${isSel ? (up ? "#3fb95055" : "#f8514955") : "var(--border)"}`,
                  borderRadius: 8, padding: "10px 12px", cursor: "pointer",
                  transition: "all 0.12s",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 4 }}>
                  <div>
                    <div style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600, color: "var(--text)" }}>{ticker}</div>
                    <div style={{ fontSize: 9, color: "var(--text3)", letterSpacing: 1, marginTop: 1 }}>
                      {TIER_LABELS[s.cap_tier] || s.cap_tier?.toUpperCase()}
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontFamily: "var(--mono)", fontSize: 13, color: "var(--text)" }}>${fmt2(s.price)}</div>
                    <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: up ? "var(--green)" : "var(--red)" }}>
                      {up ? "▲" : "▼"} {Math.abs(chg * 100).toFixed(2)}%
                    </div>
                  </div>
                </div>
                <MiniChart history={h} up={up} />
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontFamily: "var(--mono)", fontSize: 9, color: "var(--text3)" }}>
                  <span>B {fmt2(s.bid)}</span>
                  <span>A {fmt2(s.ask)}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}