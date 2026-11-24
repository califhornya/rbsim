# Rapporto EK: porting del motore in Rust, primo matchup

Ramo `claude/peaceful-lamport-gynyab`. Riferimento Python: `6427b90`. Il motore delle regole non è stato modificato; l'unico fix Python è in `PPOAgent.inner` (vedi Divergenze, punto 4).

**Traguardo EK raggiunto.** Partite complete in entrambi i posti, semi tenuti da parte identici, e il checkpoint allenato `ckpt_020032.pt` gioca su Rust con esempi identici bit per bit (20/20, sul Mac).

## In breve: minuti per lo stesso carico, sul Mac
Misure ufficiali del Mac di Matteo: Apple Silicon, Python 3.13.2, torch 2.13. Checkpoint `ckpt_020032.pt` (sha `6576d1fee3bd96ee`). Il ciclo usa 8 processi e 8 thread torch nell'aggiornamento. File in `docs/rust/misure/mac_*.json`.

| carico | Python | Rust | guadagno |
|---|---|---|---|
| raccolta su un core, 100 partite self-play | 14,7 s (147 ms a partita) | 3,5 s (34 ms) | **×4,2** |
| raccolta su un core, 100 partite contro simple_trade | 10,6 s | 2,0 s | **×5,2** |
| ciclo PPO a 8 processi: raccolta di 64 partite | 1,89 s | 0,75 s | **×2,5** |
| ciclo PPO a 8 processi: aggiornamento | 3,13 s | 3,09 s | = |
| **ciclo PPO completo, 64 partite** | **5,02 s** | **3,84 s** | **×1,31 (−24%)** |
| **1.000 partite di training** | **1,31 min** | **1,00 min** | |
| una run da 20.000 partite, senza pannelli | 26 min | 20 min | |

Sul Mac l'aggiornamento è già veloce e la raccolta Python era già il 38% del ciclo: Rust la porta al 20%, e l'aggiornamento diventa l'80% del ciclo. Il guadagno sul ciclo è quindi minore che sul container (×1,57), dove la raccolta pesava di più.

## Le stesse misure sul container Linux
Le misure vengono dal container Linux (Intel Xeon 2,1 GHz, 4 core, Python 3.13, torch 2.13 CPU), con i pesi `PPONet()` dal seme 1 (sha `02c45ba0d9b97266`). Il motore Rust è compilato in release e nessuna misura usa le tracce.

| carico | Python | Rust | guadagno |
|---|---|---|---|
| raccolta PPO EK su un core, 60 partite self-play | 16,4 s (273 ms a partita) | 5,6 s (94 ms) | **×2,9** |
| ciclo PPO a 4 processi: raccolta di 64 partite | 5,32 s | 1,89 s | **×2,8** |
| ciclo PPO a 4 processi: aggiornamento | 4,90 s | 4,62 s | = |
| **ciclo PPO completo, 64 partite** | **10,2 s** | **6,5 s** | **×1,57 (−36%)** |
| **1.000 partite di training** | **2,7 min** | **1,7 min** | |
| una run da 20.000 partite, senza pannelli | 53 min | 34 min | |

Note di metodo:
- Ciclo: mediane di 6 cicli per motore, presi da 2 esecuzioni per motore in ordine alternato (Python, Rust, Python, Rust). I file sono `docs/rust/misure/ciclo_*_w4_*.json`.
- Raccolta su un core: `docs/rust/misure/raccolta_un_core_self.json`. Una ripetizione della stessa misura ha dato ×3,07, ma era sovrapposta ad altro lavoro e non la tengo.
- Il ciclo di riscaldamento gioca le stesse 64 partite in tutte e quattro le esecuzioni: 6.232 esempi, 17,17 turni medi. Lì la raccolta richiede 5,7–5,8 s in Python e 1,85–2,09 s in Rust.
  - Nelle misure, dal ciclo 1 in poi le partite di Python e Rust si separavano, e così due esecuzioni Python fra loro su Linux. La causa non era l'aggiornamento: era il contesto `made` di `PPOAgent.inner`, che dipendeva dal riuso degli indirizzi di memoria (Divergenze, punto 4).
  - Dopo il fix, `scripts/rust/parita_ciclo.py` dà gli stessi hash di esempi e pesi in Python e in Rust a ogni ciclo (3 cicli su 3, 4 processi). Le misure qui sopra sono precedenti al fix: il carico dal ciclo 1 è lo stesso in media, non partita per partita.
- Variabilità fra esecuzioni: la raccolta Python oscilla fra 4,6 e 6,0 s per ciclo, quella Rust fra 1,75 e 1,95 s. L'aggiornamento oscilla fra 4,4 e 6,1 s in entrambi i motori.
- Compilazione e avvio sono a parte: la build release di `riftbound_rs` richiede circa 30 s (incrementale) e il caricamento del registro e della rete 1,4 s per processo.

