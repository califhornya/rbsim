# Motore Rust (porting, primo traguardo EK)

Riferimento: il motore Python a `6427b90`, che resta la verità e non si modifica.
Rust ne è una traduzione fedele, funzione per funzione, deviazioni note comprese (D59, D62, Switcheroo).
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

### Errori
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

## Misure
- `scripts/rust/bench_raccolta.py`: raccolta su un core in ordine alternato. Separa il tempo della rete dal resto.
- `scripts/rust/bench_ppo_ciclo.py --motore python|rust`: il ciclo PPO completo.
- `scripts/rust/confronto_mac.command`: tutto in sequenza sul Mac, con il checkpoint.

I risultati vanno in `docs/rust/misure/`. Il resoconto è in `docs/rust/RAPPORTO_EK.md`.

## Non ancora portato
- Gli altri mazzi.
- I verbi delle carte di sideboard EK: `counter_spell`, `kill_gear`, `prevent_spell_damage_this_turn`, `banish_self_and_gear`. Non entrano nelle partite.
- Il bot a mano (`HandwrittenAgent`) e la ricerca dell'arena.
