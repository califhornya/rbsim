# La teoria dei punti (ricerca sul web, 18/11)

Chiesta dall'utente: "la teoria dei numeri di punti è importantissima in
Riftbound" (risposta a S9). Fonti: guide della comunità, elencate in fondo; le
pagine intere non erano leggibili dalla sessione cloud (rete bloccata), quindi
questa sintesi viene dagli estratti dei motori di ricerca. Da confermare e
correggere con l'utente: conta il suo giudizio, non le guide.

## La regola da cui nasce
§473.1.b: se una conquista darebbe il punto finale (da 7 a 8), lo dà solo se
in quel turno hai segnato tutti i campi; altrimenti peschi una carta. Tenere
un campo (a inizio turno) e i punti dalle carte non hanno questo limite. Ogni
campo si segna una volta per turno, conquistandolo o tenendolo. Il motore la
applica (`riftbound/core/loop.py`, "The Final Point").

## Due piani (nomi informali, le guide non concordano sui termini)
- Pari ("Conqueror", "playing on evens"): 2, 4, 6, poi entrambi i campi nello
  stesso turno. Da 6: due conquiste (7 e 8), oppure tenerne uno (7) e
  conquistare l'altro (8). A 7 una sola conquista non basta: servono comunque
  tutti e due i campi, quindi per chi gioca così il 7 vale poco più del 6.
- Dispari ("Holder"): arrivare a 7 e vincere tenendo un campo durante il turno
  avversario, cioè all'inizio del proprio turno; tenere i campi lascia
  l'avversario sui dispari (3, 5, 7).

## Conseguenze pratiche (dalle guide)
- Non sempre conviene segnare. Per chi gioca sui pari, da 4 a 5 spreca
  risorse: serve comunque arrivare a 6 prima della spinta finale. Da 6 a 7
  vale poco per lo stesso motivo.
- Non scambiare un'unità per un punto dispari; se l'avversario ti ha spinto
  su un dispari, torna su un pari (una conquista invece di due, o una tenuta).
- Chi gioca sui pari può lasciare che l'avversario riprenda un campo, pur di
  restare pari.
- Dalla parte di chi difende: costringere l'avversario a spendere per
  riprendersi un campo riduce le risorse che avrà per riprenderli a 7.
  Togliergli i pari è un obiettivo.
- Zona letale da 6: con l'avversario a 6, va considerato che possa vincere al
  turno dopo. A 7, una tenuta vince.
- Dentro la zona letale, un punto che non vince vale poco ("vanity"); uno
  scambio di unità per negare il punto vincente spesso conviene.
- Variante (TCGplayer): "playing on odds" non significa inseguire i dispari,
  ma tenere le rune aperte, costringere l'avversario a giocare intorno alle
  reazioni ed evitare showdown di unità piccole quando si spenderà tutto.

## Cosa cambia per il bot
La valutazione di oggi (`scripts/diag/handwritten_value.py`) pesa la
differenza di punti in modo lineare (0,45 per punto): 5-3 vale come 4-2. Da
sistemare:
- il valore di un punteggio dipende dal piano del mazzo: un punto dispari
  vale poco (o meno di niente, se costa un'unità) per chi gioca sui pari;
- la minaccia: avversario a 6 o 7, quanti campi controlla, se può segnarli
  tutti nel turno;
- quante tenute sono in arrivo (campi controllati a fine turno avversario).
Da chiedere all'utente: Evelynn e Kha'Zix giocano sui pari o sui dispari, e
quando si cambia piano?

## Fonti
- [riftbound.gg, The In-Depth Guide to Scoring](https://riftbound.gg/the-in-depth-guide-to-scoring-in-riftbound/)
- [TCGplayer, You Are Scoring Points Wrong In Riftbound](https://www.tcgplayer.com/content/article/You-Are-Scoring-Points-Wrong-In-Riftbound/666ffa6d-19a8-4893-b0f8-a0d20ffa8bd3/)
- [Tacter, 4 Questions Every Turn](https://www.tacter.com/riftbound/guides/4-questions-every-turn-1c09476a)
- [Learn Riftbound, Lethal Points](https://learnriftbound.gg/learn/intermediate/06-lethal-points)
- [Riftbound Zone, Lethal Points](https://riftbound.zone/en/guide/lethal-points-in-riftbound/)
- [Riftbound Zone, Win Conditions](https://riftbound.zone/en/guide/riftbound-win-conditions/)
- [Riftbound TCG Wiki, Win Conditions](https://riftboundtcg.wiki/guide/riftbound-tcg-win-conditions)
- [Dani Reon, How to Win Riftbound](https://www.danireon.com/en-us/blogs/news/how-to-win-riftbound-scoring-system-win-conditions)
- [Riftpocket, Conquer and Hold](https://riftpocket.com/blog/how-to-win-riftbound-scoring/)
- [Runeweave, Scoring](https://runeweave.com/rules/scoring)
- [riftbound.org, Final Point](https://riftbound.org/learn/how-to-play/final-point)
