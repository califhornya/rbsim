# Motore Rust (porting: EK, poi Rengar)

Riferimento: il motore Python a `6427b90`, congelato il 24/11 (agente PPO: quello con `f8a50e4`).
Rust ne è una traduzione fedele, funzione per funzione, deviazioni note comprese (D59, D62, Switcheroo).
Il doppio fix (Python + Rust) è finito con la consegna EK: un difetto nuovo si corregge una volta, in Rust,
secondo la procedura di `docs/audit/AUDIT.md` ("The Python engine is frozen").
Ogni run registra in `provenienza.jsonl` regole, commit, motore di ciascun matchup, liste (per contenuto),
registro delle carte e checkpoint (`riftbound/provenienza.py`). Le liste si riconoscono dal contenuto.
Perimetro attuale (`riftbound/rs/arena_rs.COPERTI`): EK, ER, KR nei due posti, cioè le liste competitive di
Evelynn, Kha'Zix e Rengar fra loro, con campi, leggende e token; le sideboard di Rengar ed EK hanno i loro verbi
(non entrano nelle partite di training: si provano con le liste variate di `riftbound/rs/mazzi.py`).
Il motore Rust si sceglie in modo esplicito. Il default resta Python.

## Costruire e verificare

```bash
uv pip install maturin
cd rust/rbsim-py && maturin develop --release && cd ../..
python -m pytest -q tests/rust
```

I test in `tests/rust` caricano davvero `riftbound_rs`. Se l'estensione manca falliscono, non vengono saltati.

## Usarlo
- Training PPO: `python scripts/ppo.py --mazzi ekr --motore rust ...`.
  - Le partite dei matchup coperti (EK, ER, KR) vanno su Rust (`_motore`, liste riconosciute dal contenuto).
  - Gli altri matchup e le partite contro il bot a mano restano su Python, come dichiarato all'avvio.
  - L'aggiornamento della rete non cambia.
- In codice: `riftbound.rs.collect_rs.play` ha la stessa firma e lo stesso ritorno di `riftbound.ai.ppo.collect.play`.

## Profili delle regole

Decisione del 25/11 (Astra, Matteo): un unico selettore, scelto all'avvio della partita e tenuto dal suo
registro, quindi valido per i due giocatori, le copie di ricerca, i worker e i replay.
- `6427b90` (default): identico a Python, deviazioni comprese. Le verifiche di parità lo fissano in modo esplicito
  (`scripts/rust/*.py`, `tests/rust/conftest.py`).
- `6427b90+D72-D76`: D72-D76 corretti (`docs/audit/AUDIT.md`). Codice dietro `reg.regole.corrette()`; per D74 e
  l'`exclude_self` di D75 una correzione dati versionata (`D72-D76/1`, `registry.rs: correggi_dati`) applicata al
  caricamento: `rust/data/registry.json` resta l'esportazione riproducibile di Python. Resta com'è: le run già
  allenate con lui restano riproducibili.
- `6427b90+D72-D77`: il precedente più D77 (decisione del 25/11): dopo uno spostamento normale che non resta in
  sospeso (`pending_move` vuoto) gli showdown messi in attesa dai suoi inneschi partono subito, come dopo ogni altra
  azione (`lp_action.rs`, dietro `reg.regole.d77()`). Stessi dati carte e stessa impronta del registro di
  `6427b90+D72-D76` (`corrette()` vale per entrambi). Profilo da usare per run e arene nuove.
- Scelta: `--regole` in `scripts/ppo.py` e `scripts/diag/arena_mazzi.py` (variabile `RBSIM_REGOLE`, ereditata dai
  worker); in codice `rust_bridge.build(..., regole=...)`, `rust_bridge.registry(regole)` (uno per thread e profilo).
- Coi profili corretti le partite di training e dell'arena devono giocare su Rust (controllo prima del lancio); un
  pannello diagnostico su Python riporta le regole storiche. Per allenare sul nuovo profilo `--init` in una nuova
  cartella: una run non cambia profilo.
