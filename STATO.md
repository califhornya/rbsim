# STATO

Aggiornato: 2026-11-25. Ramo `rust` (default; PR 43-53 unite).

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
- (25/11, Matteo) Difetti di motore: raccolti, poi corretti in un pacchetto su un profilo nuovo (D78-D80: `+D72-D80`).
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
- 25/11 D72-D76 corretti in Rust (profilo `6427b90+D72-D76`, `docs/RUST.md` "Profili delle regole", AUDIT.md; test rossi prima,
  `tests/rust/test_d72_d76.py`): storico 600/600 identiche, confronto dei profili 8/100 identiche con ogni prima differenza spiegata.
- 25/11 D77 corretto in Rust (`6427b90+D72-D77`, `test_d77.py`): storico 180/180 (`confronto_regole._delta` da sistemare).
- 25/11 D78-D80 corretti (`6427b90+D72-D80`, pagina; `test_d78_d80.py`; Vex solo per il controllore): `tests/rust` 288, storico 200/200.
- 25/11 pagina su Rust col profilo D72-D77 (`docs/RUST.md` "Posto umano e traccia in diretta", "Pagina coach su Rust"):
  posto umano nel ponte (`set_human_agent`, `trace_on(watch)`, `Agent::notify` solo per lui; `test_umano.py`), vista dallo
  stato Rust (`riftbound/rs/vista_rs.py`, viste uguali a Python), "Come paghi?" in Rust (`payment.rs`, vie uguali a Python),
  `riftbound/ai/coach_rs.py` (campione a lavoro fisso N=42, rewind rigiocando le risposte, Sett The Boss, carte guardate);
  `scripts/coach.py --motore rust|python --regole --iterazioni`; fuori perimetro e con `--net` resta Python (storico 40/40).
- 25/11 apertura nella pagina: campo/d20/chi comincia su entrambi i motori; `riftbound/ai/apertura.py` provvisorio.
- 25/11 taratura sul Mac (`docs/rust/misure/calibra_20261125_1931.txt`): a 0,030 s il campione fa ~138 iterazioni nel turno
  (reazione 445, showdown 342); 138 fisse non inferiori a 0,030 s (ES 0,505, EK 0,520) → pagina a 138 (era 42, pesi casuali).
  Prior utile su D72-D77 (contro il bot senza prior: ES 0,583, EK 0,550). Le partite salvate registrano le iterazioni vere.

## In corso
§8 accumulo (`docs/bot/accumulo/`, MISURA_1-4): il campione ammassa nel 13% delle decisioni di turno; più iterazioni non
correggono (è `table_value`). `accumulo` (k=3, alpha 0,2) bocciato in arena (EK 0,431, ES 0,465); `minaccia`/`corsa`
(logistiche) non cambiano le mosse; `rimonta` (solo se si perde la corsa a campi fermi: Might in base verso il campo
avversario più debole, eccesso sul campo sicuro ridotto) porta il §8 in corsa persa da 57% a 27% (ES), 52% a 19% (EK),
invariato in corsa vinta. Arena sul Mac: `rimonta_mac.command`, in attesa. Tutte spente. Da correggere (Codex, PR 55):
`rifai --valutazione storica` con `--valutazione-orig` non storica resta sull'originale (`cmd_rifai`, `_gioca`).
Astra 25/11 sera (fuori dal repo, Matteo): Might da sola + controllo, poi minaccia, poi corsa ai punti; rete: prova economica;
Q massimo; partite di Matteo dopo la prima arena (2 ES). I 13 episodi umani da ricontrollare su D80.

## Prossimi passi
2. §8 accumulo (sopra), poi §7 (showdown 6 a 2, l'avversario risponde; ricontrollare a 138): una correzione alla volta.
4. Poi: `win_probe` acceso contro spento in arena (Rust nativo, costo nel budget); apertura G1.
5. Fili del 23/11: mulligan archiviato come indizio; Switcheroo da contare sui replay; GIOCATE §6 col prior 040000 su Rust.
6. Poi: Bo3 quando serve il post-side; prior in Rust se l'arena rallenta; mazzo nuovo.

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
