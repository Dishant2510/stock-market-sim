// api/client.js — all backend API calls
// In production, set VITE_API_URL env var to your Railway backend URL
// e.g. VITE_API_URL=https://your-app.up.railway.app

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function req(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  // Users
  register: (username, password) =>
    req("/users/register", { method: "POST", body: JSON.stringify({ username, password }) }),
  login: (username, password) =>
    req("/users/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  getUser: (userId) => req(`/users/${userId}`),

  // Prices
  getAllPrices: () => req("/prices"),
  getTickerHistory: (ticker, limit = 120) =>
    req(`/prices/${ticker}?limit=${limit}`),

  // Trading
  trade: (userId, ticker, action, qty) =>
    req("/trade", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, ticker, action, qty }),
    }),

  // Portfolio
  getPortfolio: (userId) => req(`/portfolio/${userId}`),
  getTrades: (userId, limit = 50) => req(`/trades/${userId}?limit=${limit}`),

  // Market data
  getNews: (limit = 20) => req(`/news?limit=${limit}`),
  getLeaderboard: (limit = 20) => req(`/leaderboard?limit=${limit}`),
  getHealth: () => req("/health"),
};