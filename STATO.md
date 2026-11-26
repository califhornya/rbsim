# STATO

Aggiornato: 2026-11-26. Ramo `rust` (default; PR fino alla 58 unite).

## Sigle
- EK = Evelynn contro Kha'Zix; R/I/S = Rengar, Ivern, Sett (EKR, EKRI, EKRIS = i pool di mazzi).
- PPO = la rete allenata giocando contro sé stessa; "prior" = le sue preferenze sulle mosse.
- Bot a mano = la ricerca (MCTS: prova molte continuazioni) con una valutazione scritta a mano.
- Campione = il bot a mano guidato dai prior di `ekris_s12/ckpt_040000.pt`.
- Arena = partite a coppie a posti scambiati; lavoro fisso = iterazioni fisse; `Er` = lista con tutta la sideboard.

## Obiettivo (Matteo, 24/11)
Porting completo su Rust di carte e funzionalità del motore Python; i cinque mazzi (con sideboard e test) la prima tappa.
Obiettivo pratico: un avversario con cui Matteo possa giocare e allenarsi, anche con pochi mazzi.

## Decisioni prese
- (24/11, Astra/Matteo) Python congelato: regole `6427b90`, agente PPO con `f8a50e4`.
  Un difetto nuovo si corregge una volta, in Rust (AUDIT.md).
- (24/11, Astra/Matteo) Matteo gioca a mano contro il campione nella pagina coach; i consigli della vecchia rete
  si scollegano (solo con `--net`, su Python). (25/11) La pagina gira su Rust col profilo D72-D80 dove Rust copre la partita.
