# STATO

Aggiornato: 2026-11-25. Ramo `rust` (default; PR 43-47 unite); apertura della partita su `claude/brave-ramanujan-jk1cha`.

## Sigle
- EK = Evelynn contro Kha'Zix; R/I/S = Rengar, Ivern, Sett (EKR, EKRI, EKRIS = i pool di mazzi).
- PPO = la rete allenata giocando contro sé stessa; "prior" = le sue preferenze sulle mosse.
- Bot a mano = la ricerca (MCTS: prova molte continuazioni) con una valutazione scritta a mano.
- Campione = il bot a mano guidato dai prior di `ekris_s12/ckpt_040000.pt`.
- Arena = partite a coppie (posti scambiati) per decidere se un candidato è più forte.
- Lavoro fisso = numero fisso di iterazioni per decisione (invece di un tempo).
- Minuscola nei matchup degli script (`Er`) = la lista con tutta la sideboard nel mazzo.

## Obiettivo (Matteo, 24/11)
Porting completo su Rust di carte e funzionalità del motore Python; i cinque mazzi
sono la prima tappa verificabile (ordine Rengar, Ivern, Sett, ciascuno con sideboard e test).
Obiettivo pratico: un avversario con cui Matteo possa giocare e allenarsi, anche con pochi mazzi.

## Decisioni prese
- (24/11, Astra/Matteo) Python congelato: regole `6427b90`, agente PPO con `f8a50e4`.
  Un difetto nuovo si corregge una volta, in Rust (AUDIT.md).
- (24/11, Astra/Matteo) Matteo gioca a mano contro il campione nella pagina coach; i consigli della vecchia rete
  si scollegano (solo con `--net`, su Python). (25/11) La pagina gira su Rust col profilo D72-D77 dove Rust copre la partita.
