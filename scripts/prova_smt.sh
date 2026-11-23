#!/bin/bash
# Prova sul server (23/11): le arene con un processo per thread (due per
# core) danno bot più deboli? Il bot pensa 0,4 s di CPU per mossa; due
# processi sullo stesso core fanno ciascuno meno iterazioni in quel tempo,
# ma le partite al minuto quasi raddoppiano.
# 1. Iterazioni per decisione del campione (bot a mano con i prior di ekr_s8)
#    contro se stesso, Evelynn-Kha'Zix, 128 coppie (seed 60.000+), con un
#    processo per core e con un processo per thread: rapporto f.
# 2. Il campione con budget 0,4 x f (le iterazioni di un processo per
#    thread) contro il campione a 0,4 s, un processo per core; 100 coppie per
#    ciascuno dei dieci matchup (seed 70.000 + 1.000 x indice).
#    Regola fissata prima: a pesi uguali sui dieci, limite inferiore > 0,47
#    (al massimo 3 punti persi) -> le arene possono usare un processo per thread.
# Circa 40 minuti, da lanciare ad arena finita (nient'altro in parallelo).
# Risultato: runs/smt/PROVA.txt
cd "$(dirname "$0")/.." || exit 1
export PATH="$HOME/.local/bin:$PATH"
R=runs/smt
mkdir -p "$R"
C=runs/rengar/ekr_s8/ckpt_020032.pt
[ -f "$C" ] || { echo "Manca $C"; exit 1; }
fisici=$(lscpu -p=core,socket | grep -v '^#' | sort -u | wc -l)
logici=$(nproc)
for w in "$fisici" "$logici"; do
  grep -q "iterazioni per decisione" "$R/ITER_$w.txt" 2>/dev/null && continue
  uv run --extra rl python scripts/diag/arena_mazzi.py --ckpt "$C" --ckpt-avversario "$C" --vecchi --blocchi \
      --tenuta EK --coppie EK=128 --seed0 60000 --esito-positivo fatto --esito-negativo fatto \
      --out "$R/ITER_$w.txt" --righe "$R/ITER_$w.jsonl" --workers "$w" || exit 1
done
it() { grep -E "^   (candidato|avversario): [0-9]+ iterazioni" "$1" | tail -2 | awk '{s += $2} END {print s / NR}'; }
i1=$(it "$R/ITER_$fisici.txt")
i2=$(it "$R/ITER_$logici.txt")
b=$(python3 -c "print(round(0.4 * $i2 / $i1, 3))")
echo "Iterazioni per decisione: $i1 con $fisici processi, $i2 con $logici; budget equivalente $b s" | tee -a "$R/PROVA.txt"
uv run --extra rl python scripts/diag/arena_mazzi.py --ckpt "$C" --ckpt-avversario "$C" --budget-candidato "$b" \
    --vecchi --blocchi --tenuta EK,ER,KR,EI,KI,RI,ES,KS,RS,IS \
    --coppie EK=100 ER=100 KR=100 EI=100 KI=100 RI=100 ES=100 KS=100 RS=100 IS=100 --seed0 70000 \
    --esito-positivo "un processo per thread va bene" --esito-negativo "un processo per core (i bot si indeboliscono)" \
    --out "$R/PROVA.txt" --workers "$fisici"
