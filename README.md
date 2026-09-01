# Riftbound Simulator

A modular Python simulator for **Riftbound**, the new League of Legends TCG.

## Quick start

```bash
uv sync
uv run rbsim simulate --games 1000 --seed 42
```

## Running the RL / self-play stack on a remote machine

The core engine is dependency-light. The reinforcement-learning stack (PyTorch)
is an **optional extra** so you can develop the engine locally and run the heavy
AlphaZero-style self-play on a rented GPU machine.

```bash
git clone <this repo> && cd rbsim
uv sync                 # engine only (light: numpy, no torch)
uv sync --extra rl      # + PyTorch, for encoding→network→self-play training
uv run pytest -q        # sanity check
```

Notes for remote/GPU boxes:
- The network is **CUDA-aware**: it uses the GPU automatically when `torch.cuda`
  is available, else CPU. No code change needed between your laptop and a rented box.
- All randomness is **seedable** (game seeds, RNGs) for reproducible runs.
- `riftbound/ai/encoding.py` turns a game position into fixed-size numbers (state)
  and defines the fixed move-slot space (actions) the network reads/writes.
