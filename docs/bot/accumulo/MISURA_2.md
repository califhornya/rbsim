# MISURA 2 - valutazione "accumulo" candidata (25/11)

Costruita, spenta di default. Arena non giocata qui (decisione del proprietario: la gira il Mac).
## Cosa c'è (commit cc69524)
- `search.rs`: `enum Valutazione { Storica, Accumulo{k,alpha} }` sul `SearchCore` (default Storica), usata in tutte le
  foglie (`evaluate`, `iterate`, `iterate_now`, `replay_values`, mulligan). Su un campo controllato dal campione senza
  nemici: `0,05*(min(mine,need) + alpha*max(0,mine-need))`, `need = Might in base dell'avversario + k`. Il resto invariato.
- Binding: `set_search_valutazione(seat, nome, k=3, alpha=0.2)`; `set_search_valutazione_at(seat, k_ricerca, ...)`
  (solo la ricerca k: il prefisso del rifacimento resta storico); `valore_costruito` (test).
- `decisione.py rifai --valutazione accumulo [--k-acc K --alpha A]` (`--k` resta l'indice di ricerca);
  `episodi.py --valutazione ... --k-acc --alpha`; `arena_mazzi.py --valutazione-c/-a`, `--k-c/-a`, `--alpha-c/-a`
  (c = candidato, a = avversario; registrati in `opz` delle righe e nella provenienza).
- Test: `tests/rust/test_valutazione.py` (storica = default sul search_log; posizione costruita: base vuota avversaria ->
  accumulo preferisce l'unita' in base, storica sul campo; avversario con 12 in base -> il rinforzo vale ancora).
## Verifiche di non regressione
`pytest tests/rust`: 296 passed. `cargo test`: ok. `diff_trace.py --modo self --semi 1-30`: 30/30 identiche.
## 1. Rifacimento dei 18 episodi di MISURA_1 (138 e 500 iterazioni, regole D72-D80)
Scelta rifatta, classificata: stessa unita' sul campo (§8) / in base / attacco (Move su altro campo) / altra mossa (magia).
Non-§8 = l'unita' non resta sul campo gia' tenuto.
| valutazione | 138: non-§8 su 18 (base+attacco+altra) | 500: non-§8 su 18 |
|---|---|---|
| storica | 1 (0+0+1) | 3 (1+0+2) |
| accumulo k=3 a=0,2 | 13 (10+1+2) | 14 (12+1+1) |
| accumulo k=3 a=0,5 | 13 (10+1+2) | 12 (10+1+1) |
| accumulo k=6 a=0,2 | 9 (7+1+1) | 10 (7+1+2) |
Restano §8 con k=3: i tre Pit Rookie / Sett Kingpin su 154531 t9, 201243 t6 (x2) e Zed 203513 t6 (margini piccoli o campo
quasi sguarnito: ragionevole). Con k=6 anche Pyke, Fizz, Fiora tornano sul campo (need = 6+base avversaria troppo alto).
## 2. Tasso §8 con episodi.py (ES, EK, semi 1-20, due posti, 138 iter, accumulo 3/0,2)
| matchup | storica (stessi semi) | accumulo | 
|---|---|---|
| ES | 200/1458 = 13,7% | 66/1356 = 4,9% |
| EK | 167/1407 = 11,9% | 53/1283 = 4,1% |
(§7 spreco con accumulo: ES 3, EK 0.) Il tasso scende a circa un terzo; non e' zero perche' il criterio §8 conta anche
rinforzi sotto `need` (Might sul campo < base avversaria + k), che per costruzione restano apprezzati.
## 3. Arena
Non giocata. Misura veloce: ~0,5 s/partita aggregata su 4 core (138 iter, EK/ES), quindi 400 coppie per matchup ~ 15 min.
Comando (candidato accumulo vs campione storica, stesso ckpt, seed nuovi 70000+/76000+, posti scambiati dall'arena):
```
python scripts/diag/arena_mazzi.py --motore rust --regole 6427b90+D72-D80 \
  --ckpt runs/sett/ekris_s12/ckpt_040000.pt --ckpt-avversario runs/sett/ekris_s12/ckpt_040000.pt \
  --vecchi EK --blocchi ES --coppie EK=N ES=N --seed0 70000 \
  --iterazioni-candidato 138 --iterazioni-avversario 138 --win-probe-candidato --win-probe-avversario \
  --valutazione-c accumulo --k-c 3 --alpha-c 0.2 --out runs/accumulo/arena_3_02.txt
```
(`--workers` default = core-1; riprende dalle righe gia' giocate. Le soglie PROMOSSO/no stampate vanno ignorate: conta
il punteggio per matchup con IC al 95% sulle coppie. Un solo matchup: `--vecchi EK --blocchi` vuoto / `--vecchi` vuoto
`--blocchi ES`.)
## Limiti
Il §8 scende, ma la forza non e' misurata: i 13 non-§8 sono scelte diverse, non per forza migliori. Decide l'arena.
