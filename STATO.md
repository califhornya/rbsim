# STATO

Aggiornato: 2026-11-18 notte (partita dal vivo contro Ivern registrata; G16-G23).

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
- (Utente, 17/11) `Result` di una copia: contatori dal punto di copia, lasciato.
- Flow: solo sconti di aura (§356.3-4 aperti). Ricerca: un nodo per opzione, prior uguali.
- Scelte nascoste: decise quando servono, rigiocando dall'ultima decisione.
- (Utente, 13/11) La rete serve come avversario per allenarsi e per misurare
  mazzi e matchup. Tetto al training rispettato: run 4 non migliora → stop.
  Proposte in parole semplici (cosa faccio, quanto costa, cosa sapremo);
  ogni deviazione dal piano concordato detta esplicitamente.
- Training: più partite e meno esempi per partita invece di più ricerca per
  mossa: il valore ha bisogno di esiti, non di posizioni della stessa partita.
- (Utente, 18/11 sera) Rete: parte dalle partite del bot a mano (imita il
  bot migliore, non simple_trade), poi self-play; si allena sul Mac.
- (Utente, 18/11) Regole dal motore o da CORE_RULES, mai a memoria; lezioni
  in GIUDIZI.md sempre con partita e turno (i principi da soli non si capiscono).
- (gptAstra, 18/11) Rete: per seed, 1.600 allenare / 200 epoca / 200 test, disgiunti,
  Evelynn metà in A e metà in B (prima: 200 tutte Evelynn in B, usate due volte).
- (Utente, 18/11) Rete: mosse delle carte in mano dalla carta (puntatore), "once" della leggenda visibile.
- Mano nota: carte per identità (`Player.hand_public`, come `Deck.known_top`);
  determinize ordina il pool prima di mescolare (dipende solo da cosa è nascosto).

## Fatto
- Audit, passaggi 1-7: D1–D58, Q1–Q4 e Q6; dettagli in AUDIT.md.
- Revisione esterna (17/11): D59-D68 in AUDIT; fase 1 del piano v2: D66-D68
  corrette (`tests/audit/test_audit_copies.py`), 28 golden identiche.
- Partite dal vivo su RiftAtlas (17-18/11): partita 1 giocata da Claude
  (persa), BO3 dall'utente. GIUDIZI G8-G15; checklist e note in PARTITA_LIVE.
  18/11 notte: contro Ivern (flamingo, stanza 82FAW), interrotta al turno 10
  sul 5-4; G16-G23; registrazione e log in `docs/bot/partite/`.
- PR #32 (18/11): determinize tiene le carte note (`tests/test_hidden_info.py`);
  ricerca corretta (bot 0,58 → 0,80 contro simple_trade); risposte S6-S9,
  S11a/b (`risposte_scenari.jsonl`), TEORIA_PUNTI, mazzo Sett di Ksword.
- Ricerca col turno avversario (`docs/bot/TURNO_AVVERSARIO.md`): 0,44 ± 0,05
  contro il bot #32, più debole; aiuta in s3012 t7 e s3011 (`posizioni/`).

## In corso
Rete dal bot a mano (`docs/bot/RETE.md`): `scripts/rete.command` sul Mac
(partite, allenamento, misure; ~2 ore), branch `claude/vigilant-gates-b95tqx`
con divisione, mano→mossa e trigger di Evelynn corretti (`tests/test_bootstrap_split.py`,
`tests/test_net_hand_and_legend.py`). In attesa di `runs/boot1/RISULTATI.txt`.

## Prossimi passi
0. Valutazione dai giudizi (`riftbound/ai/judgment_value.py`, 18/11):
   misurata un giudizio alla volta, non rende il bot più forte (testa a testa
   0,49); più peso alla mano lo peggiora (0,65). Turno avversario simulato:
   più debole così com'è (0,44); scegliere per media o per caso peggiore
   delle simulazioni sbaglia 5-6 posizioni su 7. Deciso: la rete. Stop se
   non prevede l'esito meglio del valore a mano o non fa 0,55 contro il bot;
   se passa, self-play da `net_boot.pt` (lanciatore da preparare).
   Registratore RiftAtlas usato nella 82FAW (nessun buco; `avversarioScoperto`
   esclude le carte rivelate). Parser JSON → posizione del motore: PR #34.
1. Base del bot (`handwritten_value.py 200 100`, 20 min): 0,80 contro
   simple_trade, 0,97 contro random. Giudizi: `docs/bot/GIUDIZI.md`.
2. Piano v2 (fasi 0, 2-6, D59-D65) dopo il bot, se l'utente decide. Possono aspettare: training, sideboard, tempi, carte fuori dai mazzi.
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
- `riftbound/ai/handwritten.py`: il bot a mano (valore, ricerca a tempo);
  `scripts/bootstrap_net.py` + `scripts/rete.command`: la rete dal bot.
- `scripts/diag/`: le misure (`handwritten_value.py`: base del bot;
  `opponent_turn.py` / `opponent_turn_check.py`: turno avversario, posizioni).
  `docs/archivio/`: storico (training del 13/11, BACKLOG A-G, piano v1).
- `riftbound/data/cards/all_cards.json`: dati; `riftbound/data/reference/
  piltover_archive.json`: testo stampato (`scripts/piltover_sync.py compare`).
- `riftbound/data/decks/`: precon, competitive dell'utente (`scripts/deck_from_txt.py`).
- `tests/golden_games.json` + `test_golden_games.py`: 28 partite, solo stato
  finale (`RBSIM_REGEN_GOLDEN=1` per rigenerarle). `BACKLOG.md`: voci aperte.