- Provenienza: `regole` (il profilo), `regole_partite` (quelle di ciascun matchup), `registro.rust_effettivo`
  (l'impronta del registro corretto) e `correzione_dati`; le righe dell'arena e la chiave di ripresa hanno le regole
  del matchup (una riga senza = `6427b90`); accanto a ogni `ckpt_*.pt` di `ppo.py` un `ckpt_*.provenienza.json`.
- `riftbound_rs.correzioni()`: quante volte D72..D77 hanno cambiato qualcosa in questo thread, ricerca compresa
  (D77 solo sul suo profilo); sui profili corretti ogni decisione della traccia ne ha l'istantanea.
  `scripts/rust/confronto_regole.py` gioca le stesse partite su `6427b90` e `6427b90+D72-D76` e spiega la prima
  differenza.

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

### Posto umano e traccia in diretta
- `Game.set_human_agent(seat, ask)`: ogni decisione del posto (mulligan, turn_action, reaction, showdown_action, anche con una sola opzione) e ogni scelta nella mossa (tutti i `choice`, più `decide_optional`, `decide_mode`, `decide_predict_recycle`) chiama `ask(event_json: str)`. L'evento è quello che la traccia registra (stesse funzioni di `trace.rs`, stesse chiavi, stato prima della risposta) senza i campi della risposta (`action`/`index`, `chosen`/`by`, `out`); la decisione porta in più, solo per `ask`, `actions` (le mosse del menu in forma `action`). Imposta il side chooser se il gioco non ne ha uno; da chiamare prima di `trace_on()`.
- La risposta è un oggetto Python (non JSON) della forma del campo mancante: decisione = int indice in `menu`; scelta = int indice in `options_raw`; mulligan = lista di al più 2 indici distinti della mano; `decide_optional` e `decide_predict_recycle` = bool; `decide_mode` = int in `0..n` o `None`. Per una decisione vale anche la lista `[tipo, indice, corsia(, dst)]` (il campo `action` della traccia), giocata così com'è anche fuori dal menu: serve a bot e replay (`simple_trade` gioca azioni fuori dal menu), la pagina umana risponde con l'indice. Una risposta non valida (bool al posto di int, tipo sbagliato, indice fuori range) alza `ValueError` da `start()` / `run_segment()`.
- `set_human_agent(seat, ask, payments=False)`, con `payments=True` ("Come paghi?" della pagina, port di `coach.payment_options`, `gold_only_plays`, `CoachAgent._coached/_gold_step`, `CoachLoop`; `rbsim-core/src/payment.rs`, `human.rs`): nell'evento di ogni decisione compaiono `pay` (una voce per mossa del menu: `null`, o, dove Python offrirebbe una scelta, cioè con più di un modo, la lista dei modi, quello del motore per primo) e `gold_only` (le giocate pagabili solo con i Gold; con una mossa sola nel menu, come per Python, `pay` è tutto `null` e `gold_only` vuota; `[{"action": [tipo, indice, corsia(, dst)], "ways": [...]}]`, anche con un modo solo). Un modo è `{"golds": n, "gold_domain": "FURY".. | null, "prefer": dominio | null, "recycled": [[dominio, rune], ...]}`: gli stessi campi di Python senza il `text` italiano, che costruisce Python; `recycled` = le rune riciclate per dominio, nell'ordine del `rune_pool` (come la tupla di Python), non i riferimenti alle singole rune. Stessi ordine, dedup e regola "non più rune del minimo" di Python. Calcolati su copie del gioco dentro Rust: il gioco non si tocca.
- Con `payments=True` una decisione accetta anche `{"index": i, "via": w}` (mossa `i` del menu pagata col modo `w` di `pay[i]`, indice nella lista) e `{"solo_gold": j, "via": w}` (`gold_only[j]` col suo modo `w`). Un modo senza Gold imposta la preferenza `recycle_first` per quella mossa; uno con Gold: il posto esegue da sé gli step, un Gold per decisione (ognuno una decisione della traccia, senza `ask`; la sua domanda "quale dominio" è risposta dal posto), poi la mossa con la preferenza, come `_gold_plan`/`_gold_step`. Una risposta `via` senza `payments=True`, un `via` fuori dalla lista o per una mossa senza scelta alza `ValueError`. Se il piano non è più possibile la decisione si richiede (un evento nuovo).
- Gancio del motore: `Game.recycle_first: Option<(Side, Domain)>` (py: `CoachLoop.recycle_first`), onorato in `pay_card_cost` (Power senza dominio proprio: `Player.pay_first` sostituisce `pay_power_of` per quella spesa) e in `pay_generic_power`, e consumato alla prima spesa di quel lato. Il posto umano lo azzera a ogni sua decisione. Spento (default) il motore è identico bit per bit, per ogni altro agente.
- `trace_on(watch=None)`: con `watch`, ogni evento registrato va anche a `watch(event_json: str)`, completo (risposta compresa), nello stesso ordine di `events()`.
- Un'eccezione di `ask` o `watch` (anche una `BaseException`) esce da `start()` / `run_segment()` come lo stesso oggetto; il gioco è finito, se ne costruisce un altro. Dentro i callback non si usa il `Game`.
- `correzioni` (profili D72+) è il contatore al momento della registrazione, dopo il lavoro dell'agente: la domanda a un umano lo porta com'era prima della risposta.

### Pagina coach su Rust (fase 4)
- `scripts/coach.py --motore rust|python` (default rust), `--regole` (default `6427b90+D72-D77`), `--iterazioni`.
  Una partita fra due mazzi di `arena_rs.COPERTI` contro il campione o `simple_trade` gira su Rust con quel profilo
  (`riftbound/ai/coach_rs.py`, `RustGame`); il resto (altri mazzi, `--net` con i consigli, "La rete", `--motore python`)
  gira su Python con `6427b90`. `state()["regole"]`/`["motore"]` e le righe di `games.jsonl` dicono cosa si è giocato.
- Il posto di Matteo è `set_human_agent(posto, ask, payments=True)` + `trace_on(watch)`: `ask` costruisce la stessa domanda
  della pagina Python (testi e tavolo da `vista_rs` e dalle funzioni di `coach.py`; "Come paghi?" con `payment_text`),
  risponde da sé dove Python non chiede (una sola opzione, `decide_*`, scelte fuori da una mossa di Matteo) e traduce la
  risposta (indice; `{"index","via"}`; `{"solo_gold","via"}`); `watch` tiene tavolo, eventi e log durante le mosse dell'avversario.
  Le mosse del menu vengono dal tasto `actions` dell'evento di decisione che riceve `ask` (una `[tipo, indice, corsia(, dst)]`
  per voce, come il campo `action` della traccia; non è nella traccia registrata né in `watch`).
