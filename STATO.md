# STATO

Aggiornato: 2026-11-26 sera. Ramo `rust` (default).

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
- (25/11, Matteo) Ogni correzione su un profilo nuovo (le run allenate restano riproducibili); difetti raccolti e
  corretti in pacchetto (D78-D80: `+D72-D80`); (26/11) D81 subito, da solo (`+D72-D81`): falsava ogni partita con Sett.
  (26/11) D82 subito, da solo (`+D72-D82`): Edge of Night da coperta si attaccava al campo 0 (Evelynn di Matteo).
- Rust identico a Python sul profilo storico, deviazioni note comprese (D59, D62, D71); ramo non portato = NotPorted.
- Ogni tappa comprende i matchup coi mazzi già ammessi; liste riconosciute dal contenuto (`lista_sha`); perimetro
  Rust = `arena_rs.COPERTI` (i cinque mazzi fra loro).
- Elementi della pila con identità (`ChainItem.uid`): in Python una scelta sulla pila è l'oggetto, non l'indice.
- Sideboard provata con liste variate (`riftbound/rs/mazzi.py`): il training non fa sideboarding.
- Confine PPO e prior: Rust costruisce la domanda, Python forward (+ campionamento o softmax).
- Budget (metodo (a) di Astra): verifica esatta con due copie a passo comune, niente import di posizioni.
- (25/11, Matteo) Apertura come RiftAtlas/§488 (`docs/bot/APERTURA.md`): campo scelto coperto, d20, chi vince decide chi
  comincia (G2-G3: chi ha perso). Il campione deve scegliere campo e inizio in modo ponderato, per matchup.
- Divergenze dell'arena mista: quelle solo nelle ricerche si rigiocano coi conteggi registrati
  (identiche = spiegate); quelle di partita al rilancio; si guardano solo quelle che restano.
