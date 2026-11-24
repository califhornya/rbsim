# Rapporto Sett: il mazzo di Sett nel motore Rust

Ramo `claude/vibrant-johnson-k8ovzv`, unito in `rust` (PR 45). Riferimento Python: regole `6427b90`, agente PPO con `f8a50e4`
(congelato, `docs/audit/AUDIT.md`). Il motore Python non è stato toccato.

**Tappa Sett raggiunta: i cinque mazzi sono su Rust.** La lista competitiva di Sett con la sua sideboard gioca su
Rust. Sui matchup ES, KS, RS e IS nei due posti le partite sono identiche a quelle Python: partite autonome, esempi
PPO bit per bit, replay e arena a lavoro fisso, ricerche comprese. Zero divergenze del motore, nessun `NotPorted`.
Gli altri sei matchup restano identici. Evelynn, Kha'Zix, Rengar, Ivern e Sett fra loro vanno su Rust nell'arena e
nel training (`arena_rs.COPERTI`, `ppo._motore`).
Verificata anche sul Mac col checkpoint del campione: 320/320 partite con esempi PPO identici, 80/80 d'arena.

## Cosa è stato portato
Inventario: `docs/rust/INVENTARIO_SETT.md` (`scripts/rust/inventario.py --liste S --matchup ES KS RS IS Es Ks Rs Is`).
24 carte, 32 effetti, 19 verbi. L'inventario segnava tre pezzi mancanti; le partite ne hanno trovati altri quattro,
che non sono verbi ma costi e sostituzioni letti dal motore:

| Cosa | Carte | Dove in Rust |
|---|---|---|
| costi aggiunti (`_cost_extras`, `_choose_cost_extras`, `_spend_cost_extras`): `spend_buff_free` | Call to Glory ("spendi un buff: ignora il costo") | `lp_costs2.rs`; `lp_pay.rs` `pay_card_x` (gli extra scelti si pagano dopo energia e potere); `lp_action.rs` (unità) |
| costo "spendi un buff" di un'abilità (`_buff_to_spend`, `_spend_buff`) | Monastery of Hirana (pesca alla conquista) | `lp_abilities2.rs` `activated_affordable`, `buff_to_spend`, `spend_buff`; `lp_abilities.rs` `pay_discard_and_banish` |
| sostituzione della morte `sett_save` | Sett The Boss | `lp_deaths.rs` `try_replace_death`, `death_saved` |
| condizione `this_is_mighty` | Fiora Victorious (DEFLECT, GANKING, SHIELD se MIGHTY) | `lp_conditions.rs` |
| verbo `kill_unit_or_gear` (e `has_valid_target`) | Decree of Unity (sideboard) | `effects.rs` `fx_kill_unit_or_gear`; `effects_core.rs` `unit_or_gear_options`; `_kill_gear` con `_only` (`fx_kill_gear_only`) |
| verbo `grant_temporary_might_per_friendly` | Sett Kingpin | `effects.rs` (in Python il passivo non chiama l'handler: 0 esecuzioni) |

L'opzione di `cost_extras` è in Python una tupla (dizionario, energia, potere): ora `Opt::Tuple` con `Opt::Json` per il
dizionario. Nel dump è il dizionario; nel descrittore del PPO conta l'ultimo elemento (il potere, `number`), come in
`features.describe_choice`; nell'etichetta della ricerca è il `repr` Python del dizionario (`{'energy': 3, ...}`).

### Rami tradotti che Sett non tocca, e `NotPorted`
- `_choose_cost_extras`: `kills` (Commander Ledros), `xp`, `discards`, `gear_returns`, `picks` danno `NotPorted`, come
  gli altri tipi di `_cost_extras` (`spend_buffs_for_power`, `kill_units_for_power`, `spend_xp_for_energy`,
  `discard_for_energy`, `return_gear_for_energy`, `less_if_chosen`).
- `_buff_to_spend`: "self" e "other" tradotti, non provati.
- `kill_unit_or_gear`: `side: any` e `where: here` tradotti; `banish` (Burn Away) dà `NotPorted`.
- Costi di un'abilità "uccidi un'unità o un gear amico" restano `NotPorted`.

### Liste con la sideboard
`riftbound/rs/mazzi.py` costruisce la lista di Sett con tutta la sideboard nel mazzo:
- entrano solo magie: Decree of Strength, Decree of Unity, Repulse, Sabotage, Salvage (×2 ciascuna);
- escono Call to Glory ×2, Punch First ×2, Rampage ×2, Showstopper ×2, Pit Rookie, First Mate. Di ogni carta resta
  almeno una copia.

Il file è `tests/rust/mazzi/competitive_sett_sideboard.json` (`--matchup Es`).

## Correttezza
Script di parità con `--matchup` e `--posti`; primo giocatore bilanciato (parità del seme); rete PPO `PPONet()` dal
seme 1. Tutte le prove sono sulla build finale del motore (dopo l'ultima correzione è cambiata solo l'etichetta delle
ricerche, e l'arena è stata rifatta).

Semi di sviluppo:

| prova | matchup (nei due posti) | esito |
|---|---|---|
| autonome random contro random | ES, KS, RS, IS (semi 1–150), Es, Ks, Rs, Is (31–150) | 1.200/1.200, 960/960 |
| autonome simple_trade contro simple_trade | ES, KS, RS, IS, Es, Ks, Rs, Is (1–100) | 1.600/1.600 |
| esempi PPO bit per bit, self-play e contro simple_trade | ES, KS, RS, IS (1–60) | 960/960 |
| replay di partite PPO tracciate, self-play e contro simple_trade | ES, KS, RS, IS (1000001–1000040) | 640/640 |
| arena a 50 iterazioni, bot a mano e coi prior: traccia e ogni ricerca | ES, KS, RS, IS (40000–40004) | 80/80 |
| posizioni mirate (`scripts/rust/posizioni_sett.py`) | 3 posizioni | 3/3, ramo eseguito |
| `pytest tests/rust` | 97 test | verdi |
| suite Python completa (`pytest -q --ignore=tests/rust`) | 1.952 test | verdi |

Rami eseguiti (lato Python): 320 partite random e simple_trade sugli otto matchup danno 494 buff spesi, 786 calcoli
del costo con un buff spendibile e 85 costi aggiunti pagati, 370 morti sostituite da `sett_save` (le altre sostituzioni
darebbero `NotPorted`), `this_is_mighty` vera 6.861 volte, Decree of Unity 50 (4 su un gear). Nelle partite PPO (agente col chooser, semi 1–30) la scelta `cost_extras` capita 125 volte, 44 senza spendere il
buff: sono fra quelle confrontate bit per bit.

Semi tenuti da parte (900001–900040, mai usati prima), build finale; risultati in `docs/rust/misure/tenuti_sett_*.json`:

| prova | ES | KS | RS | IS | Es, Ks, Rs, Is (sideboard) | EK, ER, KR, EI, KI, RI (di nuovo) |
|---|---|---|---|---|---|---|
| arena a 50 iterazioni, bot a mano: traccia e ogni ricerca | 80/80 | 80/80 | 80/80 | 80/80 | | |
| arena a 50 iterazioni, bot coi prior: traccia e ogni ricerca | 80/80 | 80/80 | 80/80 | 80/80 | | |
| esempi PPO bit per bit, self-play | 80/80 | 80/80 | 80/80 | 80/80 | | 80/80 ciascuno |
| esempi PPO bit per bit, PPO contro simple_trade | 80/80 | 80/80 | 80/80 | 80/80 | | |
| replay tracciato di partite PPO self-play | 80/80 | 80/80 | 80/80 | 80/80 | | |
| autonome simple_trade contro simple_trade | 80/80 | 80/80 | 80/80 | 80/80 | 80/80 ciascuno | 80/80 ciascuno |
| autonome random contro random | 80/80 | 80/80 | 80/80 | 80/80 | 80/80 ciascuno | 80/80 ciascuno |

In tutto 4.320 partite su 4.320 (ogni matchup nei due posti), di cui 640 dell'arena con 43.103 ricerche confrontate.
Nessun `NotPorted`, nessuna differenza. Lanciatore: `bash scripts/rust/tenuti_sett.sh 4`, circa un'ora sul container.

Tempo medio di una partita d'arena a 50 iterazioni (container, dentro gli strumenti di confronto):

| matchup | bot a mano, Python / Rust | bot coi prior, Python / Rust |
|---|---|---|
| ES | 12,5 / 0,48 s | 15,7 / 1,70 s |
| KS | 13,3 / 0,47 s | 16,3 / 1,45 s |
| RS | 12,6 / 0,47 s | 15,1 / 1,49 s |
| IS | 18,8 / 0,70 s | 20,7 / 1,77 s |

### Posizioni mirate
Stessa procedura di Rengar e Ivern (posizione costruita in Python, importata in Rust dallo stato canonico, stesse
mosse, tracce identiche e ramo eseguito):
- **decree_gear**: Decree of Unity senza unità Chaos nemiche uccide un gear Chaos (`_kill_gear` con `_only`).
- **sett_save**: un'unità con buff muore in combattimento; Sett The Boss paga una runa, si esaurisce, spende il buff e
  la rimanda in base.
- **monastery**: conquista di Monastery of Hirana con un'unità con buff: spende il buff e pesca.

### Divergenze trovate
Nessuna del motore. Due degli strumenti:
1. **Etichetta della scelta `cost_extras` nelle ricerche dell'arena.** Le ricerche erano identiche nei numeri; Rust
   scriveva il dizionario in JSON, Python col `repr`. Ora `search.rs` scrive il `repr` (`py_repr`).
2. **Ordine delle chiavi nell'import di una posizione.** Lo stato canonico ordina le chiavi dei dizionari, così la
   riserva di potere importata in Rust era in ordine alfabetico e la runa generica di `sett_save` si pagava da un altro
   dominio. Nelle partite vere i due motori costruiscono la riserva nello stesso ordine. La posizione usa un solo
   dominio.

## Perimetro
- `riftbound/rs/arena_rs.py`: `COPERTI = ("EK", "ER", "KR", "EI", "KI", "RI", "ES", "KS", "RS", "IS")`: i cinque mazzi
  fra loro. Restano su Python le liste con la sideboard e le partite contro il bot a mano.
- `scripts/ppo.py` `_motore` e `scripts/diag/arena_mazzi.py --motore rust` seguono lo stesso perimetro: il mix
  `ekris` del training è tutto su Rust.

## Col checkpoint vero (sul Mac)
Il checkpoint del campione non è nel repository: qui le prove PPO e quelle col prior usano reti dal seme.
Sul Mac (M1 Max, 24/11, commit `a956e64`, campione `ekris_s12/ckpt_040000.pt`):

```bash
bash scripts/rust/sett_mac.command ../rbsim/runs/sett/ekris_s12/ckpt_040000.pt
```

Uscite: `docs/rust/misure/mac_sett_*_20261124_2242.json`.

| Prova (semi, nei due posti) | ES | KS | RS | IS |
|---|---|---|---|---|
| Esempi PPO bit per bit, self-play (1–20) | 40/40 | 40/40 | 40/40 | 40/40 |
| Esempi PPO bit per bit, contro simple_trade (1–20) | 40/40 | 40/40 | 40/40 | 40/40 |
| Arena col prior, 50 iterazioni (40000–40009): partite identiche | 20/20 | 20/20 | 20/20 | 20/20 |
| Ricerche confrontate, tutte identiche | 1.373 | 1.345 | 1.212 | 1.921 |
| Tempo per partita d'arena, Python / Rust | 11,2 / 0,76 s (×14,7) | 13,2 / 0,85 s (×15,6) | 11,8 / 0,77 s (×15,3) | 17,5 / 1,24 s (×14,1) |

Nessun errore Rust. Sugli esempi PPO Rust è ×3,6–5,7: conta anche il forward della rete, che resta in Python.

## Comandi esatti

```bash
cd rust/rbsim-py && maturin develop --release && cd ../..
python -m pytest -q tests/rust
python scripts/rust/inventario.py --liste S --matchup ES KS RS IS Es Ks Rs Is --partite 30 --out docs/rust/INVENTARIO_SETT.md
python scripts/rust/autonome.py --semi 1-150 --matchup ES --posti --agenti random random
python scripts/rust/diff_trace.py --semi 1000001-1000040 --modo self --matchup IS --posti
python scripts/rust/parita_ppo.py --semi 1-60 --matchup KS --posti --avversario simple_trade
python scripts/rust/arena_parita.py --semi 40000-40004 --matchup RS --posti --bot prior --iterazioni 50
python scripts/rust/posizioni_sett.py
bash scripts/rust/tenuti_sett.sh 4        # i semi tenuti da parte, tutte le prove
```

## Cosa vale fare dopo
1. Con i cinque mazzi su Rust: arene e training interamente su Rust; budget dell'arena da ricontrollare sui matchup
   nuovi prima di usare 0,030 s fuori da EK.
2. Il resto del catalogo, con lo stesso metodo (inventario, porting guidato dalle partite, parità, semi tenuti da parte).
