# STATO

Aggiornato: 2026-11-26. Ramo `rust` (default).

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
- Budget (metodo (a) di Astra): verifica esatta con due copie a passo comune, niente import di posizioni.
- (25/11, Matteo) Apertura come RiftAtlas/§488 (`docs/bot/APERTURA.md`): campo scelto coperto, d20, chi vince decide chi
  comincia (G2-G3: chi ha perso). Il campione deve scegliere campo e inizio in modo ponderato, per matchup.
- Divergenze dell'arena mista: quelle solo nelle ricerche si rigiocano coi conteggi registrati
  (identiche = spiegate); quelle di partita al rilancio; si guardano solo quelle che restano.
- (26/11, Matteo) Basta correzioni a mano una alla volta: proposta ad Astra di riallenare la rete con la ricerca
  (visite e risultati, regole correnti); la pagina può pensare minuti a turno, le arene restano veloci.
- (26/11, Astra) Attacchi con lo showdown: sonda a un'ondata (A) dietro interruttore, soglia +0,15, generatore e
  budget congelati sulle 24; B (finestre + quota) solo confronto economico; pagina solo dopo fuori campione e arena.
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
  0/60 diverse: lo copre il test). `tests/rust` 324; `6427b90+D72-D82` default della pagina.
- 25/11 pagina su Rust (`docs/RUST.md` "Posto umano e traccia in diretta", "Pagina coach su Rust"): posto umano nel ponte
  (`set_human_agent`), vista `riftbound/rs/vista_rs.py`, "Come paghi?" (`payment.rs`), `riftbound/ai/coach_rs.py` (rewind
  rigiocando le risposte); `scripts/coach.py --motore rust|python --regole --iterazioni`; fuori perimetro e `--net`: Python.
- 25/11 taratura sul Mac (`docs/rust/misure/calibra_20261125_1931.txt`): a 0,030 s il campione fa ~138 iterazioni nel turno
  (reazione 445, showdown 342); 138 fisse non inferiori a 0,030 s (ES 0,505, EK 0,520) → pagina a 138 (era 42, pesi casuali).
  Prior utile su D72-D77 (contro il bot senza prior: ES 0,583, EK 0,550). Apertura nella pagina (`apertura.py`, provvisorio).

## In corso
§8 chiuso (26/11, GIOCATE §8): pagina con `--valutazione rimonta` (default di `coach.py`); bocciati `accumulo`, `minaccia`.
§9 (GIOCATE, segn. 28): gioca sotto Vex e lo toglie dopo; finestre: arena NON PASSA (ES 0,474, EK 0,531). T9 (Astra):
attaccare Bandle vince 30-38/100 contro 7-8 di Valley. Serie di 24 (`attacco_20261126_1352_serie/`): 5 attacchi
migliori (+28/+43 pp), mai costruiti, un'ondata con AMBUSH o magia nello showdown; sonda di fine turno +0,15: 5 veri, 0 falsi.
(26/11) Sonda A, prototipo offline (`riftbound/rs/sonda.py`, `attacco.py sonda|congela|fuori|t9-foglia`): sui dati
salvati sceglie l'attacco in 6 su 24 (i 5 veri + EK4A T15 neutro). Da lanciare: `scripts/rust/sonda_mac.command`
(congela con identità, 72 posizioni nuove ES/EK + R/I, T9 foglia contro vittorie), ~1 h.
(26/11, Matteo) 155859 (seme 680137721, D72-D82) vinta 8 a 4; segnalazioni 29-35 (SEGNALAZIONI; 35 candidato D83:
costo di un modo pagato senza "Come paghi?", niente Gold). Serie «stesso seme» (`stesso_seme_20261126_1614/`, Evelynn
automatica dal T1): rifacimento IDENTICO (153 righe); Sett 0 vittorie su 500, ma solo 6 partite distinte: il seme
della ricerca cambia poco le mosse del campione. Il passaggio segui-Matteo-poi-pilota richiede un agente composto.

## Prossimi passi
1. Risposte di Astra alla proposta «riallenare con la ricerca» (7 domande: priorità, partenza, valore nelle foglie,
   esplorazione, promozione, scelte interne, «pensa» nella pagina). Poi il registro delle visite e il ciclo.
2. `sonda_mac` (prova offline della sonda A) quando Matteo vuole; D83 (Reckless/Gold) da verificare.
3. §7; `win_probe` in arena; apertura G1; Bo3 col post-side; fili del 23/11.

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
  (rifai, concordanza; `riftbound/rs/decisione_rs.py`), `episodi.py`, `attacco.py` (proposte d'attacco, serie, sonda A:
  `riftbound/rs/sonda.py`), `stesso_seme.py` (`riftbound/rs/stesso_seme.py`); arena con `--iterazioni-*`, `--win-probe-*`.
- `tests/rust/`: test sull'estensione (`test_<mazzo>.py`, `test_d72_d76.py`, `test_d77.py`); qui `maturin build --release` + `pip install`.
- `scripts/ppo.py` (`_motore`, `--regole`), `scripts/diag/arena_mazzi.py` (`--motore rust`, `--regole`);
  `riftbound/provenienza.py` (profili, `regole_partite`); `scripts/rust/confronto_regole.py` (i due profili).
- Partita a mano: `scripts/coach.py` (server, `--campione`, `--budget`, `--net`, `--motore`, `--regole`, `--iterazioni`),
  `riftbound/ai/coach.py` (`CoachSession`), `coach_rs.py` (partita su Rust), `coach_page.html`; `scripts/allenatore.command` (Mac).
- `docs/RUST.md`, `docs/rust/` (rapporti, inventari, misure), `docs/audit/AUDIT.md`.
- `riftbound/core/`: motore Python di riferimento (congelato).
