# Backlog: cosa resta aperto

Solo le voci aperte. Riprese dalla sezione "Open now" del vecchio backlog
(2026-11-10), tolte quelle chiuse da allora (banlist, audit delle regole, merge
su `main`, reti pre-F3). Priorità e stato: `STATO.md`. Regole non controllate:
`docs/audit/AUDIT.md`, sezione "Not checked". Il lavoro chiuso (sezioni A-G,
citate nei commenti del codice come "BACKLOG G3", "B20"):
`docs/archivio/BACKLOG_chiuso.md`.

Una voce è chiusa quando un test gioca la situazione e controlla cosa dicono il
testo della carta o le Core Rules. Le voci nuove vanno qui.

## Struttura del motore
- [ ] `loop.py` in un blocco unico e groviglio tra motore ed `effects.py`
      (89 metodi interni usati dagli effetti): problema e piano a fasi in
      `docs/PIANO_MOTORE.md`.

## Carte e regole
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

## Training (fermo dal 13/11, vedi STATO.md)
- [ ] `scripts/diag/` (tranne `handwritten_value.py`) e l'esempio in
      `train_selfplay.py` puntano a Kai'Sa/Kennen, i mazzi su cui sono
      allenate le reti esistenti:
      spostarli su Evelynn/Kha'Zix quando si riallena, e rifare il lanciatore
      a doppio clic (`allena.bat` / `allena.command`, tolti il 17/11 perché
      ripartivano dal run 4).
- [ ] Tuning: budget MCTS, schedule del learning rate, dimensione della rete;
      valutare su 100+ partite.
