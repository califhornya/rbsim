# STATO

Aggiornato: 2026-11-12 (sesto passaggio: righe PARTIAL/GAP di MECHANICS.md riverificate, D53-D56).

## Obiettivo
Motore Riftbound fedele a `docs/rules/CORE_RULES.md` e al testo stampato delle
carte, prima di qualsiasi training (precon Zed vs Shen per primi).
Documento di riferimento: `docs/audit/AUDIT.md` (l'intestazione riassume lo stato).

## Decisioni prese
- Una deviazione = un test in `tests/audit/` che gioca la situazione + un commit
  di fix (verificabile e reversibile). Eccezione: D35-D49, soli dati, un commit.
- Golden game rigenerate solo per cambi voluti, motivo per partita nel commit.
- D19-D21, D23, D26, D29, D34: scelte tecniche, motivate in AUDIT.md.
- Q1–Q4, D27 (utente): priorità §337.4; Shadow Order Disciple invariato; cap
  dei turni = pareggio; Keeper of Law conta solo le unità di chi la gioca;
  Patched Porobot è unità e gear insieme.
- Quarto passaggio per classi (~930 carte fuori dalle liste, lette le segnalate).
- (Utente, 2026-11-12) Otto mazzi non precon eliminati (con agenti Pyke e
  Diana), correzioni di carte tenute; training sui due mazzi competitive.
- L'agente random è seminato dal seed della partita (riproducibile).
- Commenti di Codex: verificati uno per uno prima di agire (i due del
  2026-11-12 erano fondati: D53 e il default di `scripts/round_robin.py`).
- Flow: costo alternativo con i soli sconti di aura; gli altri modificatori
  §356.3-4 lasciati aperti perché nessuno è nei quattro mazzi.

## Fatto
- Passaggi 1-4: D1–D49, Q1–Q4, bug del coach (`cc3d776`). Dettagli in AUDIT.md.
- Rimozione mazzi: test spostati sui precon, 20 golden game rigenerate.
- Quinto passaggio (mazzi `competitive_kaisa`, `competitive_kennen`, con
  sideboard): 22 carte nuove lette, 480 partite sotto gli invarianti; D50-D52
  (gear HIDDEN da coperto, Standard Move e "when I become exhausted", Decree of
  Unity senza bersaglio); 8 golden game Kai'Sa vs Kennen. Training di prova ok.
- Sesto passaggio (righe PARTIAL/GAP di MECHANICS.md, BACKLOG O2 primo punto):
  Deflect, Hunt, Level, Backline, Empower/Empowered, Flow, Deploy verificati
  con test (`tests/audit/test_audit_mechanics_rows.py`); Unique rimandata
  (§825.4). Corrette:
  - D53 `0b877df`: Edge of Night senza unità "here" si attaccava altrove.
  - D54 `5ef1d33`: il [rune] di Kai'Sa per le spell non pagava i costi Flow.
  - D55 `e115324`: Abandon su una spell giocata con Flow la rimandava in mano.
  - D56 `56ce034`: disempower toglieva tutti gli status (Kayle Justified).
  - `10dd08a`: `round_robin.py` di default cercava i mazzi rimossi.
  Nessuna golden game cambiata. Suite verde (1751 passed, 5 skipped).

## In corso
Niente.

## Prossimi passi
Piano concordato (2026-11-12). Punti in ordine di peso per il training:
1. Banlist del 23/11: l'utente incolla l'elenco → aggiornare
   `riftbound/data/banned_cards.json`, ricontrollare i due mazzi competitive.
2. **Regole, da qui si riparte.** Righe di MECHANICS.md fatte. Restano le
   parti mai controllate che toccano i mazzi: effetti di sostituzione
   §367-373 (Zhonya's Hourglass; Abandon contro Flow già in D55), layer
   §475-482.
3. **Ricerca della rete (BACKLOG O3), il punto più importante per la qualità.**
   La ricerca guidata dalla rete decide solo la prima scelta di un'azione;
   bersagli dentro l'azione, scelte in difesa e scelte nascoste (dig,
   predict) restano alla baseline fissa: Kai'Sa e Kennen vivono di queste.
4. Training (BACKLOG O4): reti vecchie non caricabili (`ACTION_DIM` 319),
   riallenare da zero; budget MCTS, LR, dimensione rete; valutare su 100+
   partite. Qui ~3 s a partita con 10 iterazioni MCTS su 4 core: con 100
   serve una macchina con GPU.
5. Possono aspettare: sideboard imparato, tempi per turno del match, merge
   di `main` (indietro di molti commit), carte del corpus fuori dai mazzi,
   costruzione del mazzo (§103).

Da decidere (utente): allentare la regola "niente training finché il
BACKLOG non è vuoto" (proposta: partire dopo 1-3, il punto 5 in parallelo);
dove allenare (questo container o macchina con GPU).

## File principali
- `docs/audit/AUDIT.md`: elenco delle deviazioni, stato, domande aperte, cosa
  non è stato controllato.
- `tests/audit/`: un test per deviazione (`test_audit_precon_rules.py`,
  `test_audit_mechanics.py`, `test_audit_card_data.py`, `test_audit_decks.py`
  terzo passaggio, `test_audit_corpus.py` quarto, helper in `audit_helpers.py`).
- `riftbound/core/loop.py`: il motore (turno, chain, showdown, combattimento).
- `riftbound/core/battlefield.py`: controllo, contesa, Hold / Conquer.
- `riftbound/core/effects.py`: gli effetti delle carte.
- `riftbound/core/legality.py`: azioni legali offerte agli agenti.
- `riftbound/ai/coach.py` + `scripts/coach.py`: il coach e la sua pagina.
- `riftbound/data/cards/all_cards.json`: dati delle carte;
  `riftbound/data/reference/piltover_archive.json`: testo stampato
  (`scripts/piltover_sync.py compare` per le differenze).
- `riftbound/data/decks/`: `precon_zed`, `precon_shen`, `competitive_kaisa`,
  `competitive_kennen` (le liste dell'utente).
- `tests/audit/test_audit_competitive.py`: test del quinto passaggio (e D53-D55).
- `tests/audit/test_audit_mechanics_rows.py`: sesto passaggio (righe MECHANICS.md, D56).
- `docs/MECHANICS.md`: stato di ogni meccanica (riverificato 2026-11-12).
- `tests/golden_games.json` + `tests/test_golden_games.py`: 20 partite di
  riferimento Zed vs Shen (rigenerare con `RBSIM_REGEN_GOLDEN=1`).
- `BACKLOG.md`: tutto ciò che resta prima del training.
