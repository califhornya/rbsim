# STATO

Aggiornato: 2026-11-27. Ramo `rust` (default).

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
- (25/11, Astra/Matteo) Selettore delle regole in Rust (`--regole`; `6427b90` = Python, fissato dalle verifiche di parità);
  ogni correzione su un profilo nuovo (run riproducibili), in pacchetto o da sola se falsa le partite (D81, D82);
  provenienza e ripresa dell'arena con le regole; run nuova (`--init`) per allenare su un profilo.
- Rust identico a Python sul profilo storico, deviazioni note comprese (D59, D62, D71); ramo non portato = NotPorted.
- Ogni tappa comprende i matchup coi mazzi già ammessi; liste riconosciute dal contenuto (`lista_sha`); perimetro
  Rust = `arena_rs.COPERTI` (i cinque mazzi fra loro).
- Pila con identità (`ChainItem.uid`); sideboard provata con liste variate (`mazzi.py`), il training non la fa.
- Confine PPO e prior: Rust costruisce la domanda, Python forward (+ campionamento o softmax).
- Budget (metodo (a) di Astra): verifica esatta con due copie a passo comune, niente import di posizioni.
- (25/11, Matteo) Apertura come RiftAtlas/§488 (`docs/bot/APERTURA.md`): campo scelto coperto, d20, chi vince decide chi
  comincia (G2-G3: chi ha perso). Il campione deve scegliere campo e inizio in modo ponderato, per matchup.
- Arena mista: divergenze solo nelle ricerche rigiocate coi conteggi registrati; si guardano solo quelle che restano.
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
- (27/11, Matteo; Astra non disponibile) «Pensa» = politica migliorata per simulazione: alla decisione di turno la mossa
  del campione + le 2 più visitate, giocate fino alla fine sugli stessi 32 mondi `ignote` (40000..), si gioca la media
  più alta (pari: il campione). Misura sulle 480 posizioni, verifica su 100 mondi diversi (50000..); regola fissata
  prima: lim. inf. > 0 e ≥20 posizioni cambiano mossa. Campione predefinito invariato senza arena (lim. inf. > 50%).

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
Strade precedenti chiuse senza guadagno (pilota, scelta per Q, sonda A, 1.000 iterazioni, movimento); `rimonta` default.
«Pensa» misurata sul CCX63 (`docs/bot/esperimenti/fondo_20261127_1404/`): **PASSA**, +2,5 pp [+1,7, +3,4], 135/480
cambiano mossa (+8,9 pp sulle cambiate); costo: 65,7 s/turno sul Mac (mediana), arena 100 coppie/matchup ~56 h di CCX63.
Matteo ha ~16 h di CCX63. Varianti economiche (`ridotto.txt`): regola fissata prima (≥ +1,9 pp, lim. inf. > 0, non verificate ≤ 10%) passa solo 2 candidati/32 mondi
(+2,0 pp, costo 0,75, 42 h). 8 mondi/3 candidati: +1,7 pp [+0,9, +2,6] (21 non verificate; a 0: +2,0), costo 0,25:
arena ~14 h, ~16,5 s/turno sul Mac. `analisi.txt` (`fondo_analisi.py`): Q ordina le posizioni (Spearman 0,75; 0,40 a
inizio partita) ma non le mosse (58% d'accordo con le partite giocate); errori sparsi su tutti i tipi. Domande ad Astra.

## Prossimi passi
1. Risposte di Astra (direzione: Pensa in partita o come insegnante; arena 8 mondi) e decisione di Matteo.
2. «Pensa» nella pagina (`coach_rs.py`, `scripts/coach.py`), facoltativa, con la variante scelta.
3. Arena candidato con Pensa contro campione sul CCX63, semi nuovi (non 30M..90M), regola fissata prima.

## File principali
- `rust/rbsim-core/src/`: motore (`game.rs`, `lp_*.rs`, `effects*.rs`, `legality.rs`, `agents.rs`,
  `obs.rs`, `features.rs`, `dump.rs`, `trace.rs`); `search.rs` la ricerca dell'arena.
- `rust/rbsim-py/`: estensione `riftbound_rs` (`ppo.rs`, `search_py.rs` prior e valore).
  Riallenamento: `riftbound/rs/{raccolta,allena,generazione,seguiti}.py`, `scripts/rust/` omonimi, `generazione_mac`,
  `valore_mac`; `make_probs_misto`, `set_search_valore_rete_at`; scelta finale: `scelta.py`, `scelta_mac`; `pensa.py`, `pensa_mac`; `muovi.py`, `muovi_mac`;
  «Pensa»: `fondo.py`, `fondo.command`, varianti `fondo_ridotto.py`, analisi `fondo_analisi.py`.
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
