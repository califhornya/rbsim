# Giudizi dell'utente per il bot

Raccolti rispondendo a situazioni concrete (formato: situazione → cosa fai
e perché). Servono a scrivere la valutazione del bot dentro la ricerca che
c'è già, e come situazioni di prova. Mazzi: i due competitive (Kai'Sa,
Kennen).

## Lezione sul metodo
- I confronti astratti tra posizioni ("5-3 con 2 carte in mano contro 3-3
  con 4") l'utente non li sa giudicare senza altre informazioni: il valore
  di una posizione dipende dai mazzi e dalle carte, non da conteggi
  generici. Il bot va pensato per mazzo, non con pesi uguali per tutti.
- Le situazioni concrete funzionano: risposte ricche, con il perché.

## Giudizi (13/11, primo gruppo)

Kennen:
- G1. Il cimitero è il motore del mazzo (Rhasa costa meno, FLOW, Last
  Rites, Fizz): riempirlo ha valore. BURN 2 di Kennen e il resto di
  Lightning Rush contano come guadagno.
- G2. Riciclare una runa (de-ramp) è un costo; con Seal of Discord in campo
  pesa meno, perché il Seal paga poi la potenza Chaos.
- G3. Contro Kai'Sa, Kennen (forza 4) muore a Falling Star al secondo turno
  di lei: giocarlo restando senza rune aperte è un rischio grosso.
- G4. Nocturne Horrifying è un bersaglio: le carte che guardano in cima al
  mazzo (Lightning Rush 3, Trifarian Captain 4) servono anche a trovarlo e
  giocarlo per una runa. Contare i Nocturne già visti (3 nel mazzo): se
  Lightning Rush ne ha mostrati 2, cercare il terzo con Captain vale poco;
  se ne ha mostrati 0, vale di più.
- G5. Sequenza: una runa esaurita per energia si può poi riciclare per la
  potenza del Seal; l'energia resta e paga Lightning Rush. (Il motore lo
  permette: `Player.recycle_rune` / `runes_left_play`.)
- G6. Mano senza giocate economiche (es. Rhasa, Star-Crossed, Rebuke, Last
  Rites, Hard Bargain da secondo): partita quasi persa; giocare Kennen anche
  se morirà è meglio di non fare niente. È il caso "va fatto per forza".

Kai'Sa:
- G7. Uccidere Kennen con Falling Star al proprio secondo turno è una
  giocata enorme: toglie il campione a chi ha anche riciclato una runa, e
  con le 2 rune rimaste Noxus Hopeful costa 2 (LEGION). "Avantissimo."

## Situazioni di prova (con la risposta dell'utente)
- S1a. Kennen secondo, primo turno, 3 rune (2 Chaos, 1 Order), Kai'Sa ha
  Plundering Poro in base. Mano: Seal of Discord, Trifarian Captain,
  Traveling Merchant, Lightning Rush, Star-Crossed. → Seal, con l'energia
  della runa riciclata Lightning Rush cercando Nocturne (pagato col Seal);
  le 2 rune rimaste per Merchant, o Captain se Lightning Rush non ha
  mostrato Nocturne. Kennen possibile ma esposto a Falling Star.
- S1b. Come S1a, mano: Traveling Merchant, Trifarian Captain, Gust, Rhasa,
  Edge of Night. → Trifarian Captain sperando in Nocturne; Kennen no
  (contro Kai'Sa, senza rune aperte, è in pericolo).
- S1c. Come S1a, mano: Rhasa, Star-Crossed, Rebuke, Last Rites, Hard
  Bargain. → Kennen (meglio di niente), partita quasi persa.
- S2. Kai'Sa, secondo turno, 4 rune (2 Fury, 2 Mind), Poro in base; Kennen
  avversario in base (giocato al suo primo turno). Mano: Falling Star,
  Noxus Hopeful, Stupefy, Lecturing Yordle, Hextech Ray. → Falling Star su
  Kennen, poi Noxus Hopeful scontato.
