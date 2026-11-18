# Partite dal vivo su RiftAtlas

Per la sessione che le gioca: le conversazioni precedenti non ci sono più,
qui c'è quello che serve. Prima partita giocata il 17-18/11: lezioni in
`docs/bot/GIUDIZI.md` (G8-G15), checklist e note pratiche in fondo.

## Cosa facciamo
L'utente e Claude giocano insieme contro un amico (giocatore reale), su
RiftAtlas, nel browser del PC dell'utente. L'amico sa che è un test con
Claude. Mazzo dell'utente: Evelynn (`competitive_evelynn.json`). Mazzo
dell'amico il 17/11: Sett (legend The Boss, campione Kingpin; Trifarian
Captain, Call to Glory, Rengar, Rampage, Sabotage); le sue carte si leggono
man mano (testo stampato: `riftbound/data/reference/piltover_archive.json`).

Serve una sessione sul PC dell'utente (app Claude desktop, con Claude in
Chrome o il browser dell'app), aperta nella cartella rbsim aggiornata.

## Come si gioca (concordato)
1. Gioca l'utente. Quando chiede, Claude legge il tavolo e propone la mossa
   col perché, in breve.
2. Claude clicca solo dopo l'ok dell'utente (o clicca l'utente).
3. Il timer non è un problema (detto dall'utente).
4. Claude vede solo quello che vede l'utente: niente mano dell'amico.
5. Si discute: i disaccordi sono la parte utile.
6. A fine partita, con l'ok dell'utente: note in `docs/bot/GIUDIZI.md`
   (situazione → cosa si è fatto e perché, dove eravamo in disaccordo).

## Il mazzo Evelynn in breve (testo stampato, abbreviato)
- Legend Evelynn Agony's Embrace: una volta per turno, quando giochi una carta
  da coperta, peschi 1; se non è il tuo turno, poi scarti 1.
- Campione Evelynn Entrancing (2, M2): Hidden, Backline; giocata da coperta
  nel tuo turno, puoi spostare un'unità nemica da un altro posto (basi
  comprese) al suo campo; quella unità attacca (§466.2.c.1).
- Unità: Bedeviling Stranger ×2 (2, Hidden), Gutter Guardian ×3 (3, Hidden,
  Show Off una carta Hidden → +1 potenza), Pyke Returned ×3 (3, Hidden,
  Backline, Gold esausto quando muore un nemico mentre è a un campo, una
  volta per turno), Reckless Innovator ×3 (3, Accelerate; quando si esaurisce:
  Gold o paga Chaos e pesca), Momentary Companion ×2 (4, Hidden, Temporary
  se giocata nel turno avversario), Vex Apathetic ×2 (4, Deflect; stordisce
  le unità che l'avversario gioca mentre lei è a un campo), Fizz Trickster ×1
  (3+1, rigioca una magia ≤3 dal cimitero), K'Sante Courageous ×2 (5,
  Accelerate, Shield 2, tenendo canalizza 1 runa), Rengar Trophy Hunter ×3
  (5+1, M6, Ambush anche senza tue unità se ci sono nemici).
- Magie: Gust ×1 (1, Reaction, rimanda in mano un'unità ≤3 a un campo), Punch
  First ×2 (1+2, Action, +5), Switcheroo ×2 (2+2, Hidden, Action, scambia le
  Might), Hold 'Em ×3 (3, Action, +3; costa 2 meno se hai giocato un'unità o
  gear su un campo nel turno), Rampage ×2 (3), Star-Crossed ×2 (3+1,
  Reaction, rimanda in mano una tua unità e una nemica).
- Gear: Boots of Swiftness ×2 (Equip Chaos, +2, Ganking), Edge of Night ×2
  (Hidden; da coperta si attacca a una tua unità lì; +2), The Good Stuff ×2
  (Deploy, scarta 1 e pesca 3; se tieni lì torna in mano).
- Campi: Bandle Scouts' Academy (nascondi qui → Gold esausto), Packed
  Amphitheater (campioni qui +1), Rakelstake (prima unità o gear giocata qui
  nel turno → Predict). Rune: 5 Body, 7 Chaos. Sideboard nel file del mazzo.

## Regole già verificate nel motore che contano in partita
- Nascondere costa [rune] e si può solo su un campo che controlli, una carta
  per campo; controllare vuol dire averlo conquistato (un punto).
- Un'unità entra esausta (salvo Accelerate): non si muove nel turno in cui
  la giochi. Da campo a campo serve Ganking.
- Una gear giocata da coperta (Edge of Night) è "giocata lì": conta per
  Rakelstake e Hold 'Em (risposta dell'utente, Q6 di AUDIT.md).
