#!/bin/bash
# Prepara un server Ubuntu 24.04 appena creato (shell di root) per scripts/rust/movimento.command.
# Idempotente: si puo' rilanciare. Non scarica il repo ne' il checkpoint.
#   bash server_prepara.sh
set -euo pipefail

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential git curl tmux pkg-config

if ! command -v rustc >/dev/null 2>&1 && [ ! -x "$HOME/.cargo/bin/rustc" ]; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
fi
# shellcheck disable=SC1091
. "$HOME/.cargo/env"

if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
grep -q 'cargo/env' "$HOME/.bashrc" 2>/dev/null || echo '. "$HOME/.cargo/env"' >> "$HOME/.bashrc"
grep -q '.local/bin' "$HOME/.bashrc" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"

echo
echo "== versioni"
rustc --version
cargo --version
uv --version
git --version | head -1
tmux -V
echo "core: $(nproc)"
cat <<'MSG'

== prossimi passi (apri una nuova shell o `source ~/.bashrc` per avere rustc e uv nel PATH)
1. git clone <URL del repo> rbsim && cd rbsim && git checkout rust
2. dal tuo computer, copia il checkpoint del campione:
     scp runs/sett/ekris_s12/ckpt_040000.pt root@<server>:rbsim/runs/sett/ekris_s12/
   (sul server prima: mkdir -p rbsim/runs/sett/ekris_s12)
3. dentro tmux (cosi' la corsa sopravvive alla disconnessione):
     tmux new -s movimento
     bash scripts/rust/movimento.command
   avanzamento: tail -f runs/movimento/*.out   (stacca con Ctrl-b d, riattacca con tmux attach -t movimento)
MSG
