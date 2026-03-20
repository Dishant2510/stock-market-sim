const fmtD = n => (n < 0 ? "-$" : "$") + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const MEDALS = ["🥇", "🥈", "🥉"];

export default function Leaderboard({ leaderboard, currentUserId }) {
  const rows = leaderboard || [];

  return (
    <div style={{ height: "100%", overflowY: "auto", padding: "24px 28px" }}>
      <div className="label" style={{ marginBottom: 20 }}>LEADERBOARD</div>

      <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {["RANK", "TRADER", "PORTFOLIO VALUE", "CASH", "HOLDINGS", "P&L"].map(h => (
                <th key={h} style={{ padding: "12px 20px", textAlign: h === "TRADER" || h === "RANK" ? "left" : "right", borderBottom: "1px solid var(--border)", fontFamily: "var(--mono)", fontSize: 10, color: "var(--text2)", letterSpacing: 1, fontWeight: 400 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const isMe = row.user_id === currentUserId;
              return (
                <tr key={row.user_id}
                  style={{
                    borderBottom: "1px solid var(--border)",
                    background: isMe ? "#58a6ff08" : "transparent",
                  }}
                >
                  <td style={{ padding: "14px 20px", fontFamily: "var(--mono)", fontSize: 14, color: i < 3 ? "var(--yellow)" : "var(--text2)", textAlign: "left" }}>
                    {MEDALS[i] || `#${i + 1}`}
                  </td>
                  <td style={{ padding: "14px 20px", textAlign: "left" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontWeight: 600, color: isMe ? "var(--accent)" : "var(--text)", fontSize: 14 }}>{row.username}</span>
                      {isMe && <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--accent)", background: "#58a6ff15", padding: "1px 6px", borderRadius: 3, letterSpacing: 1 }}>YOU</span>}
                    </div>
                  </td>
                  <td style={{ padding: "14px 20px", fontFamily: "var(--mono)", fontWeight: 600, fontSize: 14, color: "var(--text)", textAlign: "right" }}>
                    {fmtD(row.total_value)}
                  </td>
                  <td style={{ padding: "14px 20px", fontFamily: "var(--mono)", fontSize: 13, color: "var(--text2)", textAlign: "right" }}>
                    {fmtD(row.cash)}
                  </td>
                  <td style={{ padding: "14px 20px", fontFamily: "var(--mono)", fontSize: 13, color: "var(--text2)", textAlign: "right" }}>
                    {fmtD(row.holdings_value)}
                  </td>
                  <td style={{ padding: "14px 20px", fontFamily: "var(--mono)", fontSize: 13, textAlign: "right", color: row.pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                    {row.pnl >= 0 ? "+" : ""}{fmtD(row.pnl)}
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} style={{ padding: "40px 20px", textAlign: "center", color: "var(--text2)", fontSize: 14 }}>
                  No traders yet. You could be #1! 🏆
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}