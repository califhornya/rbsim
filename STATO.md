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
- (26/11 sera, Astra) Pilota senza promozione: campione resta `ckpt_040000`; raccolta da 100.000 rinviata finché non si
  sa se il valore appreso aiuta a scegliere. Prova (d): prior di `ckpt_040000` + 20% valore di `rete.pt` (epoca 5, due
  checkpoint completi) nelle foglie; arena sugli stessi semi del pilota + «seguiti». Promozione a parte, su semi nuovi.
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
(26/11 sera) Pilota (`generazione_20261126_1810`, 4.000 partite, D72-D83): (b) 47,95%, (c) 49,05%, c−b +1,10 pp
[−0,80, +3,00]; EQM sull'esito 0,7184 → 0,6339. Da lanciare sul Mac: `valore_mac.command` = arena (d) (100 coppie × 10,
semi 40M come il pilota), confronto appaiato d−c (solo il prior), d−b, c−b; seguiti (semi 50M: partite del campione
contro sé stesso, dove (d) cambia mossa entrambe le mosse fino all'esito sugli stessi 32 mondi `ignote`).
§8-§9: `rimonta` default della pagina; finestre bocciate. Serie di 24: 5 attacchi migliori mai costruiti; sonda A
offline (`sonda.py`, `sonda_mac.command`): attacco in 6 su 24, ora diagnosi. Segnalazioni 29-35 (35 = D83, corretto).
«Stesso seme»: rifacimento identico; Sett 0 su 500 contro Evelynn automatica (la ricerca non ha rumore).

## Prossimi passi
1. Matteo: `valore_mac.command` sul Mac; risultati ad Astra (arena.txt, confronto.txt, seguiti/riepilogo.txt).
2. Se (d) sceglie linee migliori con regolarità: raccolta più grande sul CCX63; promozione su semi nuovi (non 30M/40M/50M).
3. `sonda_mac` sulle 72 posizioni (diagnosi). Dopo: «Pensa» nella pagina se c'è capacità.

## File principali
- `rust/rbsim-core/src/`: motore (`game.rs`, `lp_*.rs`, `effects*.rs`, `legality.rs`, `agents.rs`,
  `obs.rs`, `features.rs`, `dump.rs`, `trace.rs`); `search.rs` la ricerca dell'arena.
- `rust/rbsim-py/`: estensione `riftbound_rs` (`ppo.rs`, `search_py.rs` prior e valore).
  Riallenamento: `riftbound/rs/{raccolta,allena,generazione,seguiti}.py`, `scripts/rust/` omonimi, `generazione_mac`,
  `valore_mac.command`; `arena_rs.make_probs_misto` (prior e valore da due reti), `set_search_valore_rete_at`.
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