- (26/11, Matteo e Astra) Filone principale: riallenare la rete con la ricerca (visite N/ΣN e esito ±1), --init da
  ckpt_040000 (che resta l'avversario fisso), stessa architettura. Pilota: 2.000 partite (200 per matchup, D72-D82),
  Dirichlet 0,25/α 0,3 alle radici di turno, temperatura 1 sulle prime 4 decisioni di turno, poi la più visitata;
  valore: prima raccolta con rimonta, poi in sviluppo 80/20 rimonta/valore (rimonta sul Pass che chiude il turno).
  Promozione: 800 coppie per matchup, media ≥0,52, lim. inf. 95% >0,50, ogni matchup lim. inf. unilaterale >0,47.
  Ritocchi a mano in pausa; la pagina può pensare minuti («Pensa», facoltativo), arene veloci.
- (26/11, Astra) Attacchi con lo showdown: sonda A dietro interruttore, soglia +0,15; pagina solo dopo fuori campione.
- (26-27/11, Astra) Campione resta `ckpt_040000`; valore al 20% chiuso (forse solo sul Pass che chiude il turno);
  raccolta da 100.000 da parte; scelta finale per Q confermata (regola di stop). Promozioni sempre su semi nuovi.
- (25/11, Astra) Scenari e promozioni nuove su D72-D77; rete ferma (`ckpt_040000`, profilo di addestramento registrato
  a parte). Correzioni una alla volta, provate su casi opposti e partite tenute fuori. Campione calibrato come
  avversario predefinito; apertura G1: campo abituale e scelta manuale; Bo3 quando Matteo vuole il post-side.
## Fatto
- Porting EK, Rengar, Ivern, Sett (`docs/rust/RAPPORTO_*.md`): identico a Python; `COPERTI` = i cinque mazzi. Arena
  in Rust verificata sul Mac; 24/11 bot Rust a 0,030 s contro Python a 0,400 s: 0,4938 (lim. inf. 0,478): **PROMOSSO**.
- 24-25/11 pagina col campione (`scripts/coach.py`, `coach_page.html`, `allenatore.command`/`.bat`); segnalazioni 1-14
  (`docs/bot/SEGNALAZIONI.md`); partite in `runs/coach/partite/`; `win_probe` (vittoria nel turno; arena invariata).
- 25-26/11 difetti di motore corretti in Rust, ognuno su un profilo (`docs/RUST.md` "Profili delle regole", AUDIT.md,
  `tests/rust/test_d*.py`): D72-D76 (storico 600/600), D77 (180/180), D78-D80 (200/200), D81 (Call to Glory, segnalazione
  26; ES 80/80, 9/30 diverse), D82 (Edge of Night da coperta al BF1 si attaccava al BF0, segnalazione 27; EK ed ES 80/80,
  0/60 diverse: lo copre il test). `tests/rust` 429 (con torch); `6427b90+D72-D82` default della pagina.
- 25/11 pagina su Rust (`docs/RUST.md` "Posto umano e traccia in diretta", "Pagina coach su Rust"): posto umano nel ponte
  (`set_human_agent`), vista `riftbound/rs/vista_rs.py`, "Come paghi?" (`payment.rs`), `riftbound/ai/coach_rs.py` (rewind
  rigiocando le risposte); `scripts/coach.py --motore rust|python --regole --iterazioni`; fuori perimetro e `--net`: Python.
- 25/11 taratura sul Mac (`docs/rust/misure/calibra_20261125_1931.txt`): a 0,030 s il campione fa ~138 iterazioni nel turno
  (reazione 445, showdown 342); 138 fisse non inferiori a 0,030 s (ES 0,505, EK 0,520) → pagina a 138 (era 42, pesi casuali). Prior utile (ES 0,583, EK 0,550).

## In corso
Pilota (b) 47,95%, (c) 49,05%; prova (d) 50,2% [48,7, 51,7], seguiti +0,2 pp. (27/11) Scelta finale
(`scelta_20261127_0946/`): visite − Q −0,3 pp [−1,0, +0,3]: resta la Q. (CCX63) Sonda A fuori campione (`sonda_20261127_1020/`): 37
posizioni (non 72), −0,70 pp [−3,81, +1,89], VP 1, FP 2, FN 2: niente arena. 1.000 contro 138 (`pensa_20261127_1034/`):
51,2% [49,6, 52,9]: resta 138 (per turno p95 5,2 s, max 121 s). Astra (155859, T5): «muovo Sett, poi Fiora sul campo»
+19 pp [+9,5, +28,5] sulla linea del bot. Altri 4 replay (`muovi_20261127_1255/`): 4 posizioni, M−B +4,5 pp [−2,0,
+16,0]; il bot schiera in base dove muovere era meglio solo in 204705 T4 (+4): troppo poche per decidere.
§8-§9: `rimonta` default della pagina; finestre bocciate; sonda A a un'ondata archiviata (Astra). Segnalazioni 29-35.
«Stesso seme»: rifacimento identico; Sett 0 su 500 contro Evelynn automatica (la ricerca non ha rumore).

## Prossimi passi
1. Risposta di Astra: allargare «muovo prima» alle 60 autonome dei seguiti (`muovi.py --autonome`), a parte le posizioni
   dove il bot schiera in base; poi, se regge, riservare visite iniziali al movimento (offline).
2. Promozioni su semi nuovi (non 30M/40M/50M/60M/70M).

## File principali
- `rust/rbsim-core/src/`: motore (`game.rs`, `lp_*.rs`, `effects*.rs`, `legality.rs`, `agents.rs`,
  `obs.rs`, `features.rs`, `dump.rs`, `trace.rs`); `search.rs` la ricerca dell'arena.
- `rust/rbsim-py/`: estensione `riftbound_rs` (`ppo.rs`, `search_py.rs` prior e valore).
  Riallenamento: `riftbound/rs/{raccolta,allena,generazione,seguiti}.py`, `scripts/rust/` omonimi, `generazione_mac`,
  `valore_mac`; `make_probs_misto`, `set_search_valore_rete_at`; scelta finale: `scelta.py`, `scelta_mac`; `pensa.py`, `pensa_mac`; `muovi.py`, `muovi_mac`.
- `riftbound/rs/`: ponte Python (`rust_bridge.py`, `collect_rs.py`, `arena_rs.py` con il perimetro,
  `trace_py.py`, `mazzi.py` liste con sideboard).
- `scripts/rust/`: verifiche (`autonome.py`, `diff_trace.py`, `parita_ppo.py`, `arena_parita.py`,
  `posizioni_*.py`, `tenuti_*.sh`, `inventario.py`), Mac (`rengar_mac.command`, `ivern_mac.command`, `sett_mac.command`,
  `arena_mac.command`), misure (`bench_*.py`), arena mista (`arena_mista*.py`, altra sessione).
- Calibrazione e diagnosi del campione: `scripts/rust/calibra_campione.py` (misura, forza, profilo), `decisione.py`
  (rifai, concordanza; `riftbound/rs/decisione_rs.py`), `episodi.py`, `attacco.py` (proposte d'attacco, serie, sonda A:
  `riftbound/rs/sonda.py`), `stesso_seme.py` (`riftbound/rs/stesso_seme.py`); arena con `--iterazioni-*`, `--win-probe-*`.
- `tests/rust/`: test sull'estensione (`test_<mazzo>.py`, `test_d72_d76.py`, `test_d77.py`); qui `maturin build --release` + `pip install`.
- `scripts/ppo.py` (`_motore`, `--regole`), `scripts/diag/arena_mazzi.py` (`--motore rust`, `--regole`);
  `riftbound/provenienza.py` (profili, `regole_partite`); `scripts/rust/confronto_regole.py` (i due profili).
- Partita a mano: `scripts/coach.py` (server, `--campione`, `--budget`, `--net`, `--motore`, `--regole`, `--iterazioni`),
  `riftbound/ai/coach.py` (`CoachSession`), `coach_rs.py` (partita su Rust), `coach_page.html`; `scripts/allenatore.command` (Mac).
- `docs/RUST.md`, `docs/rust/` (rapporti, inventari, misure), `docs/audit/AUDIT.md`; `riftbound/core/`: Python (congelato).