- (25/11, Astra) Un selettore delle regole in Rust: `6427b90` (default, = Python; le verifiche di parità lo
  fissano), `6427b90+D72-D76` o `6427b90+D72-D77` (`--regole`, solo su Rust, scelto all'avvio). Provenienza, righe e
  ripresa dell'arena con le regole; run nuova (`--init`) per allenare su un profilo; promozioni solo con le sue partite.
- (25/11, Matteo) D77 su un profilo nuovo, D72-D76 invariato: le run già allenate con lui restano riproducibili.
- Rust identico a Python sul profilo storico, deviazioni note comprese (D59, D62, D71); ramo non portato = NotPorted.
- Ogni tappa comprende i matchup con i mazzi già ammessi (Rengar: ER, KR, ed EK di nuovo).
- Liste riconosciute dal contenuto (`lista_sha`); perimetro Rust = `arena_rs.COPERTI` (i cinque mazzi fra loro).
- Elementi della pila con identità (`ChainItem.uid`): in Python una scelta sulla pila è l'oggetto, non l'indice.
- Sideboard provata con liste variate (`riftbound/rs/mazzi.py`): il training non fa sideboarding.
- Confine PPO e prior: Rust costruisce la domanda, Python forward (+ campionamento o softmax).
- Etichette dei `repr` Python: in Rust testo diverso con la stessa uguaglianza (carte per `uuid`).
- Chiavi di ripresa dell'arena: checkpoint (hash), budget, motore, regole (non il commit).
- Budget (metodo (a) di Astra): verifica esatta con due copie a passo comune, niente import di posizioni.
- (25/11, Matteo) Apertura come RiftAtlas/§488 (`docs/bot/APERTURA.md`): campo scelto coperto, d20, chi vince decide chi
  comincia (G2-G3: chi ha perso). Il campione deve scegliere campo e inizio in modo ponderato, per matchup.
- Divergenze dell'arena mista: quelle solo nelle ricerche si rigiocano coi conteggi registrati
  (identiche = spiegate); quelle di partita al rilancio; si guardano solo quelle che restano.

## Fatto
- Porting EK (`docs/rust/RAPPORTO_EK.md`); ricerca dell'arena in Rust (`docs/rust/RAPPORTO_ARENA.md`),
  verificata sul Mac col campione (20/20 a 50 iterazioni; Rust ×14,6 a partita).
- 24/11 prova di forza (arena mista a passo comune, Mac, 800 coppie): bot Rust a 0,030 s contro Python a 0,400 s =
  0,4938 ± 0,0158, lim. inf. 0,4780 > 0,47: **PROMOSSO 0,030 s per EK**. Partita Rust a 0,03 s: 2,36 s.
- 24/11 tappe Rengar e Ivern (`docs/rust/RAPPORTO_RENGAR.md`, `RAPPORTO_IVERN.md`, inventari): semi tenuti 2.000/2.000 e
  3.120/3.120, pila con identità; Mac col campione: PPO 240/240 ciascuna, arena col prior 40/40 e 60/60.
- 25/11 tappa Sett (`docs/rust/RAPPORTO_SETT.md`, `INVENTARIO_SETT.md`): costi aggiunti (Call to Glory), "spendi un
  buff", `sett_save`, `this_is_mighty`, `kill_unit_or_gear`, Sett Kingpin. Autonome 3.760/3.760, PPO 960/960, replay
  640/640, arena 80/80; tenuti 4.320/4.320 con gli altri sei matchup (`docs/rust/misure/tenuti_sett_*.json`), nessuna
  divergenza. Perimetro `COPERTI` coi cinque mazzi fra loro; misure sul Mac in `docs/rust/misure/mac_sett_*`.
- 24/11 pagina col campione (`scripts/coach.py`, `riftbound/ai/coach.py`, `coach_page.html`): avversario "Il campione"
  (`PPOPriorAgent`, `--campione`, `--budget 0.4`), `--net` facoltativo; lanciatori `allenatore.command`/`.bat`; immagini
  locali o Piltover Archive in cache (`card_images.py`); carte guardate; Sett The Boss chiede quale unità salvare. Playwright.
- 25/11 pagina (segnalazioni di Matteo, `docs/bot/SEGNALAZIONI.md`): magia uguale su ogni campo = una voce "Lancia X";
  gear/rune esauste ruotate; "Come paghi?" (`payment_options`, `CoachLoop`); opzioni identiche una sola. Rewind ("Annulla
  l'ultima mossa", R): `CoachLoop.record` + replay dal seme (`_Record`, `_Seat`, `CoachSession.rewind`). Motore invariato.
- 25/11 D72-D76 corretti in Rust (profilo `6427b90+D72-D76`, `docs/RUST.md` "Profili delle regole", AUDIT.md; test rossi prima,
  `tests/rust/test_d72_d76.py`): storico 600/600 identiche, confronto dei profili 8/100 identiche con ogni prima differenza spiegata.
- 25/11 D77 corretto in Rust (profilo `6427b90+D72-D77`, `9fcdc25`, contatore `D77`, `tests/rust/test_d77.py`): storico 180/180
  identiche. D72-D76 contro D72-D77 (semi 1-10): simple_trade 80/80 identiche, random 65/80 (le 15 diverse hanno D77 in uno
  showdown, ma `confronto_regole._delta` non le attribuisce a D77: da ricontrollare se si riusa lo script).
- 25/11 pagina su Rust col profilo D72-D77 (`docs/RUST.md` "Posto umano e traccia in diretta", "Pagina coach su Rust"):
  posto umano nel ponte (`set_human_agent`, `trace_on(watch)`, `Agent::notify` solo per lui; `test_umano.py`), vista dallo
  stato Rust (`riftbound/rs/vista_rs.py`, viste uguali a Python), "Come paghi?" in Rust (`payment.rs`, vie uguali a Python),
  `riftbound/ai/coach_rs.py` (campione a lavoro fisso N=42, rewind rigiocando le risposte, Sett The Boss, carte guardate);
  `scripts/coach.py --motore rust|python --regole --iterazioni`; fuori perimetro e con `--net` resta Python.
  `tests/rust` 233, coach Python 59 verdi; storico 40/40 identiche dopo gli agganci (pagamento, notify).
- 25/11 tavolo come il tappetino ufficiale (`coach_page.html`): rune stese una per carta, Base/Leggenda/Campione e
  Mazzo delle rune/Rune/Mazzo/Cimitero, avversario ruotato; niente punti sul tavolo (Matteo).

- 25/11 apertura nella pagina (`ef54d27`, `704d578`): Rust `build_game(bf_a, bf_b)` come Python (senza scelte estrazioni
  invariate; `test_campi.py`), flusso campo/d20/chi comincia su entrambi i motori (`CoachSession.scegli_campo`, `inizia`,
  `/api/campo`, `/api/inizia`; `test_apertura.py`); `riftbound/ai/apertura.py` provvisorio (campo a caso, comincia sempre).
  `tests/rust` 243, coach 59, apertura 11 verdi; Playwright fino al mulligan.

## In corso

## Prossimi passi
0. Scelta ponderata del campione (`apertura.py`): tabella per matchup misurata sul Mac, campione contro sé stesso,
   per campo mio × campo suo × chi comincia; campo = il migliore contro le scelte avversarie (col d20), inizio = confronto
   a campi scoperti, se non significativo comincia. In attesa dell'ok di Matteo e dei suoi campi da Game 1. Poi la Bo3.
1. Arene EK su Rust a 0,030 s (`arena_mazzi.py --motore rust --budget-candidato 0.03
   --budget-avversario 0.03`); budget da ricontrollare sugli altri matchup prima di usarlo lì.
2. Rete del prior in Rust o a batch (collo di bottiglia dell'arena).
3. Profilo `6427b90+D72-D77`: rimisurare il campione (pesi fermi) contro il bot a mano senza prior, da ES ed EK poi tutti
   i matchup della promozione, coppie a posti scambiati, IC 95%; ricontrollare il budget 0,030 s (Astra, 25/11).
4. Pagina su Rust: provarla con Matteo (tavolo nuovo compreso: clic, anteprima, evidenziazioni non provati a mano);
   rimisurare N (`ITERAZIONI_CAMPIONE`, 42, misurato con una rete a pesi casuali) col checkpoint vero sul Mac;
   unire il ramo in `rust` (PR) quando Matteo è d'accordo.
5. Segnalazioni in `docs/bot/SEGNALAZIONI.md`; scenari di GIOCATE.md §7-§8 (carte sprecate; accumulo sul campo già tenuto: `table_value`).

## File principali
- `rust/rbsim-core/src/`: motore (`game.rs`, `lp_*.rs`, `effects*.rs`, `legality.rs`, `agents.rs`,
  `obs.rs`, `features.rs`, `dump.rs`, `trace.rs`); `search.rs` la ricerca dell'arena.
- `rust/rbsim-py/`: estensione `riftbound_rs` (`ppo.rs` agente PPO, `search_py.rs` prior).
- `riftbound/rs/`: ponte Python (`rust_bridge.py`, `collect_rs.py`, `arena_rs.py` con il perimetro,
  `trace_py.py`, `mazzi.py` liste con sideboard).
- `scripts/rust/`: verifiche (`autonome.py`, `diff_trace.py`, `parita_ppo.py`, `arena_parita.py`,
  `posizioni_*.py`, `tenuti_*.sh`, `inventario.py`), Mac (`rengar_mac.command`, `ivern_mac.command`, `sett_mac.command`,
  `arena_mac.command`), misure (`bench_*.py`), arena mista (`arena_mista*.py`, altra sessione).
- `tests/rust/`: test sull'estensione (`test_<mazzo>.py`, `test_d72_d76.py`, `test_d77.py`); qui `maturin build --release` + `pip install`.
- `scripts/ppo.py` (`_motore`, `--regole`), `scripts/diag/arena_mazzi.py` (`--motore rust`, `--regole`);
  `riftbound/provenienza.py` (profili, `regole_partite`); `scripts/rust/confronto_regole.py` (i due profili).
- Partita a mano: `scripts/coach.py` (server, `--campione`, `--budget`, `--net`, `--motore`, `--regole`, `--iterazioni`),
  `riftbound/ai/coach.py` (`CoachSession`), `coach_rs.py` (partita su Rust), `coach_page.html`; `scripts/allenatore.command` (Mac).
- `docs/RUST.md`, `docs/rust/` (rapporti, inventari, misure), `docs/audit/AUDIT.md`.
- `riftbound/core/`: motore Python di riferimento (congelato).
