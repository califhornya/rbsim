# Note di lavoro del porting (per riprendere dopo una pausa)

Riferimento: Python a `6427b90`, in sola lettura anche in `/home/user/rbsim-ref` (worktree).
Il comportamento è identico al riferimento, deviazioni comprese (D59, D62, Switcheroo).

## Convenzioni Rust (rbsim-core)
- Un oggetto Python con identità diventa un indice in un'arena di `Game`:
  - `CardId(u32)` → `gs.cards: Vec<Card>`;
  - `UnitId(u32)` → `gs.units: Vec<Unit>` (UnitInPlay);
  - `GearId(u32)` → `gs.dgear: Vec<DGear>` (DeployedGear);
  - un `Battlefield` è l'indice nel vettore `gs.battlefields`.

  Le arene crescono e basta, senza riuso: `is` diventa uguaglianza di id. `Clone` del `Game` copia tutto, e la mappa fra copie (`_mapped`) è l'identità.
- Ogni funzione Rust porta un commento `// py: loop.py <nome>` col nome del metodo Python.
- I rami raggiungibili solo con carte fuori dal perimetro diventano `not_ported!("dove", "cosa")`, che produce `Err(Engine::NotPorted)`, un errore identificabile.
- I `params` degli effetti restano `serde_json::Value`, come i dict Python, letti con gli stessi default.
- Gli attributi dinamici delle carte (`card._kicker_paid`, ...) sono campi di `Card` con default. Quelli visti in EK: `_attached_to`, `_attached_turn`, `_chosen_card`, `_graceful_from`, `_graceful_owed`, `_graceful_prepaid`, `_granted_repeat`, `_kicker_paid`, `_owner`, `_play_pending`, `_played_from`, `_power_paid`, `_repeat_extra`, `_repeat_paid`, `_showed_off`, `_shown`, `_spent`, `is_token`, `tapped`.
- Generatore: `rng::PyRandom` (MT19937 identico a CPython, verificato).
- Copie: `_declare_choices` e `_choices_on_board_as_played` usano `deepcopy`; in Rust si fa `clone()` del `Game` con gli agenti a None. Le eccezioni nella dichiarazione sono ingoiate come in Python, tranne `NotPorted`, che risale sempre.

## Ponte Python (riftbound/rs)
- `canon.py`: dump canonico. Gli id canonici sono assegnati alla prima vista e dipendono dalla storia dei dump, quindi i due motori vanno confrontati con lo stesso calendario di dump.
- `trace_py.py`: traccia, con test che non cambia la partita.

## Fatto e da fare
Vedi STATO.md. Copertura per funzione: `scripts/rust/copertura_funzioni.py runs/rust_f3/coverage.json`.
