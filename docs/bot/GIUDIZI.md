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
- (18/11, utente e revisione esterna) I principi astratti, riletti a freddo, si
  capiscono poco: ogni principio va con la partita e il turno in cui è
  successo, e diventa uno scenario giocabile appena si può. Una mossa si
  giudica prima di vedere la pesca; l'esito (cosa è stato pescato) si scrive
  a parte. Per una mossa che vale per la pesca, preparare la coppia di casi:
  trigger della legend disponibile / già usato in questo turno.

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
`docs/bot/risposte_scenari.jsonl` (dal 18/11 anche: le opzioni e la mano a ogni
mossa, la prima mossa considerata e scartata, cosa farebbe cambiare scelta, e
a parte l'esito, cioè cosa è successo dopo la prima decisione). I testi:
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
- Risposta a S8 (18/11, in chat): gira Momentary Companion in risposta al
  trigger di Kha'Zix: 7 contro 6 (Pyke 3 + Companion 4, Kha'Zix 4 + 2). Il +2
  lui lo prende comunque (la condizione si guarda quando si innesca), quindi
  ora o nello showdown cambia poco. Poi aspetta la sua mossa, tenendo
  Star-Crossed con le rune aperte e la pesca di Evelynn: "non sto male".
  Seguiti (in chat). S8.1, lui Punch First su Kha'Zix (11 contro 7):
  Star-Crossed rimanda in mano Kha'Zix, "fortuna perché spreca Punch First".
  S8.2, lui Rengar con Ambush (12 contro 7): Star-Crossed rimanda in mano
  Rengar, non Kha'Zix: "Kha'Zix lo voglio uccidere, più scomodo". In tutti e
  due l'unità amica rimandata in mano è la Stranger dalla base (confermato),
  così all'Academy restano 7 contro 6; senza quel bersaglio "dipende". S8.3 era
  una domanda sbagliata di Claude: a 7 contro 6 Kha'Zix assegna 6 danni e la
  Companion muore nel combattimento (Pyke ha Backline, §826.3: il danno
  letale va prima alle altre unità), non a inizio turno per Temporary.
  Ancora G8: il combattimento si calcola, non si immagina.

## Partite dal vivo su RiftAtlas (17-18/11)
Evelynn contro Sett (legend The Boss, Kingpin). Partita 1 (stanza HN5VE):
gioca Claude, l'utente corregge; persa, concessa sul 3-5 al turno 9. BO3:
gioca l'utente; G1 (FC3TX) interrotta al turno 6, G2 (VZUFX) vinta, G3
(TYASM) finita sul 7-7 al turno 15. Log turno per turno e foto del tavolo
finale della G3 in `docs/bot/partite/`. Giudizi dati dall'utente in chat:

- G8. Regole sempre dal motore o da `docs/rules/CORE_RULES.md`, mai a
  memoria. Errori fatti a memoria: Deploy si gioca su qualsiasi campo
  (§830.1.b); la mossa standard esaurisce l'unità (§144.2: scatta "quando mi
  esaurisco" di Reckless Innovator); la cleanup del combattimento cura tutte
  le unità (§468.1.a.1, §143.3.b.2); "Add [Rune]" (Show Off di Gutter
  Guardian, Gold) dà 1 potenza da spendere, non una runa; nell'Ending Phase
  non c'è priorità (§317): nel turno avversario si reagisce solo a una sua
  azione in catena o in uno showdown.