Dove va ora il tempo:
- Sul percorso Rust, l'**84% della raccolta è il forward della rete in PyTorch** (71 ms a partita, circa 0,8 ms a decisione). Motore, osservazione, descrittori e attraversamenti PyO3 valgono il 16% (14 ms a partita).
- Sul ciclo, l'**aggiornamento** è ora il 71%.
- Il guadagno ×1,57 sul ciclo coincide col tetto stimato in F0 (circa 1,6×). Andare oltre non dipende più dal motore.

## Correttezza
Tutti i campioni qui sotto sono giocati con la build finale. Su questi campioni: zero divergenze inspiegate e zero `NotPorted`.

| prova | campione | esito |
|---|---|---|
| replay di partite PPO tracciate, evento per evento (stato canonico, finestra, menu, azione, scelte interne, estrazioni casuali) | semi 1000001–1000040 | 40/40 identiche |
| partite autonome dai semi, senza decisioni né estrazioni registrate: simple_trade nei due posti | semi 201–500 | 300/300 |
| esempi PPO bit per bit (`collect.play` contro `collect_rs.play`), self-play | semi 151–400, più 59 | 251/251 |
| esempi PPO bit per bit, PPO contro random | semi 1–100 | 100/100 |
| partite autonome simple_trade contro random | semi 1–150 | 150/150 |
| partite autonome random contro random | semi 1–200 | 200/200 |
| **semi tenuti da parte** (usati solo alla fine) | 900001–900040 | vedi sotto |
| casi Gold D59, D59b, D62 (`docs/rust/CONSEGNA1.md`) | 3 posizioni | tracce identiche |
| `pytest tests/rust` (carica davvero l'estensione) | 15 test | verdi |
| suite Python completa (`pytest -q`, golden comprese, con `tests/rust`) | 1.965 test | verdi |
| **checkpoint allenato `ckpt_020032.pt`, esempi PPO bit per bit, sul Mac** | semi 1–20 | **20/20** |
| ciclo PPO col pool, hash di esempi e pesi dopo l'aggiornamento (`parita_ciclo.py`) | 3 cicli × 64 partite | identici |

Esempi PPO bit per bit significa che coincidono `x`, `q`, `src`, `ctx`, `otype`, `ocards`, `ofeats`, `a`, `logp`, `v`, `seat` e `turn` di ogni esempio, oltre a esito, turni e conteggi.

Semi tenuti da parte (900001–900040, mai usati prima), build finale; risultati in `docs/rust/misure/tenuti_*.json`:

| prova | esito |
|---|---|
| autonome simple_trade contro simple_trade | 40/40 identiche |
| autonome random contro random | 40/40 identiche |
| esempi PPO bit per bit, self-play | 40/40 |
| esempi PPO bit per bit, PPO contro simple_trade | 40/40 |
| replay tracciato di partite PPO self-play | 40/40 identiche |

Prima della build finale, le stesse prove avevano coperto:
- 400 partite random contro random;
- 360 partite simple_trade contro random, nei due ordini;
- 100 partite PPO contro simple_trade e 100 contro random;
- il replay di 40 partite PPO contro simple_trade.

Tutte erano identiche, a parte i due errori Rust elencati sotto.

### Divergenze trovate e risolte
Le prime tre erano errori del porting Rust; la quarta un errore Python dimostrato. Ognuna ha la sua posizione minima riproducibile; i semi delle prime tre sono nei test di `tests/rust/test_parita.py`.

1. **Ordine delle chiavi del dump** (prima consegna). Rust ordinava alfabeticamente i campi del dump, Python li tiene nell'ordine di dichiarazione. Cambiava la numerazione canonica delle copie, cioè il confronto, non la partita. Ora il dump usa `preserve_order`.
2. **`cleanup_hidden_cards`** (seme 3, simple_trade). Python chiama `bf.control()`, che registra il controllo del campo, solo dentro la comprensione sulle carte coperte, cioè solo se ce ne sono. Rust lo chiamava su ogni campo e azzerava il controllo di un campo appena svuotato da un Gust.
3. **Copia di dichiarazione** (seme 59 PPO e seme 79 simple_trade). In Python `_declare_choices` gioca su un `GameLoop` nuovo, con `_choices_noted` falso. Rust clonava il loop intero. Su una giocata dalla discarica (Punch First), DEFLECT di Vex Apathetic veniva così ignorato e il bersaglio offerto in più.

4. **Contesto `made` di `PPOAgent.inner`** (errore Python, trovato sui cicli del Mac). La chiave di "scelte già fatte in questa domanda" era `(id(loop), kind, id(source))`. Una copia di dichiarazione liberata poteva lasciare il suo indirizzo alla copia successiva, che contava come lo stesso loop: `made` 1 invece di 0. Il contesto dipendeva così dalla storia della memoria del processo, cioè da quali partite erano state giocate prima nel worker e da quanti worker c'erano.
   - Nel riscaldamento del ciclo: 1 esempio su 6.232, `ctx` [0.5, 0.25, 0, 1] in Python e [0.5, 0, 0, 1] in Rust, e da lì `v`, `adv`, `ret` e l'aggiornamento.
   - Posizione minima e test che fallisce a `6427b90`: `tests/test_ppo_many_key.py` (commit `9275f8f`).
   - Fix separato (commit `f8a50e4`): la chiave tiene gli oggetti stessi, confrontati con `is`. È la semantica del `loop_id` unico di Rust; Rust non cambia.
   - Il codice è invariato su questo punto da `6427b90`: per avere esempi indipendenti dalla memoria il fix va portato sul ramo dei training. Non tocca le regole.

Nessun caso di regole ambigue è emerso in questo incarico. Le deviazioni note (D59, D62, Switcheroo) sono riprodotte come sono a `6427b90`. D71 resta una proposta d'audit separata.

## Copertura
`docs/rust/INVENTARIO_EK.md` copre 46 carte, 64 effetti e 34 verbi:
- tutti i verbi delle carte che entrano in partita hanno un handler Rust (25) o sono marcatori letti dal motore (5);
- 4 verbi appartengono a carte di sideboard che nelle partite non entrano: `counter_spell` (Abandon), `kill_gear` (Acceptable Losses, An Offer You Can't Refuse), `prevent_spell_damage_this_turn` (Unyielding Spirit), `banish_self_and_gear` (Ravenbloom Prefect). Non sono portati e darebbero `NotPorted`.

Le partite random contro random sono la copertura più larga: provano qualunque azione legale, comprese giocate nascoste, Switcheroo, Zed, equipaggiamenti e abilità di Gold.

## Prova con il checkpoint allenato
Fatta sul Mac il 23/11 con `scripts/rust/confronto_mac.command`: parità degli esempi 20/20, poi le misure in apertura. Lo script esegue in sequenza:
1. la compilazione;
2. `pytest tests/rust`;
3. la parità degli esempi con il checkpoint su 20 semi;
4. la raccolta su un core (self-play e contro simple_trade);
5. il ciclo PPO completo, con i motori alternati.

```bash
bash scripts/rust/confronto_mac.command runs/rengar/ekr_s8/ckpt_020032.pt
```

Dal worktree del ramo, con il checkpoint nel checkout dei training: `bash scripts/rust/confronto_mac.command ../rbsim/runs/rengar/ekr_s8/ckpt_020032.pt`. `SOLO_CICLO=1` ripete solo il ciclo.

## Comandi esatti

```bash
# build e verifica
cd rust/rbsim-py && maturin develop --release && cd ../..
python -m pytest -q tests/rust
# correttezza
python scripts/rust/diff_trace.py --semi 1000001-1000040 --modo self
python scripts/rust/autonome.py --semi 201-500 --agenti simple_trade simple_trade
python scripts/rust/parita_ppo.py --semi 151-400
python scripts/rust/autonome.py --semi 900001-900040 --agenti random random
python scripts/rust/parita_ppo.py --semi 900001-900040 --avversario simple_trade
# misure
taskset -c 2 python scripts/rust/bench_raccolta.py --semi 1-60 --out docs/rust/misure/raccolta_un_core_self.json
python scripts/rust/bench_ppo_ciclo.py --cicli 3 --workers 4 --seme 1 --motore python   # poi rust, alternando
python scripts/rust/parita_ciclo.py --motore python --cicli 3   # poi --motore rust: stessi hash
# training
python scripts/ppo.py --mazzi ek --motore rust ...
```

## Commit
- `a6bedbd`: misure F0.
- `7c899e0`, `3e5749b`, `45414de`: strumenti di confronto, motore, replay 20/20.
- `5e44d34`: consegna Gold.
- `066af0d`: agenti Rust, osservazione, PPO su Rust, correzioni.
- `f379c75` e seguenti: inventario, test, misure.
- `4515179`: script di misura compatibili con macOS (spawn).
- `9275f8f`, `f8a50e4`: test e fix Python del contesto `made`.

## Cosa vale fare dopo
1. **Arena su Rust**: il pozzo di ore più grande, visto che le arene costano circa 6 volte una tappa PPO.
   - Quasi tutto il lavoro della ricerca (copie, `determinize`, legali, applicazione) è motore. L'87% in F0 era motore e ricerca.
   - Il guadagno atteso per iterazione è grande, ma si converte in ore solo abbassando il budget, dopo una prova di forza a posti scambiati con un criterio dichiarato prima.
   - Mancano la copia durante una scelta pendente con continuazione e il `priors` sull'intero menu.
2. **Ciclo PPO oltre ×1,3 sul Mac** (×1,6 sul container). Il motore non è più il collo di bottiglia. Contano invece:
   - l'aggiornamento (80% del ciclo Rust sul Mac);
   - il forward a batch 1 (80% della raccolta Rust sul Mac, 84% sul container).

   Due possibilità: sovrapporre raccolta e aggiornamento, oppure raggruppare i forward di più partite. Entrambe cambiano la numerica o l'ordine rispetto a oggi, e vanno decise a parte.
3. **Rengar, poi Ivern e Sett**, con lo stesso metodo: inventario, porting, replay, partite autonome, parità degli esempi. Rengar serve anche al mix `ekr`.
