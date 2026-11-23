# Backlog: cosa resta aperto

Solo le voci aperte. Riprese dalla sezione "Open now" del vecchio backlog
(2026-11-10), tolte quelle chiuse da allora (banlist, audit delle regole, merge
su `main`, reti pre-F3). Priorità e stato: `STATO.md`. Regole non controllate:
`docs/audit/AUDIT.md`, sezione "Not checked". Il lavoro chiuso (sezioni A-G,
citate nei commenti del codice come "BACKLOG G3", "B20"):
`docs/archivio/BACKLOG_chiuso.md`.

Una voce è chiusa quando un test gioca la situazione e controlla cosa dicono il
testo della carta o le Core Rules. Le voci nuove vanno qui.

## Motore: correttezza e struttura
- [ ] Deviazioni aperte D59-D68 (AUDIT, ottavo passaggio: revisione esterna),
      ancora senza test; l'ordine dei fix è in `docs/PIANO_MOTORE.md` (v2).
- [ ] Un errore dentro un effetto è ignorato in silenzio (loop.py ~1575,
      ~1852): la partita può restare modificata a metà. Zero casi in 120
      partite dei sei mazzi; nei test deve far fallire (piano, fase 0).
- [ ] `scripts/trace_game.py` non è deterministico con un seed: installa gli
      agenti dopo la factory, senza il seed per posto.
- [ ] Un `GameLoop` nuovo su una copia azzera `units_played` e `spells_cast`
      (il `Result` di una copia).
- [ ] Registro delle partite: un'unità salvata da Guardian Angel risulta
      morta; una morte da Disintegrate non viene registrata.
- [ ] Coach: sbaglia morti e pescate quando entra ed esce una carta con lo
      stesso nome (Baited Hook, Traveling Merchant).
- [ ] Rete: la codifica arriva a 12 carte in mano (`MAX_HAND`), una 13ª carta
      non si può scegliere.
- [ ] Struttura: `loop.py` in un blocco unico, effetti che usano 94 metodi
      interni del motore e scrivono nello stato; fase 6 del piano.
- [ ] D71, Switcheroo (`docs/bot/GIOCATE.md` §1, casi in
      `scripts/diag/switcheroo_casi.py`; da fare ad arena finita, se l'utente
      decide): a) si gioca senza due unità allo stesso campo (§355.8:
      `has_valid_target` non conosce `swap_might`); b) il controllo preliminare
      annulla scambi validi (due amiche, due nemiche, amica più forte); c) da
      coperto il campo non è ristretto (§811.1.d.2); d) i bersagli non passano
      da `_can_choose` (DEFLECT non pagabile, "can't be chosen"). Un test per
      ciascuna in `tests/audit/`, golden da rigenerare con motivo.
- [ ] Da vedere: il menu offre "Cast Switcheroo @BF0" e "@BF1", la stessa
      mossa (il campo si sceglie dopo): opzioni doppie per la rete e la ricerca;
      controllare le altre spell che scelgono il campo da sé.

## Carte e regole
- [ ] `load_deck_json` rifiuta il campione scelto anche nel mazzo principale;
      §103.3.b.1 permette fino a 3 copie, campione compreso (la lista di Ivern
      di 82FAW ne ha una in più: `docs/bot/partite/82FAW_ivern_lista.txt`). Da
      vedere anche §103.3.a.3: quelle copie contano come Chosen Champion.
- [ ] Il resto del corpus: letto per classi (AUDIT, quarto passaggio); carta per
      carta solo le carte dei mazzi in uso.
- [ ] Flow: i modificatori di costo §356.3-4 diversi dalle aure di sconto
      (nessuno nei mazzi in uso).
- [ ] Sostituzioni e layer, nessuna carta dei mazzi: ordine di più sostituzioni
      della morte (§372), quale morte simultanea si salva (§373), dipendenze
      dei layer (§480-481).

## Coach
- [ ] Il mulligan e le scelte durante le mosse dell'avversario non sono seguiti
      dal coach; la pagina per due carte coperte (B8) e le leggende di Neeko
      (B16) non sono controllate a vista.

## Motore
- [ ] Velocità (B32): le dichiarazioni in chain girano su una copia profonda
      della partita (round robin ~1,3x più lento); idee in BACKLOG_chiuso, F.
- [ ] Motore a passi per alberi MCTS profondi: solo se la ricerca lo chiede.

## Match
- [ ] Sideboard appreso; il chooser dei battlefield vede solo i propri; mulligan
      e battlefield nello spazio delle decisioni apprese; `MINUTES_PER_TURN`
      (`core/match.py`) senza tempi reali per turno.

## Bot e rete: qualità delle giocate (`docs/bot/GIOCATE.md`)
- [ ] Partita 35.010 sul Mac, ad arena finita (§6): ricostruzione con i pesi,
      rete finale a confronto, bot completo allo showdown di Switcheroo
      (il tavolo dice se Evelynn poteva pagare il DEFLECT di Fiora).
- [ ] Quanto è diffuso: `giocate.py campione` sulla rete ckpt_040000 e sul
      campione (mosse con p < 0,10, Switcheroo fuori dallo showdown o a vuoto).
- [ ] La rete non lega Switcheroo al combattimento in corso (98% su Valley):
      se la misura lo conferma, è un limite del training (scelte interne rare).
- [ ] Mulligan di Sett a mano fissata: inconcluso a 22 seed; servono ~430 seed
      per ±0,05; meglio sul Mac con il campione come pilota.
- [ ] Nessuna misura contro un umano: un pannello di errori evidenti dalle
      partite dell'utente, GIUDIZI e scenari sul campione, partite vere registrate.

## Training (fermo dal 13/11, vedi STATO.md)
- [ ] `scripts/diag/` (tranne `handwritten_value.py`) e l'esempio in
      `train_selfplay.py` puntano a Kai'Sa/Kennen, i mazzi su cui sono
      allenate le reti esistenti:
      spostarli su Evelynn/Kha'Zix quando si riallena, e rifare il lanciatore
      a doppio clic (`allena.bat` / `allena.command`, tolti il 17/11 perché
      ripartivano dal run 4).
- [ ] Tuning: budget MCTS, schedule del learning rate, dimensione della rete;
      valutare su 100+ partite.
