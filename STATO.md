# STATO

Aggiornato: 2026-11-11 (fine del secondo passaggio dell'audit).

## Obiettivo
Motore Riftbound fedele a `docs/rules/CORE_RULES.md` e al testo stampato delle
carte, prima di qualsiasi training (precon Zed vs Shen per primi).
Documento di riferimento: `docs/audit/AUDIT.md` (l'intestazione riassume lo stato).

## Decisioni prese
- Una deviazione = un test in `tests/audit/` che gioca la situazione + un commit
  di fix: così ogni correzione è verificabile e reversibile da sola.
- Le golden game si rigenerano solo quando il cambio di comportamento è voluto,
  con il motivo partita per partita nel messaggio di commit.
- D19: `_phase_beginning` copre ancora Awaken → Channel (non spezzato in più
  metodi) perché ~40 file di test lo chiamano direttamente.
- D20: il Conquer dipende da `Battlefield.gained_control` (chi ha *ottenuto* il
  controllo nel turno), non più da `last_controller`; quest'ultimo resta solo
  perché la firma delle golden lo legge.
- D21: restrizione "battlefield where you have units" come parametro della carta
  (`battlefield: friendly_units`), non come caso speciale per nome.

## Fatto
- Primo passaggio (sessione precedente): D1–D18, tutte corrette.
- Secondo passaggio (questa sessione), tutte corrette, suite verde
  (1665 passed, 5 skipped, nessun xfail):
  - D19 `99678b6`: ordine dello Start of Turn secondo §315 (Awaken, abilità di
    inizio Beginning, Hold, Channel).
  - D20 `eb8acb7`: Conquer anche per un battlefield perso e ripreso nello stesso
    turno (§471.1). 2 golden rigenerate.
  - D21 `3ada8b6`: Moonfall solo su un battlefield dove chi la gioca ha unità.
    5 golden rigenerate.
  - D22 `197be0b`: il punto dell'Hold viene dato prima delle sue abilità (§473).

## In corso
Niente.

## Prossimi passi
1. Risposte dell'utente a Q1–Q4 in `AUDIT.md` ("Ambiguous rules"): priorità
   sulla chain, Shadow Order Disciple a mazzo vuoto, cap a 40 turni in
   self-play, Keeper of Law.
2. Audit carta per carta delle altre otto liste (finora solo le 7 carte di
   D13–D18 e D21); 136 carte segnalate da `piltover_sync.py compare`.
3. Non controllati: costruzione del mazzo (§103), procedura di match,
   effetti di sostituzione (§372-373), layer (§475-482), lato AI.
4. `ACTION_DIM` è 319 (era 316): le reti salvate prima di D2 non si caricano.

## File principali
- `docs/audit/AUDIT.md`: elenco delle deviazioni, stato, domande aperte, cosa
  non è stato controllato.
- `tests/audit/`: un test per deviazione (`test_audit_precon_rules.py`,
  `test_audit_mechanics.py`, `test_audit_card_data.py`, helper in
  `audit_helpers.py`).
- `riftbound/core/loop.py`: il motore (turno, chain, showdown, combattimento).
- `riftbound/core/battlefield.py`: controllo, contesa, Hold / Conquer.
- `riftbound/core/effects.py`: gli effetti delle carte.
- `riftbound/core/legality.py`: azioni legali offerte agli agenti.
- `riftbound/data/cards/all_cards.json`: dati delle carte;
  `riftbound/data/reference/piltover_archive.json`: testo stampato.
- `tests/golden_games.json` + `tests/test_golden_games.py`: 20 partite di
  riferimento (rigenerare con `RBSIM_REGEN_GOLDEN=1`).
- `BACKLOG.md`: tutto ciò che resta prima del training.
