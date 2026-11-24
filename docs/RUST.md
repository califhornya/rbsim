# Motore Rust (porting, primo traguardo EK)

Riferimento: il motore Python a `6427b90`, congelato il 24/11 (agente PPO: quello con `f8a50e4`).
Rust ne è una traduzione fedele, funzione per funzione, deviazioni note comprese (D59, D62, Switcheroo).
Il doppio fix (Python + Rust) è finito con la consegna EK: un difetto nuovo si corregge una volta, in Rust,
secondo la procedura di `docs/audit/AUDIT.md` ("The Python engine is frozen").
Ogni run registra in `provenienza.jsonl` regole, commit, motore di ciascun matchup, liste (per contenuto),
registro delle carte e checkpoint (`riftbound/provenienza.py`). Le liste EK si riconoscono dal contenuto.
Perimetro attuale: Evelynn contro Kha'Zix, con i mazzi competitivi e i rispettivi campi, leggende e token.
Il motore Rust si sceglie in modo esplicito. Il default resta Python.

## Costruire e verificare

```bash
uv pip install maturin
cd rust/rbsim-py && maturin develop --release && cd ../..
python -m pytest -q tests/rust
```

I test in `tests/rust` caricano davvero `riftbound_rs`. Se l'estensione manca falliscono, non vengono saltati.

## Usarlo
- Training PPO: `python scripts/ppo.py --mazzi ek --motore rust ...`.
  - Le partite Evelynn–Kha'Zix vanno su Rust.
  - Gli altri matchup e le partite contro il bot a mano restano su Python, come dichiarato all'avvio.
  - L'aggiornamento della rete non cambia.
- In codice: `riftbound.rs.collect_rs.play` ha la stessa firma e lo stesso ritorno di `riftbound.ai.ppo.collect.play`.

## Contratti

### Stato e copie
- Gli oggetti Python con identità diventano indici in arene:
  - `CardId` per le carte;
  - `UnitId` per le unità in gioco;
  - `GearId` per gli equipaggiamenti schierati;
  - l'indice nel vettore per i campi di battaglia.

  Le arene non riusano gli indici, quindi `is` diventa uguaglianza di id.
- Una copia del gioco è `Clone` e la mappa fra copia e originale è l'identità degli id.
- La copia di una dichiarazione (`_declare_choices`) è, come in Python, un loop nuovo su una copia dello stato: lo stato del loop parte azzerato (`_choices_noted`, `_replay`, `_in_many`, ...). I giocatori con `decide_mode` lo ricevono tramite `_ModeAsker`.
- `bf.control()` registra il controllo e quindi modifica lo stato. Rust lo chiama negli stessi punti di Python, compresa l'osservazione dell'agente PPO.

### Casualità
- `rng::PyRandom` è un MT19937 identico a `random.Random` (`seed`, `getrandbits`, `_randbelow`, `shuffle`, `choice`, `random`).
- La partita consuma gli stessi numeri nello stesso ordine.
- Gli agenti hanno generatori propri:
  - `random` usa un MT con seme `seed*2 + (posto == B)`;
  - il PPO usa il `torch.Generator` di Python.

