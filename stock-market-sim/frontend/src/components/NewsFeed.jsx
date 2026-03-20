const IMPACT_COLOR = { bullish: "var(--green)", bearish: "var(--red)", neutral: "var(--text2)" };
const IMPACT_BG    = { bullish: "var(--green-bg)", bearish: "var(--red-bg)", neutral: "var(--bg3)" };
const IMPACT_BORDER= { bullish: "#3fb95033", bearish: "#f8514933", neutral: "var(--border)" };

export default function NewsFeed({ news, onSelectTicker }) {
  return (
    <div style={{ height: "100%", overflowY: "auto", padding: "16px" }}>
      <div className="label" style={{ marginBottom: 14 }}>AI NEWS FEED</div>

      {(!news || news.length === 0) && (
        <div style={{ color: "var(--text2)", fontSize: 13, padding: "20px 0" }}>
          <span style={{ animation: "pulse 2s infinite", display: "inline-block", marginRight: 8 }}>⏳</span>
          Waiting for first news event...
        </div>
      )}

      {(news || []).map((item, i) => (
        <div
          key={item.id || i}
          onClick={() => item.ticker && onSelectTicker?.(item.ticker)}
          style={{
            background: IMPACT_BG[item.impact] || "var(--bg2)",
            border: `1px solid ${IMPACT_BORDER[item.impact] || "var(--border)"}`,
            borderRadius: 7, padding: "11px 14px", marginBottom: 8,
            cursor: item.ticker ? "pointer" : "default",
            animation: i === 0 ? "fadeIn 0.4s ease" : "none",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span style={{
                fontFamily: "var(--mono)", fontSize: 10, letterSpacing: 1,
                color: IMPACT_COLOR[item.impact] || "var(--text2)",
              }}>
                {(item.impact || "").toUpperCase()}
              </span>
              {item.ticker && (
                <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--accent)", background: "var(--bg3)", padding: "1px 6px", borderRadius: 3 }}>
                  {item.ticker}
                </span>
              )}
              {item.sentiment_delta !== undefined && (
                <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: item.sentiment_delta >= 0 ? "var(--green)" : "var(--red)" }}>
                  {item.sentiment_delta >= 0 ? "+" : ""}{(item.sentiment_delta * 100).toFixed(0)}%
                </span>
              )}
            </div>
            <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--text3)" }}>
              {item.generated_at?.slice(11, 16) || ""}
            </span>
          </div>
          <div style={{ fontSize: 13, color: "var(--text)", lineHeight: 1.5 }}>{item.headline}</div>
        </div>
      ))}
    </div>
  );
}