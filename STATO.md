# STATO

Aggiornato: 2026-11-11 (audit, terzo passaggio; D27 rivista dopo la review della PR #19).

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
- D20: il Conquer dipende da `Battlefield.gained_control`, non da
  `last_controller` (che resta solo per la firma delle golden).
- D21: restrizione "battlefield where you have units" come parametro della carta
  (`battlefield: friendly_units`), non come caso speciale per nome.
- Q1–Q4 (decise dall'utente): priorità secondo §337.4; Shadow Order Disciple
  invariato; partita al cap dei turni = pareggio; Keeper of Law conta solo le
  unità di chi la gioca.
- D23: il tempo di un'abilità attivata sta nei dati solo se la carta stampa
  [Action]/[Reaction]; un test statico lo controlla su tutto il corpus.
- D24: Quick-Draw offre tutte le unità del giocatore; la baseline resta sulle
  unità del battlefield dell'azione, così le golden non cambiano.
- D26: un gear nemico scelto si conta alla risoluzione (come il suo DEFLECT),
  non quando la spell va in catena: differenza accettata.
- D27 (decisa dall'utente): Patched Porobot è unità e gear insieme. Un solo
  predicato `cards.is_gear()`; in gioco `UnitInPlay.is_gear` è derivato dalla
  carta attuale (non un flag fissato all'ingresso), così regge le copie
  (Shady Spectacles); `gear_unit` resta solo "gear reso unità da Orianna".
  Si gioca, muove e paga da unità.

## Fatto
- Primo passaggio: D1–D18. Secondo: D19–D22 e risposte Q1–Q4. Tutte corrette.
- Terzo passaggio (questa sessione): le 119 carte delle otto liste non precon
  lette contro il testo stampato, ~60 giocate nel motore. Suite verde
  (1685 passed, 5 skipped, nessun xfail), nessuna golden cambiata:
  - D23 `17838db`: 39 abilità di 34 carte avevano `timing: action` non
    stampato (usabili in showdown): Heart of Dark Ice, The List, ...
  - D24 `6376f85`: Quick-Draw si attacca a qualsiasi unità che controlli
    (Cloth Armor restava in base non attaccata).
  - D25 `4947f42`: Bellows Breath solo su unità nella stessa location.
  - D26 `a0063f2`: la leggenda di Ezreal conta anche i gear nemici scelti.
  - D27 `840876a`: Patched Porobot è anche un gear (Pit Crew, Ornn's Forge,
    Ornn Blacksmith, Detonate, conteggi).
  - D28 `0ac459e`: le leggende di Rengar e Kennen scelgono qualsiasi unità.

## In corso
Niente.

## Prossimi passi
1. D27, non controllati: un Equipment sul Porobot, l'encoding AI (lo vede
   come unità).
2. Resto del corpus (carte fuori dalle dieci liste): non letto. Noti: Navori
   Fighting Pit, Ambessa Matriarch of War (come D28), Facebreaker (come D25).
3. Non controllati: costruzione del mazzo (§103), procedura di match,
   effetti di sostituzione (§372-373), layer (§475-482), lato AI.
4. `ACTION_DIM` è 319 (era 316): le reti salvate prima di D2 non si caricano.

## File principali
- `docs/audit/AUDIT.md`: elenco delle deviazioni, stato, domande aperte, cosa
  non è stato controllato.
- `tests/audit/`: un test per deviazione (`test_audit_precon_rules.py`,
  `test_audit_mechanics.py`, `test_audit_card_data.py`, `test_audit_decks.py`
  per il terzo passaggio, helper in `audit_helpers.py`).
- `riftbound/core/loop.py`: il motore (turno, chain, showdown, combattimento).
- `riftbound/core/battlefield.py`: controllo, contesa, Hold / Conquer.
- `riftbound/core/effects.py`: gli effetti delle carte.
- `riftbound/core/legality.py`: azioni legali offerte agli agenti.
- `riftbound/data/cards/all_cards.json`: dati delle carte;
  `riftbound/data/reference/piltover_archive.json`: testo stampato.
- `tests/golden_games.json` + `tests/test_golden_games.py`: 20 partite di
  riferimento (rigenerare con `RBSIM_REGEN_GOLDEN=1`).
- `BACKLOG.md`: tutto ciò che resta prima del training.
