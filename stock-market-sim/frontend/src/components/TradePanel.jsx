import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../api/client";

const fmt2 = n => (n ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtD = n => (n < 0 ? "-$" : "$") + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// ─── CANDLESTICK CHART ────────────────────────────────────────────────────────

const CANDLE_TICKS = 3;   // How many price ticks form one candle
const MAX_CANDLES  = 60;   // Max candles shown at once
const CHART_H      = 180;
const PADDING      = { top: 10, bottom: 20, left: 8, right: 48 };

function buildCandles(prices) {
  if (!prices || prices.length < 2) return [];
  const candles = [];
  for (let i = 0; i < prices.length; i += CANDLE_TICKS) {
    const slice = prices.slice(i, i + CANDLE_TICKS);
    if (slice.length === 0) continue;
    candles.push({
      open:  slice[0],
      close: slice[slice.length - 1],
      high:  Math.max(...slice),
      low:   Math.min(...slice),
    });
  }
  return candles.slice(-MAX_CANDLES);
}

function CandlestickChart({ candles, livePrice }) {
  const svgRef  = useRef(null);
  const [width, setWidth] = useState(400);
  const [tooltip, setTooltip] = useState(null);

  useEffect(() => {
    const el = svgRef.current?.parentElement;
    if (!el) return;
    const ro = new ResizeObserver(e => setWidth(e[0].contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  if (!candles || candles.length === 0) {
    return (
      <div style={{ height: CHART_H, display: "flex", alignItems: "center",
        justifyContent: "center", color: "var(--text2)", fontSize: 11,
        fontFamily: "var(--mono)" }}>
        Loading chart...
      </div>
    );
  }

  const allPrices = candles.flatMap(c => [c.high, c.low]);
  if (livePrice) allPrices.push(livePrice);
  const rawMin = Math.min(...allPrices);
  const rawMax = Math.max(...allPrices);
  const pad    = (rawMax - rawMin) * 0.08 || rawMin * 0.005;
  const priceMin = rawMin - pad;
  const priceMax = rawMax + pad;
  const priceRange = priceMax - priceMin || 1;

  const innerW = width - PADDING.left - PADDING.right;
  const innerH = CHART_H - PADDING.top - PADDING.bottom;

  const toY = p => PADDING.top + innerH * (1 - (p - priceMin) / priceRange);
  const candleW = Math.max(3, Math.floor(innerW / candles.length) - 2);

  // Y axis tick prices
  const yTicks = 4;
  const yTickPrices = Array.from({ length: yTicks + 1 }, (_, i) =>
    priceMin + (priceRange * i) / yTicks
  );

  return (
    <div style={{ position: "relative", width: "100%", height: CHART_H }}
      onMouseLeave={() => setTooltip(null)}>
      <svg
        ref={svgRef}
        width={width}
        height={CHART_H}
        style={{ display: "block" }}
      >
        {/* Y-axis gridlines + labels */}
        {yTickPrices.map((p, i) => {
          const y = toY(p);
          return (
            <g key={i}>
              <line
                x1={PADDING.left} y1={y}
                x2={PADDING.left + innerW} y2={y}
                stroke="var(--border)" strokeWidth={0.5} strokeDasharray="3,4"
              />
              <text
                x={PADDING.left + innerW + 4} y={y + 4}
                fill="var(--text2)" fontSize={9}
                fontFamily="var(--mono, monospace)"
              >
                {p.toFixed(2)}
              </text>
            </g>
          );
        })}

        {/* Candles */}
        {candles.map((c, i) => {
          const x     = PADDING.left + i * (innerW / candles.length) + (innerW / candles.length - candleW) / 2;
          const isUp  = c.close >= c.open;
          const color = isUp ? "#3fb950" : "#f85149";
          const bodyY = toY(Math.max(c.open, c.close));
          const bodyH = Math.max(1, Math.abs(toY(c.open) - toY(c.close)));
          const wickX = x + candleW / 2;

          return (
            <g
              key={i}
              onMouseEnter={e => setTooltip({ x: e.clientX, candle: c })}
              style={{ cursor: "crosshair" }}
            >
              {/* Wick */}
              <line
                x1={wickX} y1={toY(c.high)}
                x2={wickX} y2={toY(c.low)}
                stroke={color} strokeWidth={1}
              />
              {/* Body */}
              <rect
                x={x} y={bodyY}
                width={candleW} height={bodyH}
                fill={isUp ? color : color}
                stroke={color} strokeWidth={0.5}
                opacity={isUp ? 0.85 : 0.85}
              />
            </g>
          );
        })}

        {/* Live price line */}
        {livePrice && (
          <g>
            <line
              x1={PADDING.left} y1={toY(livePrice)}
              x2={PADDING.left + innerW} y2={toY(livePrice)}
              stroke="var(--accent)" strokeWidth={1}
              strokeDasharray="5,3" opacity={0.7}
            />
            <rect
              x={PADDING.left + innerW + 2} y={toY(livePrice) - 8}
              width={44} height={14}
              fill="var(--accent)" rx={2}
            />
            <text
              x={PADDING.left + innerW + 4} y={toY(livePrice) + 3}
              fill="#0d1117" fontSize={9}
              fontFamily="var(--mono, monospace)" fontWeight="700"
            >
              {livePrice.toFixed(2)}
            </text>
          </g>
        )}
      </svg>

      {/* Hover tooltip */}
      {tooltip && (
        <div style={{
          position: "fixed",
          left: tooltip.x + 12,
          top: "auto",
          pointerEvents: "none",
          background: "var(--bg2)",
          border: "1px solid var(--border2)",
          borderRadius: 4,
          padding: "7px 10px",
          fontSize: 10,
          fontFamily: "var(--mono)",
          color: "var(--text)",
          zIndex: 100,
          lineHeight: 1.8,
          boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
        }}>
          <div style={{ color: "var(--text2)", marginBottom: 2 }}>OHLC</div>
          <div>O <span style={{ color: "var(--text)" }}>${fmt2(tooltip.candle.open)}</span></div>
          <div>H <span style={{ color: "#3fb950" }}>${fmt2(tooltip.candle.high)}</span></div>
          <div>L <span style={{ color: "#f85149" }}>${fmt2(tooltip.candle.low)}</span></div>
          <div>C <span style={{ color: tooltip.candle.close >= tooltip.candle.open ? "#3fb950" : "#f85149" }}>
            ${fmt2(tooltip.candle.close)}
          </span></div>
        </div>
      )}
    </div>
  );
}


// ─── TRADE PANEL ─────────────────────────────────────────────────────────────

export default function TradePanel({ ticker, priceData, user, portfolio, onTradeSuccess }) {
  const [qty, setQty]         = useState("10");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg]         = useState(null);
  const [rawPrices, setRawPrices] = useState([]);   // flat price array for candle building

  const s       = priceData || {};
  const holding = portfolio?.holdings?.find(h => h.ticker === ticker);
  const qtyNum  = parseFloat(qty) || 0;
  const buyTotal  = qtyNum * (s.ask || 0);
  const sellTotal = qtyNum * (s.bid || 0);

  // Load historical prices when ticker changes
  useEffect(() => {
    if (!ticker) return;
    setRawPrices([]);
    api.getTickerHistory(ticker, 300).then(d => {
      const hist = (d.history || []).map(r => r.price).filter(Boolean);
      setRawPrices(hist);
    }).catch(() => {});
  }, [ticker]);

  // Append live price every tick
  useEffect(() => {
    if (!s.price) return;
    setRawPrices(prev => {
      // Avoid duplicates on first load
      if (prev.length > 0 && prev[prev.length - 1] === s.price) return prev;
      const next = [...prev, s.price];
      return next.slice(-MAX_CANDLES * CANDLE_TICKS);  // cap memory
    });
  }, [s.price, s.tick]);

  const candles = buildCandles(rawPrices);

  async function handleTrade(action) {
    if (!qtyNum || qtyNum <= 0) { setMsg({ ok: false, text: "Enter a valid quantity." }); return; }
    setLoading(true); setMsg(null);
    try {
      const res = await api.trade(user.id, ticker, action, qtyNum);
      setMsg({ ok: true, text: res.message });
      onTradeSuccess?.();
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    } finally {
      setLoading(false);
    }
  }

  const change    = rawPrices.length >= 2 ? rawPrices[rawPrices.length - 1] - rawPrices[0] : 0;
  const changePct = rawPrices.length >= 2 && rawPrices[0] ? (change / rawPrices[0]) * 100 : 0;
  const up        = change >= 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>

      {/* Header */}
      <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 28, fontWeight: 700,
              color: "var(--text)", letterSpacing: -1 }}>{ticker}</div>
            <div style={{ fontSize: 10, color: "var(--text3)", letterSpacing: 2, marginTop: 2 }}>
              {s.cap_tier?.toUpperCase()} CAP · TICK {s.tick || 0}
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontFamily: "var(--mono)", fontSize: 26, fontWeight: 600,
              color: "var(--text)" }}>${fmt2(s.price)}</div>
            <div style={{ display: "flex", gap: 16, justifyContent: "flex-end", marginTop: 4 }}>
              <span style={{ fontFamily: "var(--mono)", fontSize: 11,
                color: up ? "var(--green)" : "var(--red)" }}>
                {up ? "▲" : "▼"} {Math.abs(changePct).toFixed(2)}%
              </span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--green)" }}>
                BID {fmt2(s.bid)}
              </span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--red)" }}>
                ASK {fmt2(s.ask)}
              </span>
            </div>
          </div>
        </div>

        {/* Sentiment bar */}
        {s.sentiment !== undefined && (
          <div style={{ marginTop: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <span className="label">SENTIMENT</span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 10,
                color: s.sentiment > 0 ? "var(--green)" : s.sentiment < 0 ? "var(--red)" : "var(--text3)" }}>
                {s.sentiment > 0 ? "BULLISH" : s.sentiment < 0 ? "BEARISH" : "NEUTRAL"} {(s.sentiment * 100).toFixed(0)}%
              </span>
            </div>
            <div style={{ height: 3, background: "var(--bg3)", borderRadius: 2, overflow: "hidden" }}>
              <div style={{
                height: "100%", borderRadius: 2,
                width: `${Math.abs(s.sentiment) * 50}%`,
                marginLeft: s.sentiment < 0 ? `${50 - Math.abs(s.sentiment) * 50}%` : "50%",
                background: s.sentiment > 0 ? "var(--green)" : "var(--red)",
                transition: "all 0.5s",
              }} />
            </div>
          </div>
        )}
      </div>

      {/* Candlestick chart */}
      <div style={{ padding: "8px 8px 0", flexShrink: 0, borderBottom: "1px solid var(--border)" }}>
        <CandlestickChart candles={candles} livePrice={s.price} />
        <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 8px 6px",
          fontFamily: "var(--mono)", fontSize: 9, color: "var(--text2)" }}>
          <span>{CANDLE_TICKS} ticks/candle</span>
          <span>{candles.length} candles</span>
        </div>
      </div>

      {/* Order form */}
      <div style={{ padding: "16px 20px", flex: 1, overflowY: "auto" }}>
        <div className="label" style={{ marginBottom: 12 }}>PLACE ORDER</div>

        {/* Qty input */}
        <div style={{ marginBottom: 12 }}>
          <div className="label" style={{ marginBottom: 6 }}>QUANTITY (SHARES)</div>
          <div style={{ display: "flex", gap: 6 }}>
            <input
              type="number" min="1" value={qty}
              onChange={e => setQty(e.target.value)}
              style={{ flex: 1, background: "var(--bg3)", border: "1px solid var(--border2)",
                borderRadius: 4, color: "var(--text)", fontSize: 15, padding: "10px 12px" }}
            />
            {[1, 5, 10, 25].map(n => (
              <button key={n} onClick={() => setQty(String(n))} style={{
                padding: "8px 10px", background: "var(--bg3)", border: "1px solid var(--border)",
                borderRadius: 4, fontSize: 11, color: "var(--text2)", cursor: "pointer",
              }}>{n}</button>
            ))}
          </div>
        </div>

        {/* Order summary */}
        <div style={{ background: "var(--bg2)", border: "1px solid var(--border)",
          borderRadius: 6, padding: "10px 14px", marginBottom: 14 }}>
          {[
            ["BUY TOTAL (at ask)",  fmtD(buyTotal),         "var(--red)"],
            ["SELL TOTAL (at bid)", fmtD(sellTotal),        "var(--green)"],
            ["AVAILABLE CASH",      fmtD(user?.cash ?? 0),  "var(--accent)"],
          ].map(([label, val, color]) => (
            <div key={label} style={{ display: "flex", justifyContent: "space-between",
              marginBottom: 6, fontSize: 12 }}>
              <span style={{ color: "var(--text2)" }}>{label}</span>
              <span style={{ fontFamily: "var(--mono)", color }}>{val}</span>
            </div>
          ))}
        </div>

        {/* Trade buttons */}
        <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
          <button onClick={() => handleTrade("buy")}
            disabled={loading || buyTotal > (user?.cash ?? 0)}
            style={{ flex: 1, padding: "13px 0", borderRadius: 6, fontSize: 12,
              fontWeight: 600, letterSpacing: 2, cursor: "pointer",
              background: "var(--green-bg)", color: "var(--green)", border: "1px solid #3fb95044" }}>
            ▲ BUY {ticker}
          </button>
          <button onClick={() => handleTrade("sell")}
            disabled={loading || !holding || holding.qty < qtyNum}
            style={{ flex: 1, padding: "13px 0", borderRadius: 6, fontSize: 12,
              fontWeight: 600, letterSpacing: 2, cursor: "pointer",
              background: "var(--red-bg)", color: "var(--red)", border: "1px solid #f8514944" }}>
            ▼ SELL {ticker}
          </button>
        </div>

        {/* Message */}
        {msg && (
          <div style={{
            padding: "10px 14px", borderRadius: 6, fontSize: 12, marginBottom: 12,
            background: msg.ok ? "var(--green-bg)" : "var(--red-bg)",
            color: msg.ok ? "var(--green)" : "var(--red)",
            border: `1px solid ${msg.ok ? "#3fb95044" : "#f8514944"}`,
          }}>
            {msg.text}
          </div>
        )}

        {/* Current position */}
        {holding && (
          <div style={{ background: "var(--bg2)", border: "1px solid var(--border)",
            borderRadius: 6, padding: "12px 14px" }}>
            <div className="label" style={{ marginBottom: 10 }}>YOUR POSITION</div>
            {[
              ["SHARES HELD",    holding.qty.toFixed(2)],
              ["AVG COST",       "$" + fmt2(holding.avg_cost)],
              ["CURRENT VALUE",  "$" + fmt2(holding.market_value)],
              ["UNREALIZED P&L", fmtD(holding.pnl)],
              ["RETURN",         ((holding.pnl_pct ?? 0) * 100).toFixed(2) + "%"],
            ].map(([label, val]) => (
              <div key={label} style={{ display: "flex", justifyContent: "space-between",
                marginBottom: 6, fontSize: 12 }}>
                <span style={{ color: "var(--text2)" }}>{label}</span>
                <span style={{ fontFamily: "var(--mono)",
                  color: label.includes("P&L") || label === "RETURN"
                    ? (holding.pnl >= 0 ? "var(--green)" : "var(--red)") : "var(--text)" }}>
                  {val}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}