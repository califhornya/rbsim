# Per Astra (25/11, sera)

## La tua ultima domanda: Matteo può giocare contro il bot più forte?
Sì, e ci ha già giocato. Pagina locale (`scripts/allenatore.command` sul Mac, poi http://127.0.0.1:8765): Matteo
contro il campione, cioè la ricerca a mano guidata dai prior di `ekris_s12/ckpt_040000.pt`, sui cinque mazzi
(Evelynn, Kha'Zix, Rengar, Ivern, Sett, ciascuno con la sideboard). Gira su Rust con le regole corrette D72-D77.
Fuori da questi mazzi gira su Python. Dalle sue partite sono uscite 14 segnalazioni:
- 7 erano difetti della pagina, tutti corretti;
- in 2 il motore seguiva le regole, e si è spiegato perché;
- 2 erano difetti delle regole: D77 corretto, D78 segnato;
- 2 sono errori di gioco del campione: il 7 (accumula sul campo che tiene già) è aperto, il 14 (non vedeva la
  vittoria nel turno) è corretto;
- 1 ha portato alla partita salvata.

A parte c'è un altro errore di gioco (GIOCATE §7), anch'esso aperto.

Le partite ora si salvano complete (`runs/coach/partite/`, rigiocabili). Matteo dice che la pagina sembra andare
tutto bene.

## Cosa resta aperto (perché non si perda niente)
1. **Forza del campione nella pagina.** Lavoro fisso di 42 iterazioni per decisione, misurato con una rete a pesi
   casuali. Va rimisurato col checkpoint vero sul Mac: forse nella pagina è più debole che in arena (0,4 s).
2. **Errori di gioco visti da Matteo.**
   - §7: Call to Glory e Punch First lanciate per prime in uno showdown già vinto 6 a 2.
   - §8: accumula unità sul campo che tiene già (Might 24, poi 31) invece di attaccare quello di Matteo.
   - Causa probabile: `table_value` (0,05 per punto di Might su un campo, senza limite; 0,03 una carta in mano) e
     una ricerca che vede un turno solo. Gli scenari non sono ancora scritti.
3. **Controllo della vittoria nel turno (`win_probe`).** È solo nella pagina, non nel campione dell'arena; non è
   misurato.
4. **Apertura.** Il campo e chi comincia sono già nella pagina, ma il campione sceglie il campo a caso e comincia
   sempre. Proposta: una tabella per matchup (campo mio × campo suo × chi comincia) misurata sul Mac. Bo3 non fatta:
   comincia chi ha perso; campi esclusi dopo una vittoria (§488.5); sideboard fra le partite, che il campione non fa.
5. **Profilo delle regole.** Il campione è allenato su `6427b90` (con D72-D77), la pagina gioca su D72-D77. Da
   rimisurare: il campione contro il bot a mano senza prior su quel profilo, poi tutti i matchup della promozione.
   Da decidere se riallenare sul profilo nuovo.
6. **D78** (Vex: "They can't move it" non ferma Showstopper). Segnato, si corregge quando Matteo lo dice.
7. **Velocità dell'arena.** Il budget di 0,030 s è promosso solo per EK, da ricontrollare sugli altri matchup. La rete
   del prior va portata in Rust o messa a batch: è il collo di bottiglia.
8. **Fili del 23/11 mai chiusi.**
   - Mulligan di Sett: a 40 semi, rimandare solo Rampage batte la scelta della rete (+0,28 ± 0,20). È un indizio, ne
     servirebbero ~500.
   - Quanto spesso il campione gioca Switcheroo a vuoto.
   - I comandi da lanciare sul Mac (GIOCATE §6).
9. **Più mazzi.** L'obiettivo lungo è il porting completo delle carte in Rust. Oggi la pagina su Rust copre i cinque
   mazzi fra loro.
10. **Minore.** Lo script di confronto dei profili non attribuisce a D77 15 partite che lo contengono; si guarda se si
    riusa.

## Domande
1. **Come misuriamo l'utilità per Matteo?** Ogni partita è salvata e ogni errore si segnala sul momento. Proposta:
   un numero fisso di partite per matchup, contando vittorie ed "errori evidenti" per partita. Quante partite prima
   di decidere cosa manca?
2. **Priorità.** Fra i punti 1-9, quale ordine? La nostra proposta:
   - prima il punto 1 (è il bot contro cui gioca Matteo, ed è una misura breve sul Mac);
   - poi il 2, trasformando le posizioni delle sue partite in scenari;
   - poi il 4;
   - il 5, il 7 e il 9 quando serve forza in arena.
3. **Su quale profilo si validano le correzioni della valutazione (§7, §8)?** Le arene delle promozioni sono su
   `6427b90`. Le spostiamo su D72-D77 prima di toccare `table_value`? E la rete: riallenarla sul profilo nuovo o
   tenere `ckpt_040000` come prior?
4. **Correzioni da provare per §7 e §8.** Quali per prime, e una alla volta o insieme?
   - rendimento decrescente della Might oltre quella che basta a tenere il campo;
   - la Might in base pesata come minaccia per il turno dopo;
   - un termine per la corsa ai punti quando i campi sono uno a testa;
   - un costo per le reazioni lanciate prima che l'avversario abbia risposto.
5. **`win_probe`.** Lo portiamo nel campione dell'arena (prima va misurato) o resta un aiuto solo per la pagina? Copre
   un caso dell'orizzonte di un turno, non l'orizzonte.
6. **Apertura.** La tabella per matchup vale il costo di misura sul Mac, o basta una regola semplice? La Bo3 con
   sideboard serve davvero a Matteo per allenarsi, o bastano le partite singole?
7. **Difficoltà regolabile nella pagina** (meno iterazioni, o il bot a mano senza prior). È utile ad allenarsi, o
   conta solo il bot più forte?
8. **I fili del 23/11** (mulligan di Sett, Switcheroo, comandi di GIOCATE §6): li chiudiamo, o qualcuno va ancora
   misurato?
9. **Le partite di Matteo come dati.** Ogni posizione dove Matteo segnala un errore, con la mossa che si aspettava,
   diventa uno scenario del pannello "errori evidenti" su cui provare ogni correzione. Ti sembra il modo giusto di
   ancorarci a un umano?