- Il campione su Rust cerca con `iterazioni` FISSE (`set_search_agent(.., budget=None, probs=make_probs(rete))`), non a
  tempo: la partita è determinata da seme e risposte, come serve all'"Annulla l'ultima mossa" (si registrano le risposte
  date a Rust, si ricostruisce la stessa partita e le si rigiocano fino al checkpoint senza chiedere alla pagina; poi
  `_resume` confronta il tavolo). Default N = `coach_rs.ITERAZIONI_CAMPIONE` = **42**: mediana delle iterazioni di una
  ricerca di turno con `search_stats` a `budget=0.03` (il budget Rust promosso uguale a Python a 0,4 s), 6 partite
  ES/EK (semi 1-6, profilo D72-D77, entrambi i posti a cercare; 252 ricerche, per partita 33-61, media 140, max 786).
  Misurata con una `PPONet` di pesi casuali (il checkpoint del campione non è nel container: il costo del forward è lo
  stesso): da rimisurare sul Mac col checkpoint vero.
- Differenze note con la pagina Python (Rust non dà al posto umano le informazioni): "Sett The Boss" chiede sì/no unità per
  unità (il gruppo che muore e l'unità in questione vivono solo dentro `route_deaths`, non nello stato né negli eventi);
  le carte guardate in cima si mostrano con le scelte che seguono (tenere, predire) ma non in "Prendere una delle carte
  guardate?" né in uno sguardo senza scelta (le carte escono dal mazzo dentro l'effetto, `fx_dig`): servirebbe un gancio
  in rbsim-core (`offer_reveal_from_top`, `route_deaths`) che avvisi il posto umano. Il log scrive una scelta una volta
  (i pick di una "fino a N" insieme, `RustGame._logged_choice`).
- Test: `tests/rust/test_coach_rs.py` (partite intere ES/EK/RS, rewind, campione a poche iterazioni, ripiego su Python).

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

Tutti gli script di parità prendono `--matchup XY` (lettere di `riftbound/rs/mazzi.py`: il primo mazzo in A; default
EK; minuscola = la lista con tutta la sideboard nel mazzo, es. `Er`) e `--posti` (anche il matchup rovesciato).

| Script | Cosa confronta |
|---|---|
| `scripts/rust/diff_trace.py --semi A-B --modo self\|simple_trade` | Replay di partite Python tracciate. Confronto evento per evento (stato canonico, finestra, menu, azione, scelte, estrazioni), fino alla prima differenza. |
| `scripts/rust/autonome.py --semi A-B --agenti X Y` | Partite autonome dai semi, senza nulla registrato. |
| `scripts/rust/parita_ppo.py --semi A-B [--avversario X] [--init ckpt]` | Esempi PPO bit per bit. |
| `scripts/rust/consegna1.py` | Casi Gold D59, D59b e D62. |
| `scripts/rust/inventario.py [--liste R --matchup ER KR Er Kr]` | Carte, verbi, condizioni, quantità, trigger e parole chiave, con lo stato del porting e le esecuzioni (`docs/rust/INVENTARIO_EK.md`, `INVENTARIO_RENGAR.md`). |
| `scripts/rust/posizioni_rengar.py [--caso X]` | Posizioni mirate per i rami rari di Rengar (equipaggiamento in base dopo Thrill of the Hunt, gear schierato ucciso, Mech, Seat of Power, Sunken Temple, Acceptable Losses): tracce identiche e ramo eseguito. |
| `scripts/rust/arena_parita.py --semi A-B --bot mano\|prior [--iterazioni 50] [--ckpt f.pt]` | Partite dell'arena a lavoro fisso: traccia della partita reale e ogni ricerca (menu, prior, visite, Q e W, mossa, nodi, mulligan). |
| `scripts/rust/arena_mista.py --ckpt f.pt [--budget-rust 0.03 --budget-python 0.4]` | Arena mista a passo comune: due copie della stessa partita (Python e Rust); chi cerca a tempo passa il conteggio all'altra copia; traccia e ricerche controllate. |
| `scripts/rust/confronto_regole.py --semi A-B --agenti mano mano [--iterazioni 50]` | Le stesse partite in Rust su `6427b90` e su `6427b90+D72-D76`: prima differenza, origine (partita o ricerca) e correzioni scattate. |
| `scripts/rust/arena_mista_riprova.py --righe f.jsonl --seme S --posto-rust A --ckpt f.pt` | Rigioca una partita dell'arena mista coi conteggi registrati, senza cronometro; per la prima ricerca diversa, le simulazioni diverse. |

## Misure
- `scripts/rust/bench_raccolta.py`: raccolta su un core in ordine alternato. Separa il tempo della rete dal resto.
- `scripts/rust/bench_ppo_ciclo.py --motore python|rust`: il ciclo PPO completo.
- `scripts/rust/bench_arena_fisso.py --motore python|rust --iterazioni 50`: l'arena a lavoro fisso, tempo per partita.
- `scripts/rust/confronto_mac.command`: tutto in sequenza sul Mac, con il checkpoint.

I risultati vanno in `docs/rust/misure/`. Il resoconto è in `docs/rust/RAPPORTO_EK.md`.

## Non ancora portato
- Ivern, Sett e il resto del catalogo.
- I verbi delle carte di sideboard EK: `counter_spell`, `prevent_spell_damage_this_turn`, `banish_self_and_gear`; il
  `play_token` di An Offer You Can't Refuse (`it_controller`). Non entrano nelle partite. `kill_gear` è portato (Rengar).
- Gli altri bot (`HorizonAgent`, `NetAgent`; il coach c'è: sopra) e l'esplorazione della ricerca (rumore, temperatura).
