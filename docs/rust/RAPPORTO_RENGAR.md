# Rapporto Rengar: il mazzo di Rengar nel motore Rust

Ramo `claude/clever-mendel-vdxw9k`, verso `rust`. Riferimento Python: regole `6427b90`, agente PPO con `f8a50e4`
(congelato, `docs/audit/AUDIT.md`). Il motore Python non è stato toccato; l'unica correzione Python è nello strumento
di traccia (`riftbound/rs/trace_py.py`, punto 2 delle divergenze).

**Tappa Rengar raggiunta.** La lista competitiva di Rengar con la sua sideboard gioca su Rust. Sui matchup ER e KR
nei due posti, ed EK di nuovo, le partite sono identiche a quelle Python. Valgono i semi tenuti da parte, gli esempi
PPO bit per bit e l'arena a lavoro fisso, ricerche comprese: zero divergenze inspiegate, nessun `NotPorted`.
EK, ER e KR vanno su Rust nell'arena e nel training (`arena_rs.COPERTI`, `ppo._motore`).

## Cosa è stato portato
Inventario: `docs/rust/INVENTARIO_RENGAR.md` (`scripts/rust/inventario.py --liste R --matchup ER KR Er Kr`).
25 carte (mazzo, sideboard, leggenda, campione, tre campi, il token Mech), 26 effetti, 15 verbi.
Prima di questa tappa mancavano:

| Cosa | Carte | Dove in Rust |
|---|---|---|
| verbo `ready_unit` | First Mate, Pyke Dockside Butcher | `effects.rs` `fx_ready_unit` |
| verbo `blink_unit` | Thrill of the Hunt | `effects.rs` `fx_blink_unit` |
| verbo `deal_damage` | Bilgewater Tracker (sideboard) | `effects.rs` `fx_deal_damage` |
| verbo `kill_gear` | Brittle Steel (sideboard); anche Acceptable Losses e An Offer You Can't Refuse, sideboard EK | `effects.rs` `fx_kill_gear`, `gear_deflect_tax` |
| condizione `you_already_played_another_card_this_turn` | Noxus Hopeful (LEGION) | `lp_conditions.rs` |
| condizione `friendly_total_might_at_least` | Kinkou Initiate | `lp_conditions.rs` (`friendly_units`, `threshold`) |
| condizione `friendly_mighty_unit_here` | Sunken Temple | `lp_conditions.rs` |
| quantità `other_battlefields_controlled` | Seat of Power | `effects_core.rs` `effect_amount` (ora `&mut`: `bf.control()` registra il controllo) |

Tutto il resto che Rengar usa era già nel motore. Trigger: `on_friendly_unit_played`, `on_win_combat`,
`on_conquer`, `on_death`, `on_move`, `on_self_played`, `cost_modifier`. Parole chiave: AMBUSH, ASSAULT, HIDDEN,
GANKING, ACCELERATE. Poi il campo Hunters' Circle (`first_play_here_discount`) e il token Mech (`play_token`).

Due funzioni già portate ora seguono Python alla lettera:
- `_gear_matches`: per i filtri diversi dall'energia Rust usava `zone_card_matches`. Python guarda solo il dominio.
  Nessuna carta EK aveva quei filtri.
- `_to_trash`: mancava `empowered = False` sulla carta che lascia il campo.

I verbi sono tradotti per intero, funzione per funzione. Alcuni rami servono solo ad altre carte e i matchup di
Rengar non li toccano (copertura riga per riga delle funzioni Python sul campione):
- `deal_damage`: `split`, `bonus_source`, `its_damage`, `filter`, `banish_if_dies`;
- `blink_unit`: `any_side`, `same_location`, `base`, `play_location`;
- `kill_gear`: `max_energy_self_might`, `self`, unità che sono gear, DEFLECT dei gear.

Questi rami si proveranno con le carte che li usano. Dove Python chiama funzioni non ancora portate, Rust dà
`NotPorted`: `split`, `same_location`, `amount_if_attacking`, `then_if_killed`, `_only`.

