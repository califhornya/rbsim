# Giudizi dell'utente per il bot

Raccolti rispondendo a situazioni concrete (formato: situazione → cosa fai
e perché). Servono a scrivere la valutazione del bot dentro la ricerca che
c'è già, e come situazioni di prova. Mazzi: dal 17/11 Evelynn e Kha'Zix
(`competitive_evelynn`, `competitive_khazix`); i giudizi su Kai'Sa e Kennen
(sotto) restano come storico, i due mazzi non si giocano più (ban).

## Lezione sul metodo
- I confronti astratti tra posizioni ("5-3 con 2 carte in mano contro 3-3
  con 4") l'utente non li sa giudicare senza altre informazioni: il valore
  di una posizione dipende dai mazzi e dalle carte, non da conteggi
  generici. Il bot va pensato per mazzo, non con pesi uguali per tutti.
- Le situazioni concrete funzionano: risposte ricche, con il perché.

## Kai'Sa e Kennen (storico): giudizi (13/11, primo gruppo)

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

## Kai'Sa e Kennen (storico): situazioni di prova (con la risposta)
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

## Kai'Sa e Kennen (storico): secondo gruppo, mai risposto
Due campi (il tuo e il suo), effetti dei campi non rilevanti, si vince a 8.
- S3. Tu Kennen, turno 5, 3-3. 6 rune e Seal in campo. Tu controlli il tuo
  campo con Traveling Merchant (2), lei il suo con Noxus Hopeful (4).
  Kennen in base, pronto. Lei: 4 carte in mano, 6 rune aperte. Mano:
  Nocturne Horrifying, Star-Crossed, Ride the Wind, Lightning Rush.
- S4. Tu Kai'Sa, sotto 5-6, tuo turno. 8 rune (4 Fury, 4 Mind). Lui
  controlla il suo campo con Kennen (4) e Traveling Merchant (2): al suo
  turno lo tiene e va a 7. Tu controlli il tuo con Noxus Hopeful (4),
  pronto. Lui: 3 carte in mano. Mano: Singularity, Brynhir Thundersong,
  Falling Star, Hextech Ray, Thousand-Tailed Watcher.
- S5. Tu Kennen, turno 4, avanti 3-2. Lei senza unità in campo, 2 carte in
  mano, 5 rune aperte; il suo campo è vuoto. Il tuo è presidiato da
  Bedeviling Stranger (2). In base: Trifarian Captain (1) e Traveling
  Merchant (2), pronti. Conquistare il suo campo con tutti e due, uno,
  nessuno? (Interessa quanto si rischia.)

## Evelynn e Kha'Zix: primo gruppo (17/11, in attesa di risposta)
S6-S9 si giocano sulla pagina degli scenari (`scripts/scenari.bat` o
`scenari.command`, doppio clic): la posizione è costruita con mosse vere
(`docs/bot/scenari.json`, controllata da `tests/test_scenari.py`), giochi tu
il turno e scrivi il perché; le risposte vanno in
`docs/bot/risposte_scenari.jsonl`. I testi:
- S6. Sei Evelynn, primo giocatore, all'inizio del tuo secondo turno (0-0).
  Bedeviling Stranger è in base, pronta; lui ha Traveling Merchant in base.
  Cosa fai in questo turno, e perché? (È il turno 3 della partita: i turni si
  contano per giocatore.)
- S7. Sei Kha'Zix, secondo giocatore, al tuo primo turno (0-0). Lei ha
  Bedeviling Stranger in base: al suo prossimo turno può portarla all'Academy,
  conquistarla, nasconderci una carta e prendere un Gold. Cosa giochi,
  pensando al suo turno dopo? (Turno 2 della partita.)
- S8. Sei Evelynn, nel suo quarto turno, 3-3. All'Academy hai Pyke da solo e
  Momentary Companion nascosta; Bedeviling Stranger è in base. Lui ha appena
  mosso Kha'Zix Mutating Horror dalla base al tuo campo («quando attacco o
  difendo, se un nemico è solo qui, +2 Might e 2 XP»): tocca a te. Cosa fai, e
  in che momento? (Turno 8 della partita.)
- S9. Sei Kha'Zix, al tuo quarto turno, 4-2. Con Grim Resolve Zed ha appena
  conquistato l'Academy ed è lì esausto (8 di Might fino a fine turno); lo
  Shadow Clone è in base. Hai 3 XP e la leggenda pronta; lei ha Vex in base e
  4 carte in mano. Spendi 2 XP per riportare Zed in base, 1 XP per il Buff, o
  li tieni? Perché? E il resto del turno? (Turno 7 della partita.)
- S10. Domanda sulle carte, non sulle posizioni: con Evelynn, quali carte di
  Kha'Zix temi di più e come giochi intorno? E con Kha'Zix, quali di Evelynn?
