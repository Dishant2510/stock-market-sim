const fmt2 = n => n?.toFixed(2) ?? "0.00";
const fmtPct = n => (n >= 0 ? "+" : "") + (n * 100).toFixed(2) + "%";

export default function TickerTape({ prices }) {
  const tickers = Object.keys(prices).slice(0, 30); // show first 30 in tape
  const items   = tickers.map(t => {
    const s   = prices[t];
    const h   = s.history || [];
    const chg = h.length >= 2 ? (s.price - h[0]) / h[0] : 0;
    return `${t}  $${fmt2(s.price)}  ${fmtPct(chg)}`;
  }).join("   ·   ");

  return (
    <div style={{ overflow: "hidden", background: "#010409", borderBottom: "1px solid var(--border)", height: 30, display: "flex", alignItems: "center" }}>
      <div style={{ whiteSpace: "nowrap", animation: "tape 60s linear infinite", display: "flex", alignItems: "center" }}>
        {[items, items].map((block, i) => (
          <span key={i} style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text2)", letterSpacing: 1, padding: "0 40px" }}>
            {block.split("·").map((seg, j) => {
              const parts = seg.trim().split("  ");
              const pct   = parts[2] || "";
              const up    = pct.startsWith("+");
              return (
                <span key={j} style={{ marginRight: 40 }}>
                  <span style={{ color: "var(--accent)" }}>{parts[0]}</span>
                  <span style={{ color: "var(--text)", margin: "0 6px" }}>${parts[1]?.replace("$","")}</span>
                  <span style={{ color: up ? "var(--green)" : "var(--red)" }}>{pct}</span>
                </span>
              );
            })}
          </span>
        ))}
      </div>
    </div>
  );
}