### Liste con la sideboard
Le partite di training non fanno sideboarding, quindi le carte di sideboard non entrerebbero mai in partita.
`riftbound/rs/mazzi.py` costruisce la lista di Rengar con tutta la sideboard nel mazzo:
- entrano Ferrous Forerunner ×2, Brittle Steel ×2, Decree of Strength ×2, Bilgewater Tracker ×2, Sabotage, Rampage;
- escono Noxus Hopeful ×3, Pit Rookie ×3, First Mate ×2, Irresistible Faefolk ×2.

Il file è `tests/rust/mazzi/competitive_rengar_sideboard.json`. Negli script si indica con la lettera minuscola,
per esempio `--matchup Er`. Lo riconosce il contenuto: non è una lista coperta, e nel training resterebbe su Python.

## Correttezza
Tutti gli script di parità prendono `--matchup` e `--posti` (anche il matchup rovesciato: ognuno dei due mazzi in A e
in B). Il primo giocatore è bilanciato, perché dipende dalla parità del seme. Rete PPO: `PPONet()` dal seme 1.

Semi di sviluppo, build finale:

| prova | matchup (nei due posti) | esito |
|---|---|---|
| partite autonome random contro random | ER, KR, Er, Kr (semi 1–150) | 1.200/1.200 |
| partite autonome simple_trade contro simple_trade | ER, KR (1–150) | 600/600 |
| partite autonome simple_trade contro random | Er, Kr (1–100) | 400/400 |
| partite autonome random contro simple_trade | EK (1–100), RR (1–60) | 200/200, 60/60 |
| replay di partite PPO self-play tracciate | ER, KR (1000001–1000040) | 160/160 |
| esempi PPO bit per bit, self-play | ER, KR (1–100) | 400/400 |
| esempi PPO bit per bit, PPO contro simple_trade | ER, KR (1–60) | 240/240 |
| esempi PPO bit per bit, PPO contro random | EK, Kr (1–60) | 240/240 |
| arena a 50 iterazioni, bot a mano: traccia e ogni ricerca | ER, KR (40000–40009) | 40/40 |
| arena a 50 iterazioni, bot coi prior: traccia e ogni ricerca | ER, KR (40010–40014) | 20/20 |
| posizioni mirate (`scripts/rust/posizioni_rengar.py`) | 7 posizioni | 7/7, ramo eseguito |
| `pytest tests/rust` | 49 test | verdi |

Semi tenuti da parte (900001–900040, mai usati prima), build finale; risultati in `docs/rust/misure/tenuti_rengar_*.json`:

TENUTI

Le partite dell'arena confrontano anche ogni ricerca: menu, prior della radice, visite, Q e W di ogni figlio,
valore, mossa e numero di nodi. Un `NotPorted` nelle simulazioni della ricerca fermerebbe la partita Rust
(`rust_error`); non ne è comparso nessuno.

### Posizioni mirate
Riguardano rami che le partite intere toccano poco o mai. La posizione è costruita a mano in Python
(`tests/audit/audit_helpers`), importata in Rust dallo stato canonico e giocata con le stesse mosse. Le tracce devono
essere identiche e il ramo deve essere stato eseguito davvero:
- **thrill_gear**: Thrill of the Hunt su un'unità con un equipaggiamento. L'equipaggiamento resta in base. In ER e
  KR non capita, perché Rengar non ha equipaggiamenti.
- **brittle_deployed**: Brittle Steel uccide un gear schierato su un campo.
- **bilgewater_base**: Bilgewater Tracker (fino a due unità ovunque). L'unica nemica è in base e muore.
- **ferrous_dies**: Ferrous Forerunner muore in combattimento e lascia due Mech in base.
- **seat_of_power**: conquista controllando un altro campo, pesca 1.
- **sunken_temple**: conquista con un'unità MIGHTY, paga 1 e pesca 1.
- **acceptable_losses**: ogni giocatore uccide il suo gear meno caro (sideboard di Kha'Zix).

### Divergenze trovate e risolte
Ognuna ha la sua partita nei test (`tests/rust/test_rengar.py`).

1. **`_kicker_paid` a tre stati** (errore del porting Rust; seme 1000011 RE, self-play PPO, replay).
   - In Python l'attributo può mancare, valere None o valere un booleano.
   - `_card_flags`, uscendo, rimette sulla carta quello che c'era prima con `getattr(card, k, None)`: un attributo
     assente diventa None.
   - Grim Apothecary giocata con AMBUSH ha appena messo il suo trigger. Thrill of the Hunt la bandisce e la rigioca
     prima che `_resolve_card_effects` la azzeri. `getattr(card, "_kicker_paid", False)` vale allora None, non False,
     e il trigger nuovo porta `_kicker_paid: None`.
   - Rust trattava l'assenza e None allo stesso modo. Ora `Card` tiene `kicker_set` e `showed_set` (l'attributo
     esiste), e le assegnazioni passano da `set_kicker` e `set_showed`.
   - Cambiava lo stato canonico del trigger, non le regole: i due valori sono entrambi falsi.
