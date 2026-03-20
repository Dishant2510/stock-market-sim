const fmt2 = n => (n ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtD = n => (n < 0 ? "-$" : "$") + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function Portfolio({ portfolio, onSelectTicker }) {
  if (!portfolio) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--text2)" }}>
      Loading portfolio...
    </div>
  );

  const { cash, holdings_value, total_value, total_pnl, holdings } = portfolio;

  return (
    <div style={{ height: "100%", overflowY: "auto", padding: "24px 28px" }}>
      <div className="label" style={{ marginBottom: 20 }}>PORTFOLIO SUMMARY</div>

      {/* Summary cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 24 }}>
        {[
          ["TOTAL VALUE",    fmtD(total_value),    "var(--text)"],
          ["CASH",           fmtD(cash),            "var(--accent)"],
          ["HOLDINGS",       fmtD(holdings_value),  "var(--text)"],
          ["ALL-TIME P&L",   fmtD(total_pnl),       total_pnl >= 0 ? "var(--green)" : "var(--red)"],
        ].map(([label, val, color]) => (
          <div key={label} style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 8, padding: "18px 20px" }}>
            <div className="label" style={{ marginBottom: 8 }}>{label}</div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 22, fontWeight: 600, color }}>{val}</div>
          </div>
        ))}
      </div>

      {/* P&L bar */}
      <div style={{ marginBottom: 24, background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 8, padding: "16px 20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
          <span className="label">RETURN ON $100,000</span>
          <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: total_pnl >= 0 ? "var(--green)" : "var(--red)" }}>
            {total_pnl >= 0 ? "+" : ""}{((total_pnl / 100000) * 100).toFixed(2)}%
          </span>
        </div>
        <div style={{ height: 4, background: "var(--bg3)", borderRadius: 2 }}>
          <div style={{
            height: "100%", borderRadius: 2,
            width: `${Math.min(100, Math.abs(total_pnl / 100000) * 100 * 10)}%`,
            background: total_pnl >= 0 ? "var(--green)" : "var(--red)",
            transition: "width 0.5s",
          }} />
        </div>
      </div>

      {/* Holdings table */}
      <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
        <div style={{ padding: "12px 20px", borderBottom: "1px solid var(--border)" }}>
          <span className="label">OPEN POSITIONS ({(holdings || []).length})</span>
        </div>

        {(!holdings || holdings.length === 0) ? (
          <div style={{ padding: "40px 20px", textAlign: "center", color: "var(--text2)", fontSize: 14 }}>
            No open positions. Start trading! 📈
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {["TICKER", "SHARES", "AVG COST", "CURRENT", "MKT VALUE", "P&L", "RETURN"].map(h => (
                  <th key={h} style={{ padding: "10px 16px", textAlign: "right", borderBottom: "1px solid var(--border)", fontFamily: "var(--mono)", fontSize: 10, color: "var(--text2)", letterSpacing: 1, fontWeight: 400 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {holdings.map(h => (
                <tr key={h.ticker}
                  onClick={() => onSelectTicker?.(h.ticker)}
                  style={{ borderBottom: "1px solid var(--border)", cursor: "pointer", transition: "background 0.1s" }}
                  onMouseEnter={e => e.currentTarget.style.background = "var(--bg3)"}
                  onMouseLeave={e => e.currentTarget.style.background = ""}
                >
                  <td style={{ padding: "12px 16px", fontFamily: "var(--mono)", color: "var(--accent)", fontWeight: 600, textAlign: "right" }}>{h.ticker}</td>
                  <td style={{ padding: "12px 16px", fontFamily: "var(--mono)", color: "var(--text)", textAlign: "right" }}>{h.qty?.toFixed(2)}</td>
                  <td style={{ padding: "12px 16px", fontFamily: "var(--mono)", color: "var(--text2)", textAlign: "right" }}>${fmt2(h.avg_cost)}</td>
                  <td style={{ padding: "12px 16px", fontFamily: "var(--mono)", color: "var(--text)", textAlign: "right" }}>${fmt2(h.current_price)}</td>
                  <td style={{ padding: "12px 16px", fontFamily: "var(--mono)", color: "var(--text)", textAlign: "right" }}>{fmtD(h.market_value)}</td>
                  <td style={{ padding: "12px 16px", fontFamily: "var(--mono)", color: h.pnl >= 0 ? "var(--green)" : "var(--red)", textAlign: "right" }}>{fmtD(h.pnl)}</td>
                  <td style={{ padding: "12px 16px", fontFamily: "var(--mono)", color: h.pnl_pct >= 0 ? "var(--green)" : "var(--red)", textAlign: "right" }}>
                    {h.pnl_pct >= 0 ? "+" : ""}{((h.pnl_pct || 0) * 100).toFixed(2)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}