- (25/11, Astra) Un selettore delle regole in Rust: `6427b90` (default, = Python; le verifiche di parità lo
  fissano), `6427b90+D72-D76`, `+D72-D77` o `+D72-D80` (`--regole`, solo su Rust, scelto all'avvio). Provenienza, righe e
  ripresa dell'arena con le regole; run nuova (`--init`) per allenare su un profilo; promozioni solo con le sue partite.
- (25/11, Matteo) D77 su un profilo nuovo, D72-D76 invariato: le run già allenate con lui restano riproducibili.
- (25/11, Matteo) Difetti di motore: raccolti, poi corretti in un pacchetto su un profilo nuovo (D78-D80: `+D72-D80`);
  (26/11) D81 subito, da solo (`+D72-D81`), perché falsava ogni partita con Sett.
  (26/11) D82 subito, da solo (`+D72-D82`): Edge of Night da coperta si attaccava al campo 0 (Evelynn di Matteo).
- Rust identico a Python sul profilo storico, deviazioni note comprese (D59, D62, D71); ramo non portato = NotPorted.
- Ogni tappa comprende i matchup con i mazzi già ammessi (Rengar: ER, KR, ed EK di nuovo).
- Liste riconosciute dal contenuto (`lista_sha`); perimetro Rust = `arena_rs.COPERTI` (i cinque mazzi fra loro).
- Elementi della pila con identità (`ChainItem.uid`): in Python una scelta sulla pila è l'oggetto, non l'indice.
- Sideboard provata con liste variate (`riftbound/rs/mazzi.py`): il training non fa sideboarding.
- Confine PPO e prior: Rust costruisce la domanda, Python forward (+ campionamento o softmax).
- Etichette dei `repr` Python: in Rust testo diverso con la stessa uguaglianza (carte per `uuid`).
- Budget (metodo (a) di Astra): verifica esatta con due copie a passo comune, niente import di posizioni.
- (25/11, Matteo) Apertura come RiftAtlas/§488 (`docs/bot/APERTURA.md`): campo scelto coperto, d20, chi vince decide chi
  comincia (G2-G3: chi ha perso). Il campione deve scegliere campo e inizio in modo ponderato, per matchup.
- Divergenze dell'arena mista: quelle solo nelle ricerche si rigiocano coi conteggi registrati
  (identiche = spiegate); quelle di partita al rilancio; si guardano solo quelle che restano.
- (25/11, Astra) Scenari e promozioni nuove su D72-D77; rete ferma (`ckpt_040000`, profilo di addestramento registrato
  a parte). Correzioni una alla volta, provate su casi opposti e partite tenute fuori. Campione calibrato come
  avversario predefinito; apertura G1: campo abituale e scelta manuale; Bo3 quando Matteo vuole il post-side.

## Fatto
- Porting EK (`docs/rust/RAPPORTO_EK.md`); ricerca dell'arena in Rust (`docs/rust/RAPPORTO_ARENA.md`),
  verificata sul Mac col campione (20/20 a 50 iterazioni; Rust ×14,6 a partita).
- 24/11 prova di forza (arena mista a passo comune, Mac, 800 coppie): bot Rust a 0,030 s contro Python a 0,400 s =
  0,4938 ± 0,0158, lim. inf. 0,4780 > 0,47: **PROMOSSO 0,030 s per EK**. Partita Rust a 0,03 s: 2,36 s.
- 24-25/11 tappe Rengar, Ivern, Sett (`docs/rust/RAPPORTO_*.md`): tutto identico a Python; `COPERTI` = i cinque mazzi.
- 24/11 pagina col campione (`scripts/coach.py`, `riftbound/ai/coach.py`, `coach_page.html`, `--campione`, `--net`
  facoltativo; lanciatori `allenatore.command`/`.bat`; immagini in cache `card_images.py`). Playwright.
- 25/11 segnalazioni 1-14 (`docs/bot/SEGNALAZIONI.md`): pagina corretta, D78 segnato, partite salvate in
  `runs/coach/partite/`, il campione cerca prima la vittoria nel turno (`win_probe`; arena invariata).
- 25-26/11 difetti di motore corretti in Rust, ognuno su un profilo (`docs/RUST.md` "Profili delle regole", AUDIT.md,
  `tests/rust/test_d*.py`): D72-D76 (storico 600/600), D77 (180/180), D78-D80 (200/200), D81 (Call to Glory, segnalazione
  26; ES 80/80, 9/30 diverse), D82 (Edge of Night da coperta al BF1 si attaccava al BF0, segnalazione 27; EK ed ES 80/80,
  0/60 diverse: lo copre il test). `tests/rust` 324; `6427b90+D72-D82` default della pagina.
- 25/11 pagina su Rust (`docs/RUST.md` "Posto umano e traccia in diretta", "Pagina coach su Rust"): posto umano nel ponte
  (`set_human_agent`), vista `riftbound/rs/vista_rs.py`, "Come paghi?" (`payment.rs`), `riftbound/ai/coach_rs.py` (rewind
  rigiocando le risposte); `scripts/coach.py --motore rust|python --regole --iterazioni`; fuori perimetro e `--net`: Python.
- 25/11 apertura nella pagina: campo/d20/chi comincia su entrambi i motori; `riftbound/ai/apertura.py` provvisorio.
- 25/11 taratura sul Mac (`docs/rust/misure/calibra_20261125_1931.txt`): a 0,030 s il campione fa ~138 iterazioni nel turno
  (reazione 445, showdown 342); 138 fisse non inferiori a 0,030 s (ES 0,505, EK 0,520) → pagina a 138 (era 42, pesi casuali).
  Prior utile su D72-D77 (contro il bot senza prior: ES 0,583, EK 0,550). Le partite salvate registrano le iterazioni vere.

## In corso
§8 accumulo chiuso (26/11, `docs/bot/accumulo/`, GIOCATE §8): pagina con `--valutazione rimonta` (default di `coach.py`,
spenta altrove); arena contro la storica EK 0,522, ES 0,533, altri 8 0,515-0,607. Bocciati `accumulo`, `minaccia`/`corsa`.
Matteo: partita Evelynn-Sett 013325 (`rimonta`, D72-D81, quasi certamente la prima delle due) vinta 8 a 4 in 14; alla
domanda §8 nessuna giocata di Sett l'ha messo in difficoltà (GIOCATE §8). Manca la seconda. Da fare: i 13 episodi umani
ricontrollati su D80 (Astra).
§9 (GIOCATE, segnalazione 28): il campione gioca Vi con Vex vivo e lo toglie dopo; nelle simulazioni nessuno giocava le
finestre di reazione e showdown (copie senza agenti). Astra (26/11, risposte fuori dal repo): migliorare la ricerca, `rimonta`
resta il campione; esperimento sul T9 di 013325 (k=10): finestre on/off × quota on/off sugli stessi mondi, linea di Matteo
guidata, continuazioni fino alla fine per Kinkou su Bandle / Vi in base / Sett su Valley; poi il valore oltre il turno.
Fatto (spento di default, storico 80/80): `finestre` (piloti PPO nelle simulazioni, ripresa della finestra), `quota`, diagnosi;
`decisione.py incrocio|guidata|continua`; rilevatore §9 in `episodi.py`. In attesa: il blocco sul Mac (`docs/bot/esperimenti/`).

## Prossimi passi
1. Leggere `docs/bot/esperimenti/` (T9, Vex ES/EK): se le finestre trovano la linea da sole → arena; solo con la quota → esplorazione in allenamento.
2. §7 (showdown 6 a 2, l'avversario risponde; ricontrollare a 138): una correzione alla volta.
3. Poi: `win_probe` in arena (Rust nativo); apertura G1; Bo3 col post-side; prior in Rust se l'arena rallenta; mazzo nuovo.
4. Fili del 23/11: mulligan archiviato come indizio; Switcheroo da contare sui replay; GIOCATE §6 col prior 040000 su Rust.

## File principali
- `rust/rbsim-core/src/`: motore (`game.rs`, `lp_*.rs`, `effects*.rs`, `legality.rs`, `agents.rs`,
  `obs.rs`, `features.rs`, `dump.rs`, `trace.rs`); `search.rs` la ricerca dell'arena.
- `rust/rbsim-py/`: estensione `riftbound_rs` (`ppo.rs` agente PPO, `search_py.rs` prior).
- `riftbound/rs/`: ponte Python (`rust_bridge.py`, `collect_rs.py`, `arena_rs.py` con il perimetro,
  `trace_py.py`, `mazzi.py` liste con sideboard).
- `scripts/rust/`: verifiche (`autonome.py`, `diff_trace.py`, `parita_ppo.py`, `arena_parita.py`,
  `posizioni_*.py`, `tenuti_*.sh`, `inventario.py`), Mac (`rengar_mac.command`, `ivern_mac.command`, `sett_mac.command`,
  `arena_mac.command`), misure (`bench_*.py`), arena mista (`arena_mista*.py`, altra sessione).
- Calibrazione e diagnosi del campione: `scripts/rust/calibra_campione.py` (misura, forza, profilo), `decisione.py`
  (rifai, concordanza; `riftbound/rs/decisione_rs.py`), `episodi.py`; arena con `--iterazioni-*`, `--win-probe-*`, `--avversario-mano`.
- `tests/rust/`: test sull'estensione (`test_<mazzo>.py`, `test_d72_d76.py`, `test_d77.py`); qui `maturin build --release` + `pip install`.
- `scripts/ppo.py` (`_motore`, `--regole`), `scripts/diag/arena_mazzi.py` (`--motore rust`, `--regole`);
  `riftbound/provenienza.py` (profili, `regole_partite`); `scripts/rust/confronto_regole.py` (i due profili).
- Partita a mano: `scripts/coach.py` (server, `--campione`, `--budget`, `--net`, `--motore`, `--regole`, `--iterazioni`),
  `riftbound/ai/coach.py` (`CoachSession`), `coach_rs.py` (partita su Rust), `coach_page.html`; `scripts/allenatore.command` (Mac).
- `docs/RUST.md`, `docs/rust/` (rapporti, inventari, misure), `docs/audit/AUDIT.md`.
- `riftbound/core/`: motore Python di riferimento (congelato).