2. **Etichetta di `decide_mode` nella traccia Python** (errore dello strumento di traccia, non del motore; seme 78 Er,
   simple_trade contro random).
   - `trace_py._to_real_any` riporta al gioco reale l'oggetto che un agente riceve da una copia (Reckless Innovator,
     `decide_mode` sulla copia di dichiarazione). Lo cerca per `id()` in tutte le copie fatte fino a quel momento.
   - Una copia vecchia poteva avere lo stesso `id()` per un oggetto ormai liberato. La traccia Python diceva così
     "Mech di B" invece di "Reckless Innovator di A".
   - Tolto quell'argomento, le 168 righe della partita coincidevano. Ora la ricerca parte dalla copia più recente:
     una copia fatta dopo l'oggetto non può averne l'`id()` finché l'oggetto vive.

Non è emerso nessun caso di regole ambigue. Le deviazioni note (D59, D62, Switcheroo) restano come sono a `6427b90`.

## Perimetro
- `riftbound/rs/arena_rs.py`:
  - `COPERTI = ("EK", "ER", "KR")`;
  - `coperte(deck_a, deck_b)` vale vero se le due liste sono fra quelle dei matchup coperti, riconosciute dal contenuto
    (`provenienza.lista_sha`);
  - `coperto(mu)` applica lo stesso criterio a un matchup in lettere.
- `scripts/ppo.py` `_motore` usa `coperte`: con `--motore rust` vanno su Rust le partite EK, ER e KR, in tutti e due
  i posti; vanno su Python le altre e quelle contro il bot a mano.
- `scripts/diag/arena_mazzi.py --motore rust` segue `coperto`.
- Il mix `ekr` del training (EK, EK, ER, KR) è ora tutto su Rust.

## Col checkpoint vero (sul Mac)
Il checkpoint del campione non è nel repository: qui le prove PPO e quelle col prior usano reti dal seme. Sul Mac:

```bash
bash scripts/rust/rengar_mac.command runs/sett/ekris_s12/ckpt_040000.pt
```

Lo script compila, esegue `pytest tests/rust` e poi fa due prove col checkpoint:
1. esempi PPO bit per bit su ER, KR ed EK, nei due posti, self-play e contro simple_trade, semi 1–20;
2. parità dell'arena col bot coi prior a 50 iterazioni su ER e KR, semi 40000–40009, nei due posti.

Uscite: `docs/rust/misure/mac_rengar_*.json`.

## Comandi esatti

```bash
cd rust/rbsim-py && maturin develop --release && cd ../..
python -m pytest -q tests/rust
python scripts/rust/inventario.py --liste R --matchup ER KR Er Kr --partite 30 --out docs/rust/INVENTARIO_RENGAR.md
python scripts/rust/autonome.py --semi 1-150 --matchup ER --posti --agenti random random
python scripts/rust/diff_trace.py --semi 1000001-1000040 --modo self --matchup KR --posti
python scripts/rust/parita_ppo.py --semi 1-100 --matchup ER --posti
python scripts/rust/arena_parita.py --semi 40000-40009 --matchup KR --posti --bot mano
python scripts/rust/posizioni_rengar.py
bash scripts/rust/tenuti_rengar.sh 4        # i semi tenuti da parte, tutte le prove
```

## Cosa vale fare dopo
1. Lanciare `rengar_mac.command` sul Mac, col campione.
2. Ivern (EI, KI, RI, e il mix `ekri`), con lo stesso metodo:
   - inventario e porting;
   - autonome, replay, esempi PPO e arena;
   - posizioni mirate per i rami rari;
   - semi tenuti da parte.
3. Sett.
