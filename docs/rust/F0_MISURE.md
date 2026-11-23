# F0 · Misure Python di partenza (porting Rust)

Revisione `6427b90`. Le misure sono provvisorie: vengono da questo container e dai pesi iniziali da seme, non dal Mac né da un checkpoint allenato. I dati grezzi sono in `docs/rust/misure/f0_*.json`.

**Macchina.** Container Linux, Intel Xeon 2,1 GHz, 4 core, Python 3.13.18, torch 2.13.0 (CPU).

**Pesi.** `PPONet()` dal seme 1, sha256 dei tensori `02c45ba0d9b97266`, gli stessi di `ppo.py --seme 1` (la stessa `torch.manual_seed(1)` prima di `PPONet()`). L'hash è calcolato dagli script `bench_*` sullo `state_dict`.

## PPO, self-play EK

**Ciclo completo** (`scripts/rust/bench_ppo_ciclo.py --cicli 4 --workers 4 --seme 1`).
- Configurazione: 64 partite per ciclo, 4 processi, 1 thread torch per processo, 4 thread nell'aggiornamento.
- Riscaldamento: raccolta 5,72 s, aggiornamento 6,99 s.
- Mediana di 4 cicli: raccolta **5,32 s**, aggiornamento **5,15 s**, ciclo **10,71 s**.
  - L'aggiornamento pesa il **48%** del ciclo.
  - Partite all'ora: 43.300 contando la sola raccolta, 21.500 contando il ciclo.
- Controllo con `scripts/ppo.py --mazzi ek --seme 1 --workers 4`: tempi uguali, 6 s + 5–7 s per ciclo (log in `runs/rust_f0/`).

**Dove va il tempo della raccolta** (`scripts/rust/bench_ppo_split.py --partite 32 --seme 1`, un processo e un thread, tempi esclusivi).

| parte | quota | cosa |
|---|---|---|
| motore | 43,1% | GameLoop, effetti, euristiche, copie interne |
| rete | 24,0% | forward PPONet (3.148 decisioni) |
| legali | 18,5% | `legal_actions` (4.491 chiamate) |
| osservazione | 11,1% | `Observation.from_state` + `encode_observation` |
| descrittori | 3,3% | `describe_action` / `describe_choice` |

- Una partita costa 319 ms su un core e dura in media 17,4 turni.
- Su Rust passa il **76%** della raccolta (motore, legali, osservazione, descrittori). Il forward della rete, il 24%, resta in Python.

**Tetto del guadagno sul ciclo.** Con la parte Rust 10 volte più veloce, la raccolta scende da 5,3 a circa 1,7 s e il ciclo da 10,7 a circa 6,8 s: **1,57×, −36%**. Anche con un Rust infinitamente veloce il ciclo non scende sotto circa 6,4 s (1,65×), perché l'aggiornamento resta tutto in PyTorch.

## Arena EK, PPOPriorAgent nei due posti

Le misure usano `scripts/rust/bench_arena_fisso.py`:
- semi 40000–40001;
- posti scambiati;
- chi comincia secondo la parità del seme;
- un processo;
- bot costruito direttamente, senza `arena_bot._make`.

| lavoro | partite | mediana per partita | iterazioni per decisione principale |
|---|---|---|---|
| 50 iterazioni (budget None) | 4 | 14,8 s | 50 |
| 0,4 s CPU per mossa | 4 | 22,4 s | 96–129 (sul Mac ne risultavano circa 170) |

Ripartizione del tempo a 50 iterazioni:

| parte | quota |
|---|---|
| motore e ricerca | 85,5% (copie, `determinize`, legali, applicazione, valore, albero) |
| rete del prior | 7,7% |
| osservazione | 5,8% |
| descrittori | 1,0% |

Un'arena consuma molte più ore di una run PPO. Per tappa, dai dati in STATO:
- **PPO:** 0,7–1 ora per tappa.
- **Arene:** 2,5–9,5 ore per tappa.

## Scelta del primo punto d'integrazione: la raccolta PPO

In ore lorde l'arena vale di più: è circa 6 volte il PPO per tappa, e su Rust passerebbe circa il 90% del suo lavoro. Scelgo comunque il PPO, per tre ragioni:

1. **Nell'arena il guadagno non diventa subito ore risparmiate.** A 0,4 s per mossa un motore più veloce dà più iterazioni, non partite più brevi. Le ore si recuperano solo abbassando il budget, dopo una prova di forza a posti scambiati con un criterio dichiarato prima: è una decisione a parte, e costa a sua volta ore di arena.
2. **Il lavoro sul PPO è un sottoinsieme di quello sull'arena:** motore, legali, osservazione, descrittori e scelte. L'arena richiede in più copie, `determinize` e continuazioni della ricerca, con il prior calcolato sull'intero menu. La prima prova end-to-end con un checkpoint arriva quindi prima. Il guadagno del PPO si legge direttamente sul ciclo intero, con un tetto stimato di circa 1,6× sul ciclo, cioè −36%. A beneficio misurabile simile è la precedenza indicata da Matteo.
3. **Il nucleo Rust serve a entrambi.** L'arena è la seconda integrazione naturale e il pozzo di ore più grande.

**Osservazione.** Sul PPO, dopo Rust la parte più pesante del ciclo sarà l'aggiornamento (circa il 75%). Sovrapporre raccolta e aggiornamento, o accorciare l'aggiornamento, sarebbe il passo successivo. È fuori da questo incarico.
