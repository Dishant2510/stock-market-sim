"""
rl_agent.py
─────────────────────────────────────────────────────────────────────────────
PPO (Proximal Policy Optimisation) agent for the market making task.

Architecture:
  - Shared MLP backbone (state → hidden)
  - Actor head: outputs mean + log_std for Gaussian action distribution
  - Critic head: outputs scalar state value V(s)

Uses PyTorch. Falls back gracefully if torch not installed.

Training:
  See notebooks/04_rl_market_maker.ipynb

Inference (live market making):
  agent = RLMarketMaker.load("models/rl_mm_policy.pt")
  action = agent.act(state)   # returns [spread_action, lean_action]

Saved model format: torch state dict + metadata dict in a single .pt file.
─────────────────────────────────────────────────────────────────────────────
"""

import logging
import numpy as np
from pathlib import Path

log = logging.getLogger(__name__)

STATE_DIM  = 8
ACTION_DIM = 2
HIDDEN_DIM = 128

# ─── POLICY NETWORK ───────────────────────────────────────────────────────────

def _build_network():
    """Import torch and return network classes. Raises ImportError if not installed."""
    import torch
    import torch.nn as nn

    class PolicyNet(nn.Module):
        """Shared-backbone Actor-Critic network."""
        def __init__(self):
            super().__init__()
            self.backbone = nn.Sequential(
                nn.Linear(STATE_DIM, HIDDEN_DIM), nn.Tanh(),
                nn.Linear(HIDDEN_DIM, HIDDEN_DIM), nn.Tanh(),
            )
            self.actor_mean    = nn.Linear(HIDDEN_DIM, ACTION_DIM)
            self.actor_log_std = nn.Parameter(torch.zeros(ACTION_DIM))
            self.critic        = nn.Linear(HIDDEN_DIM, 1)

        def forward(self, x):
            h     = self.backbone(x)
            mean  = torch.tanh(self.actor_mean(h))   # actions in [-1, 1]
            value = self.critic(h)
            return mean, self.actor_log_std.exp(), value

        def get_action(self, state_np: np.ndarray):
            """Sample action and return (action_np, log_prob, value)."""
            import torch
            x     = torch.FloatTensor(state_np).unsqueeze(0)
            mean, std, value = self.forward(x)
            dist  = torch.distributions.Normal(mean, std)
            action = dist.sample()
            action = torch.clamp(action, -1, 1)
            return (action.squeeze().detach().numpy(),
                    dist.log_prob(action).sum(-1).item(),
                    value.item())

        def get_value(self, state_np: np.ndarray) -> float:
            import torch
            x = torch.FloatTensor(state_np).unsqueeze(0)
            _, _, v = self.forward(x)
            return v.item()

    return PolicyNet


# ─── PPO TRAINER ──────────────────────────────────────────────────────────────

