# Rapporto Ivern: il mazzo di Ivern nel motore Rust

Ramo `claude/vibrant-johnson-k8ovzv`, verso `rust`. Riferimento Python: regole `6427b90`, agente PPO con `f8a50e4`
(congelato, `docs/audit/AUDIT.md`). Il motore Python non è stato toccato.

**Tappa Ivern raggiunta.** La lista competitiva di Ivern con la sua sideboard gioca su Rust. Sui matchup EI, KI e RI
nei due posti le partite sono identiche a quelle Python: partite autonome, esempi PPO bit per bit, replay e arena a
lavoro fisso, ricerche comprese. Zero divergenze inspiegate, nessun `NotPorted`. EK, ER e KR restano identici.
EI, KI e RI vanno su Rust nell'arena e nel training (`arena_rs.COPERTI`, `ppo._motore`).

## Cosa è stato portato
Inventario: `docs/rust/INVENTARIO_IVERN.md` (`scripts/rust/inventario.py --liste I --matchup EI KI RI Ei Ki Ri`).
27 carte (mazzo, sideboard, leggenda, campione, tre campi, il token Bird), 35 effetti, 23 verbi. Prima di questa
tappa mancavano:

| Cosa | Carte | Dove in Rust |
|---|---|---|
| verbo `counter_spell` | Defy, Hush, Not So Fast | `effects.rs` `fx_counter_spell`; `effects_core.rs` `counter_targets`, `counterable`, `chose_mine`, `uncounterable`, `has_valid_target` |
| verbo `dig` (e `reveal_and_choose`) | Ivern Nurturer | `effects.rs` `fx_dig`, `note_revealed` |
| abilità riflesse (`_reflexive`) | Ivern Nurturer ("poi, se hai rivelato un Bird, Cat, Dog o Poro, BUFF") | `lp_triggers.rs` `reflexive`; `registry.rs` `EffectSpec::from_dict` |
| verbo `green_father_brush`, token Brush e `brush_swap_back` | Ivern Green Father | `effects.rs`; `lp_hidden.rs` `replace_battlefield`, `set_battlefield_card`, `swap_back_battlefield`, `brush_helps` |
| verbo `heal_unit` | Janna Savior (sideboard) | `effects.rs` |
| verbo `name_spell` e il divieto che ne segue | Fallen Feline | `effects.rs`; `lp_rules.rs` `play_forbidden`; `Card.named_spell` (dump e import) |
| verbo `ready_units` | Raucous Anthem | `effects.rs` `fx_ready_units` |
| passivo `weaker_enemies_no_damage` | Vilemaw (sideboard) | `lp_passives.rs` `recompute_passives` |
| condizioni `has_all_pet_tags`, `played_from_hand`, `undamaged_this_turn`, `you_have_n_or_more_units_here` | Daisy!, Back Off, Affectionate Poro, Trusty Ramhound | `lp_conditions.rs` |
| quantità `n_distinct_tags_among_friendlies` | Daisy!, Friendship | `effects_core.rs` `effect_amount` |

Tutto il resto che Ivern usa era già nel motore. Nota sull'inventario: Vilemaw risultava un "marcatore" letto da
Rust, ma il ricalcolo dei passivi dava `NotPorted`. La colonna "marcatore" dice solo che Python non ha un handler; lo
stato vero lo dicono le partite.

### Due cambiamenti che toccano tutto il motore
1. **Gli elementi della pila hanno un'identità** (`ChainItem.uid`, assegnato da `put_on_chain`). In Python una scelta
   fra elementi della pila (il bersaglio di un counter) è l'oggetto stesso; in Rust `Opt::Chain` era l'indice.
   - Quando la pila si accorcia sotto un counter (un altro counter toglie il bersaglio), l'indice puntava a un altro
     elemento, anche al counter stesso: il dump ricorreva all'infinito (segfault sul seme 5 IE).
   - Ora `Opt::Chain` e `Obj::Chain` portano l'uid; `GameState::chain_pos` ritrova la posizione. Una scelta dichiarata
     il cui elemento non è più sulla pila non è fra le opzioni, come in Python (`_Ignored`).
   - Gli elementi creati dalla copia di dichiarazione dopo la copia sono stranieri (`map_back`).
2. **Le istruzioni create in partita** (`EffectSpec.from_dict`, indice `None`): quelle di un'abilità riflessa.
   `NO_IDX` sta per `None` negli indici (`ix`), anche nel dump e nella chiave "una volta per turno"
   (`(carta, None)`). Il nome canonico è il valore della spec (`json.dumps(asdict, sort_keys=True)`), come
   `canon.spec_ref`: nessuna spec del registro ha trigger `reflexive`.

