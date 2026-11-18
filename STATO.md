# STATO

Aggiornato: 2026-11-18 (partite dal vivo su RiftAtlas; determinize corretto).

## Obiettivo
Motore Riftbound fedele a `docs/rules/CORE_RULES.md` e al testo stampato delle
carte; su quello, una rete allenata in self-play sui due mazzi competitive.
Documento di riferimento: `docs/audit/AUDIT.md` (l'intestazione riassume lo stato).

## Decisioni prese
- Una deviazione = un test in `tests/audit/` che gioca la situazione + un commit
  di fix (verificabile e reversibile). Eccezione: D35-D49, soli dati, un commit.
- Golden game rigenerate solo per cambi voluti, motivo per partita nel commit.
  D19-D21, D23, D26, D29, D34: scelte tecniche, motivate in AUDIT.md.
- Q1–Q4, D27 (utente): priorità §337.4; Shadow Order Disciple invariato; cap
  dei turni = pareggio; Keeper of Law conta solo le unità di chi la gioca;
  Patched Porobot è unità e gear insieme.
- (Utente, 12/11) Otto mazzi non precon eliminati, correzioni di carte tenute.
  (17/11) Kai'Sa e Kennen bannati: i competitive sono Evelynn e Kha'Zix; i file
  vecchi restano come fixture. Un solo file di stato, BACKLOG solo voci aperte.
- (Utente, 17/11) Revisione esterna: prima la correttezza, poi la struttura
  (piano v2, `docs/PIANO_MOTORE.md`). Sera: strada A, prima il bot: solo la
  fase 1 (D66-D68, le copie: piccola, la partita vera non cambia), poi il bot.
  Fuori perimetro: D59-D65, la struttura, il training.
- (Utente, 17/11) Il `Result` di una copia conta `units_played` e
  `spells_cast` dal punto di copia: lasciato (la ricerca usa il vincitore).
- Flow: solo sconti di aura; altri modificatori §356.3-4 aperti (non nei mazzi).
- Ricerca: un nodo per opzione con chiave (tipo, carta, descrizione); prior uguali.
- Scelte nascoste: decise quando servono, rigiocando dall'ultima decisione.
- (Utente, 13/11) La rete serve come avversario per allenarsi e per misurare
  mazzi e matchup. Tetto al training rispettato: run 4 non migliora → stop.
  Proposte in parole semplici (cosa faccio, quanto costa, cosa sapremo);
  ogni deviazione dal piano concordato detta esplicitamente.
- Training: più partite e meno esempi per partita invece di più ricerca per
  mossa: il valore ha bisogno di esiti, non di posizioni della stessa partita.
- (Utente, 18/11) Regole dal motore o da CORE_RULES, mai a memoria; lezioni
  in GIUDIZI.md sempre con partita e turno (i principi da soli non si capiscono).
- Mano nota: carte per identità (`Player.hand_public`, come `Deck.known_top`);
  determinize ordina il pool prima di mescolare (dipende solo da cosa è nascosto).

## Fatto
- Audit, passaggi 1-7: D1–D58, Q1–Q4 e Q6; dettagli in AUDIT.md.
- Ricerca `6ebd0e7` (tutte le scelte, 68,8%); training `fd01c63`+.
- Revisione esterna (17/11): 7 rapporti in `docs/audit/revisione_esterna/`,
  D59-D68 in AUDIT (ottavo passaggio); la suite esegue 200/212 effetti.
- Fase 1 del piano v2 (17/11): D66-D68 corrette (le memorie salvano l'oggetto,
  non `id()`), `tests/audit/test_audit_copies.py`; 28 golden identiche.
- Partite dal vivo su RiftAtlas (17-18/11): partita 1 giocata da Claude
  (persa), BO3 dall'utente. GIUDIZI G8-G15; checklist e note in PARTITA_LIVE.
- determinize (18/11, `64f184f`): ridistribuiva tutta la mano avversaria; ora
  tiene le carte note (rimbalzate, rivelate) e non dipende dall'ordine
  nascosto. `tests/test_hidden_info.py`, 4 su 5 rossi prima (anche "la
  ricerca non sbircia"). Suite 1836 passed, 6 skipped; golden identiche.
- Risposte agli scenari (18/11): opzioni e mano a ogni mossa, mossa scartata,
  cosa farebbe cambiare scelta, esito a parte (`tests/test_scenari_answers.py`).
- Risposte dell'utente in chat a S6-S9, S11a/b (`risposte_scenari.jsonl`);
  teoria dei punti dal web in `docs/bot/TEORIA_PUNTI.md` (pari/dispari).
- Mazzo Sett di Ksword (`competitive_sett.json`); scenari con cambi di
  sideboard e `legend_used`; S11a/S11b dal log della G3 (`test_scenari_s11.py`).

## In corso
Niente. Training fermo dal 13/11 (run 3: 0,72 contro simple_trade; run 4
peggiore): rete debole. Dettagli in `docs/archivio/`.

## Prossimi passi
0. Bot negli scenari (`docs/bot/BOT_SCENARI.md`): 3 difetti della ricerca
   (mosse non provate = 0, reazioni con poche iterazioni, potenziamenti
   "questo turno" contati) e 3 della valutazione (coperte, mano, punti).
   Registratore RiftAtlas (sì dell'utente, 18/11): bozza in `scripts/riftatlas/`,
   da provare sulla pagina vera in una sessione sul PC dell'utente.
1. Bot con i giudizi dell'utente come valutazione della ricerca; stop se non
   batte nettamente simple_trade o non gioca in modo sensato. Base dopo il fix
   di determinize (`handwritten_value.py 200 100`, 12 min): 0,58 contro
   simple_trade, 0,86 contro random (prima 0,59 e 0,85: nel rumore, ±0,035).
2. Giudizi dell'utente: `docs/bot/GIUDIZI.md`. Evelynn e Kha'Zix: S6-S9 sulla
   pagina degli scenari (`scripts/scenari.bat`), S10 in chat; in attesa.
3. Training: script ancora su Kai'Sa/Kennen e lanciatore da rifare, se si riallena.
4. Piano v2, fasi 0 e 2-6 (D59-D65, struttura): dopo il bot, se l'utente decide.
5. Possono aspettare: sideboard, tempi per turno, carte e regole fuori dai mazzi.

Macchine: PC Windows (Ryzen 7 7800X3D) o Mac M1 Max. Log: `fresh`/`|v|`, `empty_turns`.

## File principali
- `docs/audit/AUDIT.md`: deviazioni, stato, domande aperte, cosa non è stato
  controllato; `tests/audit/`: un test per deviazione; `docs/MECHANICS.md`.
- `docs/bot/`: GIUDIZI, TEORIA_PUNTI, PARTITA_LIVE, scenari.json, partite/.
- `docs/PIANO_MOTORE.md`: piano v2 (correttezza, poi struttura), con
  l'avanzamento; `docs/audit/revisione_esterna/`: i rapporti (in inglese).
- `riftbound/core/`: il motore. `loop.py` (turno, chain, showdown, combattimento),
  `effects.py`, `battlefield.py` (Hold / Conquer), `legality.py` (azioni legali).
- `riftbound/ai/net_mcts.py`: la ricerca guidata dalla rete; test in
  `tests/test_net_mcts.py`. `riftbound/ai/selfplay.py` + `scripts/train_selfplay.py`.
- `riftbound/ai/coach.py`, `scenari.py` (+ `scripts/`): coach e scenari dei giudizi.
- `scripts/diag/`: le misure (`handwritten_value.py`: base del bot).
  `docs/archivio/`: storico (training del 13/11, BACKLOG A-G, piano v1).
- `riftbound/data/cards/all_cards.json`: dati; `riftbound/data/reference/
  piltover_archive.json`: testo stampato (`scripts/piltover_sync.py compare`).
- `riftbound/data/decks/`: precon, competitive dell'utente (`scripts/deck_from_txt.py`).
- `tests/golden_games.json` + `test_golden_games.py`: 28 partite, solo stato
  finale (`RBSIM_REGEN_GOLDEN=1` per rigenerarle). `BACKLOG.md`: voci aperte.
