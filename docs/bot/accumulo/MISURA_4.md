# MISURA 4 - valutazione "rimonta" (25/11)

Costruita, spenta di default (default byte-identico). Arena non giocata qui: `bash scripts/rust/rimonta_mac.command`.
## Cosa c'è
- `search.rs`: `Valutazione::Rimonta`; usa `race_info` di `corsa`. Parte dalla storica. Solo con race == -1 e non
  `op_next_wins` (si perde la corsa a campi fissi ma c'è ancora un turno per agire):
  1. progresso: campo avversario con D minima, gap = D+2; A = Might duratura in base + dei miei GANKING sugli altri campi;
     `+0,04 * min(A, gap)` (Might in base fino al gap vale 0,07 contro 0,05 sul campo).
  2. eccesso sui campi propri sicuri (miei, senza nemici): Might oltre `need = base avversaria + 3` conta 0,2 invece di 1.
  Negli altri stati (race +1, 0, op_next_wins) = storica. Costanti fisse. Collegata: `set_search_valutazione("rimonta")`,
  `decisione.py rifai --valutazione`, `--valutazione-orig`, `episodi.py --valutazione`, `arena_mazzi.py --valutazione-c/-a`.
- Deviazione dalla specifica (decisa dal caso di controllo "campo minacciato"): il premio del punto 1 non si applica se
  un campo proprio sicuro ha Might < need. Senza, con base avversaria 12 il rinforzo (0,05/Might) perdeva contro la base
  (0,07/Might) pur col campo sotto need; col vincolo il rinforzo regge. `campo_proprio_scoperto` in `search.rs`.
- `episodi.py`: ora stampa il §8 diviso per stato della corsa (`corsa()` = specchio Python di `race_info` sulla posizione
  prima della mossa; denominatore = decisioni Play/Move del campione). `decisione_rs.riassunto` espone `v`.
## Verifiche
Test nuovi in `tests/rust/test_valutazione.py` (gating race +1 / op_next_wins / nessuno segna = storica; race -1: unita'
in base batte campo con margine >= need; campo minacciato: rinforzo >= base). `pytest tests/rust`: 311 passed. `cargo test` ok. `diff_trace.py --modo self --semi 1-30`: 30/30 identiche.
## 1. I 18 episodi di MISURA_1 a 138 iterazioni (storica -> rimonta)
Stato della corsa nella posizione prima della mossa: race -1 in 10, race +1 in 8, mai op_next_wins.
- race -1 (10): 6 diventano "in base" (Pyke x2, Trifarian Captain 201243, Fizz, Traveling Merchant, Reckless Innovator ->
  Fizz Trickster in base), 4 restano §8 (Fiora, Pit Rookie, Sett Kingpin, Zed: margini piccoli o campo sguarnito).
- race +1 (8): 8/8 uguali alla storica (resta §8), come voluto.
I 6 cambi cadono tutti dove il campione perde la corsa, nessuno dove la vince.
## 2. Tasso §8 (`episodi.py`, semi 1-20, due posti, 138 iter), storica rilanciata sugli stessi semi
| matchup | storica | rimonta |
|---|---|---|
| ES | 200/1458 = 13,7% | 129/1394 = 9,3% |
| EK | 167/1407 = 11,9% | 123/1474 = 8,3% |
Per stato della corsa (episodi / decisioni Play-Move del campione; race 0 sempre 0/18-24):
| | storica ES | rimonta ES | storica EK | rimonta EK |
|---|---|---|---|---|
| race -1 | 115/203 = 56,7% | 46/173 = 26,6% | 81/156 = 51,9% | 30/159 = 18,9% |
| race +1 | 85/130 = 65,4% | 83/139 = 59,7% | 86/152 = 56,6% | 93/161 = 57,8% |
Il calo e' tutto in race -1 (circa meta' o meno); in race +1 il tasso e' invariato entro il rumore. (Le partite divergono
dopo la prima mossa cambiata, quindi i denominatori non coincidono.) Accumulo era 4,9% / 4,1% ma perdeva l'arena.
## Limiti
- Il tasso §8 non e' la forza: decide l'arena. Il progresso A e' la Might in base, non un attacco simulato (niente
  incantesimi che muovono/potenziano, niente showdown).
- Pesi 0,04 / need +3 / 0,2 non tarati.
## Arena (Mac)
`cd ~/projects/rbsim2026/rbsim-rust && git fetch && git checkout claude/focused-cannon-khz3rg && git pull && bash scripts/rust/rimonta_mac.command`
(dopo il merge in `rust`: `git checkout rust && git pull`). `rimonta` contro il campione, 800 coppie EK e ES, seed 90000+;
uscita `docs/bot/accumulo/arena_rimonta_<data>/riepilogo.txt` e zip sulla Scrivania.
