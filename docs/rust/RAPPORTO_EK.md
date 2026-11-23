# Rapporto EK: porting del motore in Rust, primo matchup

Ramo `claude/peaceful-lamport-gynyab`. Riferimento Python: `6427b90`, non modificato.

## In breve: minuti per lo stesso carico
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
  - Dal ciclo 1 in poi le partite cambiano anche fra due esecuzioni Python, perché l'aggiornamento con 4 thread torch non è riproducibile bit per bit.
  - Il confronto dal ciclo 1 in poi è quindi a pari carico atteso.
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
| **semi tenuti da parte** (usati solo alla fine) | 900001–900040 | vedi sotto |
| casi Gold D59, D59b, D62 (`docs/rust/CONSEGNA1.md`) | 3 posizioni | tracce identiche |
| `pytest tests/rust` (carica davvero l'estensione) | 15 test | verdi |

Esempi PPO bit per bit significa che coincidono `x`, `q`, `src`, `ctx`, `otype`, `ocards`, `ofeats`, `a`, `logp`, `v`, `seat` e `turn` di ogni esempio, oltre a esito, turni e conteggi.

Semi tenuti da parte (900001–900040, mai usati prima), build finale; risultati in `docs/rust/misure/tenuti_*.json`:

| prova | esito |
|---|---|
| autonome simple_trade contro simple_trade | 40/40 identiche |
| autonome random contro random | 40/40 identiche |
| esempi PPO bit per bit, self-play | 40/40 |
| esempi PPO bit per bit, PPO contro simple_trade | 40/40 |
| replay tracciato di partite PPO self-play | REPLAY_TENUTI |

Prima della build finale, le stesse prove avevano coperto:
- 400 partite random contro random;
- 360 partite simple_trade contro random, nei due ordini;
- 100 partite PPO contro simple_trade e 100 contro random;
- il replay di 40 partite PPO contro simple_trade.

Tutte erano identiche, a parte i due errori Rust elencati sotto.

### Divergenze trovate e risolte
Tutte erano errori del porting Rust, non del riferimento Python. Ognuna ha la sua posizione minima riproducibile, e il seme corrispondente è nei test di `tests/rust/test_parita.py`.

1. **Ordine delle chiavi del dump** (prima consegna). Rust ordinava alfabeticamente i campi del dump, Python li tiene nell'ordine di dichiarazione. Cambiava la numerazione canonica delle copie, cioè il confronto, non la partita. Ora il dump usa `preserve_order`.
2. **`cleanup_hidden_cards`** (seme 3, simple_trade). Python chiama `bf.control()`, che registra il controllo del campo, solo dentro la comprensione sulle carte coperte, cioè solo se ce ne sono. Rust lo chiamava su ogni campo e azzerava il controllo di un campo appena svuotato da un Gust.
3. **Copia di dichiarazione** (seme 59 PPO e seme 79 simple_trade). In Python `_declare_choices` gioca su un `GameLoop` nuovo, con `_choices_noted` falso. Rust clonava il loop intero. Su una giocata dalla discarica (Punch First), DEFLECT di Vex Apathetic veniva così ignorato e il bersaglio offerto in più.

Nessun caso di regole ambigue e nessun errore Python dimostrabile è emerso in questo incarico. Le deviazioni note (D59, D62, Switcheroo) sono riprodotte come sono a `6427b90`. D71 resta una proposta d'audit separata.

## Copertura
`docs/rust/INVENTARIO_EK.md` copre 46 carte, 64 effetti e 34 verbi:
- tutti i verbi delle carte che entrano in partita hanno un handler Rust (25) o sono marcatori letti dal motore (5);
- 4 verbi appartengono a carte di sideboard che nelle partite non entrano: `counter_spell` (Abandon), `kill_gear` (Acceptable Losses, An Offer You Can't Refuse), `prevent_spell_damage_this_turn` (Unyielding Spirit), `banish_self_and_gear` (Ravenbloom Prefect). Non sono portati e darebbero `NotPorted`.

Le partite random contro random sono la copertura più larga: provano qualunque azione legale, comprese giocate nascoste, Switcheroo, Zed, equipaggiamenti e abilità di Gold.

## Prova con il checkpoint allenato
`ckpt_020032.pt` non è nel container. La prova col checkpoint è pronta in `scripts/rust/confronto_mac.command`, che sul Mac esegue in sequenza:
1. la compilazione;
2. `pytest tests/rust`;
3. la parità degli esempi con il checkpoint su 20 semi;
4. la raccolta su un core (self-play e contro simple_trade);
5. il ciclo PPO completo, con i motori alternati.

```bash
bash scripts/rust/confronto_mac.command runs/rengar/ekr_s8/ckpt_020032.pt
```

In alternativa il checkpoint si può caricare in chat e la prova gira qui. Finché non c'è, l'ultima condizione del traguardo EK resta aperta.

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
# training
python scripts/ppo.py --mazzi ek --motore rust ...
```

## Commit
- `a6bedbd`: misure F0.
- `7c899e0`, `3e5749b`, `45414de`: strumenti di confronto, motore, replay 20/20.
- `5e44d34`: consegna Gold.
- `066af0d`: agenti Rust, osservazione, PPO su Rust, correzioni.
- `f379c75` e seguenti: inventario, test, misure.

## Cosa vale fare dopo
1. **Arena su Rust**: il pozzo di ore più grande, visto che le arene costano circa 6 volte una tappa PPO.
   - Quasi tutto il lavoro della ricerca (copie, `determinize`, legali, applicazione) è motore. L'87% in F0 era motore e ricerca.
   - Il guadagno atteso per iterazione è grande, ma si converte in ore solo abbassando il budget, dopo una prova di forza a posti scambiati con un criterio dichiarato prima.
   - Mancano la copia durante una scelta pendente con continuazione e il `priors` sull'intero menu.
2. **Ciclo PPO oltre ×1,6.** Il motore non è più il collo di bottiglia. Contano invece:
   - l'aggiornamento (71% del ciclo);
   - il forward a batch 1 (84% della raccolta Rust).

   Due possibilità: sovrapporre raccolta e aggiornamento, oppure raggruppare i forward di più partite. Entrambe cambiano la numerica o l'ordine rispetto a oggi, e vanno decise a parte.
3. **Rengar, poi Ivern e Sett**, con lo stesso metodo: inventario, porting, replay, partite autonome, parità degli esempi. Rengar serve anche al mix `ekr`.
