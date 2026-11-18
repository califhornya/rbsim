# STATO

Aggiornato: 2026-11-18 sera (ricerca con il turno avversario: più debole).

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
- PR #32 (18/11): determinize tiene le carte note e non dipende dall'ordine
  nascosto (`tests/test_hidden_info.py`); tre correzioni della ricerca (bot
  0,58 → 0,80 contro simple_trade); risposte a S6-S9, S11a/b
  (`risposte_scenari.jsonl`), TEORIA_PUNTI, mazzo Sett di Ksword.
- Ricerca che gioca anche il turno avversario (18/11 sera, `docs/bot/
  TURNO_AVVERSARIO.md`): foglie valutate dopo il turno di lui (simple_trade)
  e l'inizio del proprio. Contro il bot #32, 100 coppie Evelynn-Kha'Zix a
  0,4 s per mossa: **0,44 ± 0,05**, più debole (54 iterazioni contro 116; su
  1.816 disaccordi la sua mossa vale di più solo in 438: rumore del massimo
  su foglie variabili). Posizione dove prevedere aiuta: s3012 turno 7
  (Kha'Zix 3-2, Zed a difendere BF0 invece di attaccare BF1), 0,92 contro
  0,47 su 60 mondi nuovi; anche s3011 (0,63 / 0,42). `docs/bot/posizioni/`.

## In corso
Niente. Training fermo dal 13/11: rete debole (run 3: 0,72; `docs/archivio/`).

## Prossimi passi
0. Valutazione dai giudizi (`riftbound/ai/judgment_value.py`, 18/11):
   misurata un giudizio alla volta, non rende il bot più forte (testa a testa
   0,49); più peso alla mano lo peggiora (0,65). Turno avversario simulato:
   più debole così com'è (0,44). Decidere con l'utente la strada: la rete,
   o il turno avversario con meno rumore (media invece del massimo sulle
   foglie simulate, o simulazione solo alla radice), o s3012 come scenario.
   Registratore RiftAtlas: bozza in `scripts/riftatlas/`, da provare sul PC.
1. Base del bot (`handwritten_value.py 200 100`, 20 min): 0,80 contro
   simple_trade, 0,97 contro random. Giudizi: `docs/bot/GIUDIZI.md`.
2. Piano v2, fasi 0 e 2-6 (D59-D65, struttura): dopo il bot, se l'utente decide.
3. Possono aspettare: training (script su Kai'Sa/Kennen), sideboard, tempi per turno, carte e regole fuori dai mazzi.

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
- `scripts/diag/`: le misure (`handwritten_value.py`: base del bot;
  `opponent_turn.py` / `opponent_turn_check.py`: turno avversario, posizioni).
  `docs/archivio/`: storico (training del 13/11, BACKLOG A-G, piano v1).
- `riftbound/data/cards/all_cards.json`: dati; `riftbound/data/reference/
  piltover_archive.json`: testo stampato (`scripts/piltover_sync.py compare`).
- `riftbound/data/decks/`: precon, competitive dell'utente (`scripts/deck_from_txt.py`).
- `tests/golden_games.json` + `test_golden_games.py`: 28 partite, solo stato
  finale (`RBSIM_REGEN_GOLDEN=1` per rigenerarle). `BACKLOG.md`: voci aperte.
