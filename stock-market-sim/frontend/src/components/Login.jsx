import { useState } from "react";
import { api } from "../api/client";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);

  async function handleSubmit() {
    const name = username.trim();
    const pass = password.trim();
    if (name.length < 2)  { setError("Username must be at least 2 characters."); return; }
    if (pass.length < 4)  { setError("Password must be at least 4 characters."); return; }

    setLoading(true); setError("");
    try {
      // Try login first — if user exists, password must match
      let user;
      try {
        user = await api.login(name, pass);
      } catch (loginErr) {
        if (loginErr.message === "User not found") {
          // New user — register
          const res = await api.register(name, pass);
          user = res.user;
        } else {
          throw loginErr;  // Wrong password or other error
        }
      }
      localStorage.setItem("sim_user", JSON.stringify({ id: user.id, username: user.username }));
      onLogin(user);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center",
      justifyContent: "center", background: "var(--bg)", padding: 24 }}>

      {/* Ambient glow */}
      <div style={{ position: "fixed", top: "20%", left: "50%", transform: "translateX(-50%)",
        width: 600, height: 400,
        background: "radial-gradient(ellipse, #58a6ff08 0%, transparent 70%)",
        pointerEvents: "none" }} />

      <div style={{ width: "100%", maxWidth: 440 }}>
        {/* Logo */}
        <div style={{ marginBottom: 48, textAlign: "center" }}>
          <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text3)",
            letterSpacing: 4, marginBottom: 12 }}>VIRTUAL TRADING TERMINAL</div>
          <div style={{ fontSize: 42, fontWeight: 700, letterSpacing: -2, color: "var(--text)" }}>
            MARKETSIM
          </div>
          <div style={{ marginTop: 8, display: "flex", alignItems: "center",
            justifyContent: "center", gap: 8 }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--green)",
              display: "inline-block", animation: "pulse 2s infinite" }} />
            <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--green)" }}>
              MARKETS OPEN · 100 TICKERS LIVE
            </span>
          </div>
        </div>

        {/* Card */}
        <div style={{ background: "var(--bg2)", border: "1px solid var(--border)",
          borderRadius: 12, padding: "32px 36px" }}>
          <div className="label" style={{ marginBottom: 20 }}>Enter Trading Terminal</div>

          {/* Username */}
          <div style={{ marginBottom: 14 }}>
            <div className="label" style={{ marginBottom: 8 }}>Username</div>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSubmit()}
              placeholder="e.g. buffett42"
              maxLength={30}
              autoComplete="username"
              style={{ width: "100%", background: "var(--bg3)", border: "1px solid var(--border2)",
                borderRadius: 6, color: "var(--text)", fontSize: 15, padding: "12px 14px",
                boxSizing: "border-box" }}
            />
          </div>

          {/* Password */}
          <div style={{ marginBottom: 20 }}>
            <div className="label" style={{ marginBottom: 8 }}>Password</div>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSubmit()}
              placeholder="Min 4 characters"
              maxLength={100}
              autoComplete="current-password"
              style={{ width: "100%", background: "var(--bg3)", border: "1px solid var(--border2)",
                borderRadius: 6, color: "var(--text)", fontSize: 15, padding: "12px 14px",
                boxSizing: "border-box" }}
            />
          </div>

          {/* Error */}
          {error && (
            <div style={{ background: "var(--red-bg)", border: "1px solid #f8514933",
              borderRadius: 6, padding: "10px 14px", marginBottom: 16,
              fontSize: 13, color: "var(--red)" }}>
              {error}
            </div>
          )}

          <button
            onClick={handleSubmit}
            disabled={loading || !username.trim() || !password.trim()}
            style={{ width: "100%", padding: "13px 0", borderRadius: 6, fontSize: 13,
              fontWeight: 600, letterSpacing: 2, cursor: "pointer",
              background: loading ? "var(--border2)" : "var(--accent)",
              color: loading ? "var(--text2)" : "#000", transition: "all 0.15s",
              border: "none" }}
          >
            {loading ? "CONNECTING..." : "ENTER MARKET →"}
          </button>

          <div style={{ marginTop: 20, padding: "14px 16px", background: "var(--bg3)",
            borderRadius: 6, fontSize: 12, color: "var(--text2)", lineHeight: 1.7 }}>
            <span style={{ color: "var(--accent)" }}>New username</span> → creates account with $100,000.<br />
            <span style={{ color: "var(--accent)" }}>Existing username</span> → logs in (password required).
          </div>
        </div>

        <div style={{ textAlign: "center", marginTop: 24, fontFamily: "var(--mono)",
          fontSize: 11, color: "var(--text3)" }}>
          AI-DRIVEN · GARCH VOLATILITY · REAL MARKET DATA
        </div>
      </div>
    </div>
  );
}