### Agenti e scelte
- Il trait `Agent` ricalca `decide_*` e `inner`. `has(metodo)` corrisponde a `hasattr` in Python.
- Il chooser del loop è il port di `PPOChooser` (`SideChooser`): ogni scelta va all'`inner` dell'agente del lato che sceglie. Gli agenti sono quelli del gioco reale, anche quando si sceglie su una copia di dichiarazione.
- Agenti Rust: `random`, `simple_trade` (con l'aiuto al pagamento delle abilità Add di `base_agent`) e PPO.

### Confine PPO
Rust costruisce la domanda, Python decide.
- Rust prepara osservazione, codifica, descrittori delle opzioni, contesto, domanda e sorgente.
- L'osservazione e il turno vengono sempre dal gioco reale, anche su una copia di dichiarazione.
- `AskPPO` (`riftbound/rs/agent_rs.py`) fa ciò che fa `PPOAgent._ask`: forward, campionamento col generatore dell'agente e record.
- Con meno di due opzioni non c'è chiamata né estrazione.
- I record sono identici bit per bit a quelli di Python: `x`, `q`, `src`, `ctx`, `otype`, `ocards`, `ofeats`, `a`, `logp`, `v`, `seat`, `turn`.
- Il contesto `made` (scelte già fatte nella stessa domanda) ha come chiave il loop, il tipo di scelta e la sorgente: in Rust un `loop_id` unico, in Python gli oggetti stessi (fix `f8a50e4`; prima `id()`, che dipendeva dal riuso degli indirizzi).
- Verifica del ciclo intero, col pool e l'aggiornamento: `scripts/rust/parita_ciclo.py --motore python|rust` dà gli stessi hash di esempi e pesi a ogni ciclo.

#### Ricerca dell'arena (tappa A)
- `rbsim-core/src/search.rs` è il port di `net_mcts.py` + `handwritten.py` + `ppo/prior_bot.py` come li usa
  l'arena: backup "best", la mossa col Q più alto, `table_value` alle foglie, nessuna esplorazione né record.
- Copie: `search_copy` = `gs.clone()` senza agenti, generatore nuovo dal seme dell'agente, `determinize`
  dal punto di vista del giocatore, loop nuovo. La ripresa da una scelta pendente usa `segment` (lo stato
  all'ultima decisione principale) e il `journal` del loop reale (`replay_segment`, `Cursor`).
- Le scelte sul loop reale passano da un solo chooser `Layers` (py: `_Plan` → `_Fallback` → `PPOChooser`),
  messo sopra quello che c'era alla prima decisione di un agente di ricerca.
- Le chiavi delle scelte sono `(tipo, carta sorgente, etichetta)` come `_choice_keys`. Dove Python usa il
  `repr` di un oggetto (trigger, equipaggiamenti, carte coperte) Rust costruisce un testo diverso con la stessa
  uguaglianza: le carte per `uuid` (nuovo a ogni creazione, conservato dalle copie, come `uuid4`). Su una copia
  di dichiarazione `replay_values` etichetta le opzioni sul loop reale, come Python (unità non trovate,
  campo di battaglia → `ValueError`).
- Prior PPO: Rust costruisce osservazione, descrittori del menu e contesto; Python (`arena_rs.make_probs`)
  fa forward e softmax.
- Uso: `arena_mazzi.py --motore rust` (i matchup coperti, riconosciuti dal contenuto delle liste, su Rust;
  gli altri su Python); in codice `riftbound.rs.arena_rs.game(task)` = `arena_bot._game(task)`.
- Chiavi di ripresa dell'arena: checkpoint (percorso e hash), budget, motore, regole.

## Errori
- Un ramo non portato dà `EngineError::NotPorted{dove, cosa}`, che risale sempre.
- Le eccezioni che Python ignora (`except Exception` nelle dichiarazioni, `_Ignored`) sono ignorate allo stesso modo.

## Verifiche

| Script | Cosa confronta |
|---|---|
| `scripts/rust/diff_trace.py --semi A-B --modo self\|simple_trade` | Replay di partite Python tracciate. Confronto evento per evento (stato canonico, finestra, menu, azione, scelte, estrazioni), fino alla prima differenza. |
| `scripts/rust/autonome.py --semi A-B --agenti X Y` | Partite autonome dai semi, senza nulla registrato. |
| `scripts/rust/parita_ppo.py --semi A-B [--avversario X] [--init ckpt]` | Esempi PPO bit per bit. |
| `scripts/rust/consegna1.py` | Casi Gold D59, D59b e D62. |
| `scripts/rust/inventario.py` | Carte, verbi e stato del porting (`docs/rust/INVENTARIO_EK.md`). |
| `scripts/rust/arena_parita.py --semi A-B --bot mano\|prior [--iterazioni 50] [--ckpt f.pt]` | Partite dell'arena a lavoro fisso: traccia della partita reale e ogni ricerca (menu, prior, visite, Q e W, mossa, nodi, mulligan). |

## Misure
- `scripts/rust/bench_raccolta.py`: raccolta su un core in ordine alternato. Separa il tempo della rete dal resto.
- `scripts/rust/bench_ppo_ciclo.py --motore python|rust`: il ciclo PPO completo.
- `scripts/rust/bench_arena_fisso.py --motore python|rust --iterazioni 50`: l'arena a lavoro fisso, tempo per partita.
- `scripts/rust/confronto_mac.command`: tutto in sequenza sul Mac, con il checkpoint.

I risultati vanno in `docs/rust/misure/`. Il resoconto è in `docs/rust/RAPPORTO_EK.md`.

## Non ancora portato
- Gli altri mazzi.
- I verbi delle carte di sideboard EK: `counter_spell`, `kill_gear`, `prevent_spell_damage_this_turn`, `banish_self_and_gear`. Non entrano nelle partite.
- Gli altri bot (`HorizonAgent`, `NetAgent`, il coach) e l'esplorazione della ricerca (rumore, temperatura).