- G9. Con Evelynn una carta nascosta è anche una pesca a velocità reazione
  (legend: la prima carta giocata da coperta nel turno fa pescare 1; nel
  turno avversario poi si scarta 1). Senza risposte in mano, girarla per
  vedere una carta e cercare l'out, anche se il suo effetto non fa niente.
  Esempio: G3 turno 7. Sabotage rivela la mano (Punch First ×2, Rengar,
  Hold 'Em, Rebuke) e ricicla Rebuke (Action: nel turno di lui si giocherebbe
  solo in uno showdown); in mano nessuna reazione. Poi Rampage su Pyke
  a un campo dove l'utente ha altre unità e Bedeviling Stranger coperta.
  L'utente gira la Stranger (nessun bersaglio) solo per pescare: arriva
  Star-Crossed (scarta Hold 'Em), che rimanda in mano il Kingpin e la
  Stranger stessa, rinascosta al turno 8. Rampage va a vuoto, Pyke resta.
- G10. Lo stesso in generale: una carta vale per tutto quello che mette in
  moto (trigger di altri pezzi, il corpo come bersaglio o costo, carte
  viste), non solo per il suo testo. Esempi: Fizz rigioca Star-Crossed e
  rimanda in mano se stesso (G3 turno 12); Innovator riportato in base solo
  per il Gold (G3 turno 10); Trifarian Captain come ricerca nel mazzo; una
  gear Deploy su un campo che cadrà vale comunque per l'effetto all'ingresso
  (The Good Stuff: "scarta 1, pesca 3"; Pillaged Armory: il buff);
  Discipline (Reaction, +2 Might, pesca 1) giocata solo per pescare quando
  il +2 non serve, anche su un'unità nemica se è l'unico bersaglio.
- G11. Una rimozione che lascia un campo senza tue unità fa perdere anche la
  carta coperta lì (§190.4.c, §107.3.d): girala in risposta finché la
  rimozione è in catena. Esempio sbagliato: partita 1 turno 8. Rampage
  (Rengar contro K'Sante, da solo al Monastery con Pyke coperto): Claude
  stava per approvare guardando solo l'effetto di Pyke, che non salvava
  K'Sante; l'utente l'ha fermato. Diverso da G9: lì il campo aveva altre
  unità e la coperta non era a rischio.
- G12. Scarto della legend con la mano corta: tenere la carta che fa pescare.
  Partita 1 turno 8, due carte in mano: Claude scarta The Good Stuff,
  giusto era scartare Star-Crossed.
- G13. Ordine nel proprio turno: prima le carte che pescano (The Good Stuff a
  inizio turno), poi il resto; Gutter Guardian sempre con Show Off se c'è
  una carta Hidden da mostrare (partita 1 turno 9, tutte e due mancate).
- G14. Le carte gratis dell'avversario contano: Call to Glory costa 0 se
  spende un buff, su qualsiasi sua unità. Un'unità piccola non è un
  bersaglio sicuro se lui ha un buff in giro. Partita 1 turno 5: Innovator
  (3) mosso contro Trifarian Captain (1, il suo buff già speso al turno 4);
  Call to Glory gratis spendendo il buff del Kingpin: Captain a 4, Innovator
  muore (e Claude aveva dimenticato il Gold dell'Innovator mosso).
- G15. Prima togli la protezione, poi colpisci. G2 turno 5: Innovator dalla
  base alla Valley of Idols, contro Captain e Kingpin (muovere esaurisce:
  Gold). Nello showdown, con la priorità, Switcheroo tra Innovator e
  Kingpin: Kingpin 3, Innovator 8, il campo si pulisce. The Boss salva il
  Kingpin in base (spende il suo buff, la legend si esaurisce), ma resta 3
  (gli effetti "questo turno" seguono l'unità). Rampage lo uccide:
  Innovator, ancora 8 e curato dalla cleanup del combattimento, fa il danno.

Dalla revisione esterna (GPT, 18/11), da tenere: considerare anche quando NON
girare la coperta. Se l'unità colpita è sacrificabile e la coperta non è a
rischio, tenerla per uno showdown dopo può valere di più: rinasconderla costa
1 potenza nel proprio turno e la carta torna utilizzabile solo dal turno dopo.

Scenari da questa sezione (in `scenari.json`, si giocano sulla pagina):
- S11a. G3 turno 7, ricostruito dal turno 1 con le mosse del log e il mazzo
  di Ksword (`competitive_sett.json`, la sua lista del 18/11). Rampage in
  catena (Kingpin 6 contro Pyke), Rebuke riciclata da Sabotage, Stranger
  coperta, 3 energia aperta: cosa fai, prima di sapere cosa peschi?
- S11b. La stessa posizione, con il trigger di Evelynn già usato nel turno
  (girare la Stranger non fa pescare). La differenza tra le due risposte dice
  quanto vale la pesca e quanto il resto.
- Risposte (18/11, in chat; in `risposte_scenari.jsonl`). S11a: gira la
  Stranger "proprio perché ho 3 energy open": con l'energia per pagarla cerca
  l'ultima spiaggia, Star-Crossed; senza, "è come aver perso". Vede la pesca
  e poi decide. S11b: "non posso fare niente": passa e tiene la coperta (il
  campo ha l'Innovator, non è a rischio). Quindi qui la Stranger girata vale
  solo per la pesca, e la pesca vale perché c'è l'energia per l'out.
Nella G3 i due avevano cambiato carte dal sideboard: entrate Sabotage e
Decree of Unity (Ksword) e Rebuke (utente); le uscite non si sanno, negli
scenari escono Showstopper, Call to Glory e Switcheroo (conta solo per le
carte nascoste nei mazzi).