class PPOTrainer:
    """
    Proximal Policy Optimisation trainer.

    Usage:
        trainer = PPOTrainer()
        trainer.train(envs, n_episodes=200)
        trainer.save("models/rl_mm_policy.pt")
    """

    def __init__(
        self,
        lr           = 3e-4,
        gamma        = 0.99,
        gae_lambda   = 0.95,
        clip_eps     = 0.2,
        n_epochs     = 4,
        batch_size   = 64,
        value_coef   = 0.5,
        entropy_coef = 0.01,
    ):
        import torch
        import torch.optim as optim

        self.gamma        = gamma
        self.gae_lambda   = gae_lambda
        self.clip_eps     = clip_eps
        self.n_epochs     = n_epochs
        self.batch_size   = batch_size
        self.value_coef   = value_coef
        self.entropy_coef = entropy_coef

        PolicyNet    = _build_network()
        self.policy  = PolicyNet()
        self.optim   = optim.Adam(self.policy.parameters(), lr=lr)
        self.history = {"episode_reward": [], "episode_pnl": [], "entropy": []}

    def _collect_rollout(self, env):
        """Run one episode and collect (state, action, reward, value, log_prob, done) tuples."""
        states, actions, rewards, values, log_probs, dones = [], [], [], [], [], []

        state = env.reset(seed=np.random.randint(0, 10000))
        done  = False

        while not done:
            action, lp, v = self.policy.get_action(state)
            next_state, reward, done, _ = env.step(action)

            states.append(state)
            actions.append(action)
            rewards.append(reward)
            values.append(v)
            log_probs.append(lp)
            dones.append(done)

            state = next_state

        return states, actions, rewards, values, log_probs, dones, env.total_pnl

    def _compute_gae(self, rewards, values, dones):
        """Generalised Advantage Estimation."""
        import torch
        advantages = []
        gae        = 0.0
        next_val   = 0.0

        for t in reversed(range(len(rewards))):
            delta = rewards[t] + self.gamma * next_val * (1 - dones[t]) - values[t]
            gae   = delta + self.gamma * self.gae_lambda * (1 - dones[t]) * gae
            advantages.insert(0, gae)
            next_val = values[t]

        returns    = [a + v for a, v in zip(advantages, values)]
        adv_tensor = torch.FloatTensor(advantages)
        adv_tensor = (adv_tensor - adv_tensor.mean()) / (adv_tensor.std() + 1e-8)
        return adv_tensor, torch.FloatTensor(returns)

    def _ppo_update(self, states, actions, old_log_probs, advantages, returns):
        """One epoch of PPO gradient updates."""
        import torch
        import torch.nn.functional as F

        states_t    = torch.FloatTensor(np.array(states))
        actions_t   = torch.FloatTensor(np.array(actions))
        old_lp_t    = torch.FloatTensor(old_log_probs)

        n = len(states)
        for _ in range(self.n_epochs):
            idx = torch.randperm(n)
            for start in range(0, n, self.batch_size):
                mb = idx[start:start + self.batch_size]
                s  = states_t[mb]
                a  = actions_t[mb]

                mean, std, values_pred = self.policy(s)
                dist    = torch.distributions.Normal(mean, std)
                new_lp  = dist.log_prob(a).sum(-1)
                entropy = dist.entropy().sum(-1).mean()

                ratio   = (new_lp - old_lp_t[mb]).exp()
                adv_mb  = advantages[mb]

                # Clipped surrogate loss
                obj1    = ratio * adv_mb
                obj2    = ratio.clamp(1 - self.clip_eps, 1 + self.clip_eps) * adv_mb
                actor_loss  = -torch.min(obj1, obj2).mean()
                critic_loss = F.mse_loss(values_pred.squeeze(), returns[mb])

                loss = actor_loss + self.value_coef * critic_loss - self.entropy_coef * entropy

                self.optim.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.policy.parameters(), 0.5)
                self.optim.step()

        return entropy.item()

    def train(self, env_factory, n_episodes: int = 300, log_every: int = 20):
        """
        Train the agent.

        Args:
            env_factory: callable() → MarketMakerEnv (new env each episode)
            n_episodes:  total training episodes
            log_every:   print progress every N episodes
        """
        log.info(f"PPO training: {n_episodes} episodes")

        for ep in range(n_episodes):
            env = env_factory()
            states, actions, rewards, values, log_probs, dones, ep_pnl = \
                self._collect_rollout(env)

            advantages, returns = self._compute_gae(rewards, values, dones)
            entropy = self._ppo_update(states, actions, log_probs, advantages, returns)

            ep_reward = sum(rewards)
            self.history["episode_reward"].append(ep_reward)
            self.history["episode_pnl"].append(ep_pnl)
            self.history["entropy"].append(entropy)

            if (ep + 1) % log_every == 0:
                recent_r   = np.mean(self.history["episode_reward"][-log_every:])
                recent_pnl = np.mean(self.history["episode_pnl"][-log_every:])
                log.info(
                    f"Ep {ep+1:4d}/{n_episodes} | "
                    f"reward={recent_r:+.4f} | "
                    f"pnl=${recent_pnl:+.2f} | "
                    f"entropy={entropy:.4f}"
                )

        log.info("Training complete")

    def save(self, path: str | Path):
        """Save policy weights + metadata."""
        import torch
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "state_dict": self.policy.state_dict(),
            "history":    self.history,
            "state_dim":  STATE_DIM,
            "action_dim": ACTION_DIM,
            "hidden_dim": HIDDEN_DIM,
        }, path)
        log.info(f"Policy saved → {path}")