- Un "se" subito dopo il "quando" di un'abilità fa parte della condizione:
  si guarda quando si innesca, non quando si risolve (§383.2.a.1; es.
  Kha'Zix "se un nemico è solo qui").
- Il motore conta i turni di entrambi (turno 3 = il tuo secondo, se inizi).

## Checklist (dopo il 17/11)
- Ogni regola si controlla nel motore o in `docs/rules/CORE_RULES.md` prima di
  dirla (G8). Mai a memoria, nemmeno se sembra ovvia.
- In ogni finestra di reazione, prima di approvare: girare la carta coperta?
  Per la pesca della legend (G9), o perché il campo resterebbe senza unità e
  la coperta andrebbe persa (G11). E il contrario: tenerla, se non è a rischio.
- Scarto della legend: tenere la carta che fa pescare (G12).
- Inizio turno: prima le carte che pescano; Show Off quando c'è (G13).
- Prima di attaccare: quali carte gratis ha l'avversario (Call to Glory con un
  buff da spendere, G14)? Quali protezioni vanno tolte prima (The Boss, G15)?
- I trigger non partono da soli sul simulatore: dopo ogni mossa, controllare
  esaurimenti (Innovator), Gold, pesche, scarti, danni.

## Note pratiche su RiftAtlas (play.riftatlas.com)
- Simulatore manuale: esaurimenti, Gold, pesche, scarti e danni vanno fatti a
  mano. Fa entrare le unità esauste e le esaurisce quando si muovono: con
  Accelerate vanno preparate a mano.
- Clic su carta o runa = esaurisci/prepara (due clic, o due persone che
  cliccano, si annullano). Clic destro su una carta = cimitero; su una runa =
  riciclala. R = Rewind (annulla l'ultima azione).
- Mazzo principale: "Main Deck (D)", in basso a destra. In basso a sinistra c'è
  il mazzo delle rune: cliccarlo canalizza una runa (non pesca).
- Nascondere: passa sopra la carta in mano, "Set card hidden", trascinala sul
  campo. Girarla: "Play from Hidden" sulla carta coperta.
- Gold: "+" della base, "Add Gold token to Base".
- Showdown: Pass (W), End (Q). Catena: Approve (A), Resolve (S).
- Non chiudere dialoghi né cliccare mentre l'utente ha il controllo della
  scheda. Per importare un mazzo: la lista della repo, non quelle salvate.

## Registrazione
Il pannello del log tiene solo gli ultimi ~5 turni. Registratore usato il
17/11: un MutationObserver su `document.body` che legge il pannello, lo
divide in blocchi per "TURN n·NOME" e li salva per stanza (riga "ROOM: XXXXX";
ogni partita di una BO3 ha la sua stanza). Per estrarre il testo: il dump in
un `<main><article>` in sovrimpressione, poi get_page_text.
Da salvare in più, a ogni azione (richiesta dell'utente: tutta
l'informazione pubblica): tavolo con Might, esauste o pronte, buff, equip;
carte coperte per campo e turno in cui sono state nascoste; controllo dei
campi e punteggio; rune per dominio, pronte o esaurite; carte in mano e nel
mazzo (numero); cimiteri; carte rivelate (e da quale effetto); catena con i
bersagli; trigger della legend già usati. La mano dell'utente a parte, come
vista privata di chi decide.
