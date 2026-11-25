# MISURA 3 - valutazioni "minaccia" e "corsa" (25/11)

Costruite, spente di default. Arena non giocata qui: la gira il Mac con `scripts/rust/corsa_mac.command`.
## Cosa c'è
- `search.rs`: `Valutazione::{Minaccia, Corsa}` accanto a `Storica`/`Accumulo` (stesso meccanismo); `race_info`, `threat`;
  `table_value_v` somma `w * threat` alla storica. `lib.rs`: nomi "minaccia"/"corsa" in `set_search_valutazione`,
  `valore_costruito` (con `punti`, `attivo`, `gank`) e `analisi_costruita` -> (race, op_next_wins, threat) per i test.
- Corsa: tengono solo i campi; la prossima Beginning Phase e' di chi NON e' `obs.active` alla foglia; si alternano le
  tenute fino a V (`victory_score`, max 30 passi). race = +1 / -1 / 0 (nessuno segna). `op_next_wins` = tocca a lui e
  `punti_avv + tenute_avv >= V`.
- Minaccia: A = Might duratura in base + quella dei miei GANKING (`UnitView.keywords`) su un altro campo; per ogni campo
  dell'avversario `logistica((A - D - 2) / 2)`, massimo. Zero se `op_next_wins`. Scelta mia: zero anche se A = 0 (senza
  attaccanti la logistica darebbe 0,27 per niente).
- Pesi fissi, non esposti: minaccia 0,30; corsa 0,45 se race -1, 0,15 se +1, 0,30 se 0.
- Collegamento: `decisione.py rifai --valutazione`, `episodi.py --valutazione`, `arena_mazzi.py --valutazione-c/-a`.
## Correzione (review PR 54)
`episodi.py --valutazione X` stampava comandi che rigiocavano la partita con la storica. Ora aggiunge
`--valutazione-orig NOME:k:alpha` e `decisione.py rifai --autonoma` la porta nella partita originale (`partita_da_args`):
il prefisso si riproduce e la prima riga dice "riproduce la mossa originale: si'" (provato su ES:7:b con minaccia).
## Verifiche
`pytest tests/rust`: tutti passati (305 + i nuovi). `cargo test` ok. `diff_trace.py --modo self --semi 1-30`: 30/30 identiche.
Test nuovi: corsa 6-6 -> -1, 7-6 -> +1, 7-7 -> op_next_wins; caso 1 (corsa persa: unita' in base > accumulata, minaccia e
corsa), caso 2 (corsa vinta: rinforzo >= base), caso 3 (op_next_wins: valore = storica); nomi collegati alle partite.
## 1. I 18 episodi di MISURA_1 a 138 iterazioni
17 rifatti (ep2 non salvato: ricostruito EK:2:a k10). Con `minaccia` e con `corsa`: 18/18 restano §8 (stessa mossa
dell'originale), 0 in base, 0 attacchi. Esempio EK:8 k16: q di "Play ... to BF0" 0,753 invariata, della alternativa in base 0,735 -> 0,736.
Il termine c'e' (q cambia nella terza cifra) ma non sposta la scelta: nelle posizioni §8 la minaccia e' piccola.
## 2. Tasso §8 (`episodi.py`, semi 1-20, due posti, 138 iter)
| matchup | storica (MISURA_2) | minaccia | corsa |
|---|---|---|---|
| ES | 13,7% | 191/1448 = 13,2% | 188/1449 = 13,0% |
| EK | 11,9% | 170/1414 = 12,0% | 170/1481 = 11,5% |
Il §8 non cambia (accumulo era 4,9% / 4,1%): per costruzione questi termini non rendono sgradita la Might sul campo.
## Limiti
- Incantesimi che muovono o potenziano non contano nella minaccia; niente stima dell'attacco reale (showdown, Might
  della difesa che si rinforza), solo la logistica su A - D. Nessun tuning dei pesi.
- Il tasso §8 non e' la forza: decide l'arena (due candidati, 800 coppie EK e ES ciascuno, seed 80000+).
## Arena (Mac)
`bash scripts/rust/corsa_mac.command` da `~/projects/rbsim2026/rbsim-rust` (ramo del lavoro): `minaccia` poi `corsa` contro
il campione; `docs/bot/accumulo/arena_corsa_<data>/riepilogo.txt` e zip sulla Scrivania.