# ─── INFERENCE WRAPPER ────────────────────────────────────────────────────────

class RLMarketMaker:
    """
    Thin inference wrapper loaded by market_maker.py at server startup.
    Falls back to passive market making if model file missing or torch unavailable.
    """

    def __init__(self):
        self.policy   = None
        self.loaded   = False
        self._history: dict[str, np.ndarray] = {}  # rolling state per ticker

    def load(self, path: str | Path = "models/rl_mm_policy.pt") -> bool:
        """
        Load trained policy. Returns True on success.
        Called once at startup by market_maker.py.
        """
        path = Path(path)
        if not path.exists():
            log.info(f"RL model not found at {path} — using passive market maker")
            return False
        try:
            import torch
            PolicyNet = _build_network()
            ckpt      = torch.load(path, map_location="cpu", weights_only=False)
            self.policy = PolicyNet()
            self.policy.load_state_dict(ckpt["state_dict"])
            self.policy.eval()
            self.loaded = True
            log.info(f"RL market maker loaded from {path}")
            return True
        except Exception as e:
            log.warning(f"Failed to load RL model: {e} — using passive market maker")
            return False

    def get_quotes(
        self,
        ticker:     str,
        mid_price:  float,
        inventory:  float,
        cash:       float,
        imbalance:  float,
        sentiment:  float,
        price_history: list,
        sigma:      float,
        cap_tier:   str,
    ) -> tuple[float, float]:
        """
        Compute RL-driven bid/ask quotes for one ticker.
        Returns (bid, ask). Falls back to passive if model not loaded.
        """
        from config import CAP_PROFILES

        base_spread = CAP_PROFILES[cap_tier]["spread_pct"]

        if not self.loaded or self.policy is None:
            return (
                round(mid_price * (1 - base_spread), 4),
                round(mid_price * (1 + base_spread), 4),
            )

        # Build state vector
        anchor    = mid_price   # simplified: use current price as anchor for inference
        price_dev = 0.0         # no deviation from self at inference time

        inv_norm    = np.clip(inventory / 500, -1, 1)
        cash_norm   = np.clip(cash / 100_000 - 1, -1, 1)
        imb_norm    = np.clip(imbalance / 10, -1, 1)
        sent_norm   = np.clip(sentiment, -1, 1)

        if len(price_history) >= 20:
            rets      = np.diff(price_history[-20:]) / np.array(price_history[-20:-1])
            vol_reg   = np.clip(rets.std() / (sigma + 1e-8), 0, 3) / 3
            ret5      = np.clip((price_history[-1] - price_history[-6]) / price_history[-6] * 50, -1, 1) if len(price_history) >= 6 else 0.0
            ret20     = np.clip((price_history[-1] - price_history[-20]) / price_history[-20] * 20, -1, 1)
        else:
            vol_reg = 0.5
            ret5    = 0.0
            ret20   = 0.0

        state = np.array([price_dev, inv_norm, cash_norm, imb_norm,
                          sent_norm, vol_reg, ret5, ret20], dtype=np.float32)

        action, _, _ = self.policy.get_action(state)
        spread_action, lean_action = float(action[0]), float(action[1])

        spread = base_spread * (1.0 + spread_action)   # [0, 2x base]
        spread = max(base_spread * 0.3, min(spread, base_spread * 3))
        lean   = lean_action * base_spread * 0.5

        bid = round(mid_price * (1 - spread / 2) + lean, 4)
        ask = round(mid_price * (1 + spread / 2) + lean, 4)

        # Sanity: bid < mid < ask
        bid = min(bid, mid_price * 0.9999)
        ask = max(ask, mid_price * 1.0001)

        return bid, ask


# ─── SINGLETON ────────────────────────────────────────────────────────────────
# Imported by market_maker.py

rl_mm = RLMarketMaker()