### Rami tradotti che Ivern non tocca
I verbi sono tradotti per intero, funzione per funzione. Alcuni rami servono solo ad altre carte:
- `counter_spell`: `unless_pays`, `silence`, `return_to_hand` (con FLOW);
- `dig`: `must`, `reveal`, `rest: trash`, i filtri (`target_filter`, `reveal_filter`, `filter`);
- `replace_battlefield`: Baron Pit, `victory_score_plus` (Aspirant's Climb);
- `you_have_n_or_more_units_here`: `with_gear` (Steadfast Outrider).

Si proveranno con le carte che li usano. Danno `NotPorted`: `ready_units` con `amount` ("Ready up to N") e con un
bersaglio diverso da "le tue unità"; `_reflexive` con una spec già fatta o con una condizione; `on_reveal_from_top`
(Nocturne) e `on_revealed` restano come prima.

### Liste con la sideboard
`riftbound/rs/mazzi.py` costruisce la lista di Ivern con tutta la sideboard nel mazzo:
- entrano Disarming Rake ×2, Janna Savior ×2, Vilemaw (unità) e Hush ×2, Salvage ×2, Grand Strategem (magie);
- escono unità e magie di pari ruolo: Stalwart Poro ×2, Mutated Mouser ×2, Trusty Ramhound, Defy ×2, Back Off,
  Friendship, Raucous Anthem. Di ogni carta resta almeno una copia, così restano tutti i tag per Daisy!.

Il file è `tests/rust/mazzi/competitive_ivern_sideboard.json` (`--matchup Ei`).

## Correttezza
Script di parità con `--matchup` e `--posti`; primo giocatore bilanciato (parità del seme); rete PPO `PPONet()` dal
seme 1. Tutte le prove di sviluppo sono sulla build finale del motore (dopo l'ultima correzione è cambiato solo lo
strumento di replay, e i replay sono stati rifatti tutti).

Semi di sviluppo:

| prova | matchup (nei due posti) | esito |
|---|---|---|
| autonome random contro random | EI, KI, RI (semi 1–150), Ei, Ki, Ri (41–150) | 900/900, 660/660 |
| autonome simple_trade contro simple_trade | EI, KI, RI, Ei, Ki, Ri (1–100) | 1.200/1.200 |
| autonome random contro random, regressione | EK, ER, KR, Er, Kr (1–60) | 600/600 |
| esempi PPO bit per bit, self-play | EI, KI, RI (1–60) | 360/360 |
| esempi PPO bit per bit, PPO contro simple_trade | EI, KI, RI (1–60) | 360/360 |
| replay di partite PPO tracciate, self-play e contro simple_trade | EI, KI, RI (1000001–1000040) | 480/480 |
| replay di partite PPO tracciate, regressione | EK, ER (1000001–1000040) | 160/160 |
| arena a 50 iterazioni, bot a mano: traccia e ogni ricerca | EI, KI, RI (40000–40004) | 30/30 |
| arena a 50 iterazioni, bot coi prior: traccia e ogni ricerca | EI, KI, RI (40000–40004) | 30/30 |
| posizioni mirate (`scripts/rust/posizioni_ivern.py`) | 3 posizioni | 3/3, ramo eseguito |
| `pytest tests/rust` | 74 test | verdi |

Rami eseguiti nelle partite intere (contati sul lato Python, 360 partite random e simple_trade sui sei matchup): Brush
messo 4.286 volte e tolto 823, abilità riflessa di Ivern Nurturer 924, Fallen Feline che vieta la magia nominata 387,
Vilemaw che toglie il danno a un nemico 86, `played_from_hand` falso 59 (Back Off giocata nascosta), counter con
un'abilità fra i bersagli 18. I conteggi comprendono le copie di dichiarazione.

Semi tenuti da parte (900001–900040, mai usati prima), build finale; risultati in `docs/rust/misure/tenuti_ivern_*.json`:

| prova | EI | KI | RI | Ei, Ki, Ri (con sideboard) | EK, ER, KR (di nuovo) |
|---|---|---|---|---|---|
| arena a 50 iterazioni, bot a mano: traccia e ogni ricerca | 80/80 | 80/80 | 80/80 | | 80/80 ciascuno |
| arena a 50 iterazioni, bot coi prior: traccia e ogni ricerca | 80/80 | 80/80 | 80/80 | | |
| esempi PPO bit per bit, self-play | 80/80 | 80/80 | 80/80 | | 80/80 ciascuno |
| esempi PPO bit per bit, PPO contro simple_trade | 80/80 | 80/80 | 80/80 | | |
| replay tracciato di partite PPO self-play | 80/80 | 80/80 | 80/80 | | |
| autonome simple_trade contro simple_trade | 80/80 | 80/80 | 80/80 | 80/80 ciascuno | 80/80 ciascuno |
| autonome random contro random | 80/80 | 80/80 | 80/80 | 80/80 ciascuno | 80/80 ciascuno |

In tutto 3.120 partite su 3.120 (ogni matchup nei due posti), di cui 720 dell'arena con 53.355 ricerche confrontate
(menu, prior della radice, visite, Q e W di ogni figlio, valore, mossa, nodi). Nessun `NotPorted`, nessuna
differenza. Lanciatore: `bash scripts/rust/tenuti_ivern.sh 4`, circa un'ora sul container.

Tempo medio di una partita d'arena a 50 iterazioni (container, misurato dentro gli strumenti di confronto):

| matchup | bot a mano, Python / Rust | bot coi prior, Python / Rust |
|---|---|---|
| EI | 18,9 / 0,71 s | 21,6 / 1,91 s |
| KI | 18,0 / 0,64 s | 20,1 / 1,67 s |
| RI | 18,8 / 0,69 s | 21,2 / 1,83 s |
| EK, ER, KR | 11,1–12,8 / 0,42–0,51 s | |

Col prior Rust resta frenato dal forward della rete, che gira in Python a batch 1.

### Posizioni mirate
Per i rami che le partite intere toccano poco o mai (stessa procedura di Rengar: posizione costruita in Python,
importata in Rust dallo stato canonico, stesse mosse, tracce identiche e ramo eseguito):
- **janna_heal**: Janna Savior giocata come REACTION su un campo controllato cura un'unità amica danneggiata. Nelle
  partite intere `heal_unit` non ha mai trovato un'unità danneggiata: il danno se ne va alla fine del combattimento.
- **daisy_pets**: Daisy! attacca con Bird, Cat, Dog e Poro fra le unità amiche e stordisce un nemico
  (`has_all_pet_tags` vera: 3 volte in 360 partite).
- **nsf_ability**: Not So Fast contro l'abilità di Daisy! che sceglie un'unità nemica: il counter toglie un'abilità
  dalla pila, non una magia.

### Divergenze trovate e risolte
Ognuna ha la sua partita nei test (`tests/rust/test_ivern.py`).

1. **Scelta di un elemento della pila per indice** (errore del porting Rust; semi 1, 5, 11 EI/IE random). Vedi sopra:
   ora l'elemento ha un'identità.
2. **Dump di un elemento della pila scelto** (forma del dump; stessi semi). Python lo scrive per valore (un
   dataclass: `{"$v": ...}`), anche quando non è più sulla pila. Rust ora scrive l'elemento, e tiene una copia di
   quelli tolti finché la pila non si svuota (`GameState.chain_gone`).
3. **Effetto collaterale dell'osservazione PPO nel replay** (errore dello strumento di replay, non del motore; seme
   1000013 IR, self-play). L'osservazione del PPO chiama `bf.control()` sulla partita vera, anche quando la domanda
   arriva dalla copia di una dichiarazione (qui l'abilità della leggenda di Rengar), e `control()` aggiorna
   `held_by`. Con l'agente PPO vero Rust lo fa già (`ppo.rs`); il replay rigioca le scelte senza agente. Ora il
   `ReplayChooser` imita l'osservazione per le scelte dell'agente. Cambiava solo `held_by` di un campo vuoto.

Nessun caso di regole ambigue. Le deviazioni note (D59, D62, D71) restano come sono a `6427b90`.

## Perimetro
- `riftbound/rs/arena_rs.py`: `COPERTI = ("EK", "ER", "KR", "EI", "KI", "RI")`. `coperte` riconosce le liste dal
  contenuto: una partita fra Evelynn, Kha'Zix, Rengar e Ivern va su Rust; Sett e le liste con la sideboard restano su
  Python.
- `scripts/ppo.py` `_motore` e `scripts/diag/arena_mazzi.py --motore rust` seguono lo stesso perimetro.

## Col checkpoint vero (sul Mac)
Il checkpoint del campione non è nel repository: qui le prove PPO e quelle col prior usano reti dal seme. Sul Mac:

```bash
bash scripts/rust/ivern_mac.command ../rbsim/runs/sett/ekris_s12/ckpt_040000.pt
```

Esempi PPO bit per bit su EI, KI e RI (self-play e contro simple_trade, semi 1–20) e arena col prior a 50 iterazioni
(semi 40000–40009). Uscite: `docs/rust/misure/mac_ivern_*.json`.

## Comandi esatti

```bash
cd rust/rbsim-py && maturin develop --release && cd ../..
python -m pytest -q tests/rust
python scripts/rust/inventario.py --liste I --matchup EI KI RI Ei Ki Ri --partite 30 --out docs/rust/INVENTARIO_IVERN.md
python scripts/rust/autonome.py --semi 1-150 --matchup EI --posti --agenti random random
python scripts/rust/diff_trace.py --semi 1000001-1000040 --modo self --matchup RI --posti
python scripts/rust/parita_ppo.py --semi 1-60 --matchup KI --posti --avversario simple_trade
python scripts/rust/arena_parita.py --semi 40000-40004 --matchup EI --posti --bot prior --iterazioni 50
python scripts/rust/posizioni_ivern.py
bash scripts/rust/tenuti_ivern.sh 4        # i semi tenuti da parte, tutte le prove
```

## Cosa vale fare dopo
1. Lanciare `ivern_mac.command` sul Mac, col campione.
2. Sett (ES, KS, RS, IS e il mix `ekris`), con lo stesso metodo.
