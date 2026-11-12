# STATO

Aggiornato: 2026-11-12 (importati e verificati i due mazzi competitive; audit quinto passaggio).

## Obiettivo
Motore Riftbound fedele a `docs/rules/CORE_RULES.md` e al testo stampato delle
carte, prima di qualsiasi training (precon Zed vs Shen per primi).
Documento di riferimento: `docs/audit/AUDIT.md` (l'intestazione riassume lo stato).

## Decisioni prese
- Una deviazione = un test in `tests/audit/` che gioca la situazione + un commit
  di fix: così ogni correzione è verificabile e reversibile da sola.
  Eccezione (quarto passaggio): D35-D49, correzioni di soli dati, in un commit
  unico con un test per carta, per contenere l'uso.
- Le golden game si rigenerano solo quando il cambio di comportamento è voluto,
  con il motivo partita per partita nel messaggio di commit.
- D19: `_phase_beginning` copre ancora Awaken → Channel (~40 file di test lo
  chiamano direttamente).
- D20: il Conquer dipende da `Battlefield.gained_control`, non da `last_controller`.
- D21: restrizione "battlefield where you have units" come parametro della carta.
- Q1–Q4 (decise dall'utente): priorità secondo §337.4; Shadow Order Disciple
  invariato; partita al cap dei turni = pareggio; Keeper of Law conta solo le
  unità di chi la gioca.
- D23: il tempo di un'abilità attivata sta nei dati solo se la carta stampa
  [Action]/[Reaction]; un test statico lo controlla su tutto il corpus.
- D26: un gear nemico scelto si conta alla risoluzione, non in catena.
- D27 (decisa dall'utente): Patched Porobot è unità e gear insieme
  (`cards.is_gear()`, `UnitInPlay.is_gear` derivato dalla carta attuale).
- D29: "abilità legale" = "l'handler ha qualcosa da scegliere" (stessa lista di
  opzioni per legalità e risoluzione, `effects._HAS_OPTION`); scelte legali ma
  inutili per il testo (gear già pronto, gear nemico) non sono offerte, come in D9.
- D34: il Power generico si paga da un solo dominio quando basta (nessuna
  golden cambia), altrimenti da un misto.
- Quarto passaggio per classi e non carta per carta: fuori dalle liste ci sono
  ~930 carte; lette solo quelle segnalate da una scansione.
- (Utente, 2026-11-12) Gli otto mazzi non precon sono superati: eliminati e
  non più considerati. Rimossi con loro gli agenti Pyke e Diana, costruiti per
  quei mazzi. Le correzioni di carte trovate su quei mazzi restano.
- Golden game e test generici giocano solo i precon; l'agente random è ora
  seminato dal seed della partita (prima non era riproducibile), così può
  stare nelle golden.

## Fatto
- Passaggi 1-3: D1–D28 e risposte Q1–Q4, tutte corrette.
- Quarto passaggio (questa sessione), suite verde (1754 passed), nessuna
  golden cambiata:
  - D27 chiusa: Equipment sul Porobot e testi "your Equipment" giusti.
  - D29 `b4d8b2e`: 10 abilità attivate offerte senza niente da scegliere
    (Jax, Pyke Bloodharbor Ripper, Jayce, Teemo, Akali Rogue Assassin, Maduli,
    Unlicensed Armory, Pack of Wonders, Baited Hook, Cursed Sarcophagus).
  - D30 `15475ff` Jax: Equipment attaccato fra due unità qualsiasi.
  - D31 `bf2db18` Teemo: anche dal tavolo. D32 `2c54656` Baited Hook: l'unità
    da uccidere è scelta. D33 `73f504b` Ambessa: "Ready a unit" qualsiasi.
  - D34 `28c756d`: [rune][rune] pagabile con Power di domini diversi.
  - D35-D49 `598611d`: dati contro la stampa (le 131 carte segnalate da
    `piltover_sync compare`): 4 carte senza effetto, 4 statistiche/keyword,
    bersagli, costi, errata. Elenco in AUDIT.md.
  - Coach `cc3d776`: una seconda risposta alla stessa domanda (doppio click)
    veniva applicata alla domanda successiva; ora è rifiutata. Era la causa
    del test `test_coach` instabile sotto carico.

- Rimozione mazzi: tolti 8 mazzi e 2 agenti, test spostati sui precon,
  20 golden game rigenerate su Zed vs Shen.

- Mazzi competitive (quinto passaggio): `competitive_kaisa`, `competitive_kennen`
  importati con sideboard. 22 carte nuove lette, dubbie giocate; 480 partite
  sotto i controlli degli invarianti. Corrette:
  - D50 `df33571`: un gear HIDDEN giocato da coperto spariva (Edge of Night,
    Zhonya's Hourglass); Edge of Night si attacca a un'unità "here".
  - D51 `0e03237`: lo Standard Move non attivava "when I become exhausted"
    (Reckless Innovator e altre 5 carte).
  - D52 `334e93c`: Decree of Unity lanciabile senza bersaglio legale.
  - 8 golden game Kai'Sa vs Kennen aggiunte (le 20 dei precon invariate).
  Suite verde (1773 passed).

## In corso
Niente.

## Prossimi passi
1. Decidere su quali mazzi fare training (precon o competitive).
2. Banlist nuova annunciata per il 13/11, legale dal 23/11: aggiornare
   `riftbound/data/banned_cards.json` appena è pubblica.
3. Resto del corpus: solo scansioni per classi; carta per carta solo le
   carte dei mazzi in uso.
4. Non controllati: costruzione del mazzo (§103), procedura di match,
   effetti di sostituzione (§372-373), layer (§475-482), lato AI.
5. `ACTION_DIM` è 319 (era 316): le reti salvate prima di D2 non si caricano.

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
- `tests/audit/test_audit_competitive.py`: test del quinto passaggio.
- `tests/golden_games.json` + `tests/test_golden_games.py`: 20 partite di
  riferimento Zed vs Shen (rigenerare con `RBSIM_REGEN_GOLDEN=1`).
- `BACKLOG.md`: tutto ciò che resta prima del training.
