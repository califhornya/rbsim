# STATO

Aggiornato: 2026-11-12 (mazzi competitive verificati; training deciso su di essi; piano dei prossimi passi).

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
- D19-D21, D23, D26: scelte tecniche, motivate in AUDIT.md.
- Q1–Q4 (decise dall'utente): priorità secondo §337.4; Shadow Order Disciple
  invariato; partita al cap dei turni = pareggio; Keeper of Law conta solo le
  unità di chi la gioca.
- D27 (decisa dall'utente): Patched Porobot è unità e gear insieme
  (`cards.is_gear()`, `UnitInPlay.is_gear` derivato dalla carta attuale).
- D29: "abilità legale" = "l'handler ha qualcosa da scegliere" (stessa lista di
  opzioni per legalità e risoluzione, `effects._HAS_OPTION`); scelte legali ma
  inutili per il testo (gear già pronto, gear nemico) non sono offerte, come in D9.
- D34: il Power generico si paga da un solo dominio quando basta (nessuna
  golden cambia), altrimenti da un misto.
- Quarto passaggio per classi e non carta per carta: fuori dalle liste ci sono
  ~930 carte; lette solo quelle segnalate da una scansione.
- (Utente, 2026-11-12) Gli otto mazzi non precon eliminati e non più
  considerati, con gli agenti Pyke e Diana; le correzioni di carte restano.
- (Utente, 2026-11-12) Il training si fa sui due mazzi competitive.
- L'agente random è seminato dal seed della partita (riproducibile).

## Fatto
- Passaggi 1-3: D1–D28 e risposte Q1–Q4, tutte corrette.
- Quarto passaggio: D29-D49 (abilità senza scelta legale, Jax, Teemo,
  Baited Hook, Ambessa, Power generico misto, dati di 131 carte segnalate)
  e bug del coach (doppia risposta, `cc3d776`). Dettagli in AUDIT.md.
- Rimozione mazzi: test spostati sui precon, 20 golden game rigenerate.
- Mazzi competitive (quinto passaggio): `competitive_kaisa`, `competitive_kennen`
  importati con sideboard. 22 carte nuove lette, dubbie giocate; 480 partite
  sotto i controlli degli invarianti. Corrette:
  - D50 `df33571`: un gear HIDDEN giocato da coperto spariva (Edge of Night,
    Zhonya's Hourglass); Edge of Night si attacca a un'unità "here".
  - D51 `0e03237`: lo Standard Move non attivava "when I become exhausted"
    (Reckless Innovator e altre 5 carte).
  - D52 `334e93c`: Decree of Unity lanciabile senza bersaglio legale.
  - 8 golden game Kai'Sa vs Kennen aggiunte (le 20 dei precon invariate).
  Suite verde (1773 passed). Prova di training sui competitive: funziona.

## In corso
Niente.

## Prossimi passi
Piano concordato (2026-11-12): la prossima sessione parte dal punto 2, poi,
se c'è modo, il 3. Punti in ordine di peso per il training:
1. Banlist del 23/11: l'utente incolla l'elenco → aggiornare
   `riftbound/data/banned_cards.json`, ricontrollare i due mazzi competitive.
2. **Regole (BACKLOG O2), da qui si riparte.** `docs/MECHANICS.md`: 8 righe
   PARTIAL + 1 GAP mai riverificate (Flow è già superata): ognuna contro il
   codice e un test. Poi le parti mai controllate che toccano i mazzi:
   effetti di sostituzione §372-373 (Zhonya's Hourglass), layer §475-482.
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
- `tests/audit/test_audit_competitive.py`: test del quinto passaggio.
- `tests/golden_games.json` + `tests/test_golden_games.py`: 20 partite di
  riferimento Zed vs Shen (rigenerare con `RBSIM_REGEN_GOLDEN=1`).
- `BACKLOG.md`: tutto ciò che resta prima del training.
