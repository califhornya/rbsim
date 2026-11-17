# Partita dal vivo su RiftAtlas (sera del 17/11)

Per la sessione che la gioca: questa conversazione non c'è più, qui c'è
quello che serve.

## Cosa facciamo
L'utente e Claude giocano insieme contro un amico (giocatore reale), su
RiftAtlas, nel browser del PC dell'utente. L'amico sa che è un test con
Claude. Mazzo dell'utente: Evelynn (`competitive_evelynn.json`). Mazzo
dell'amico: non noto, probabilmente non Kha'Zix; le sue carte si leggono man
mano (testo stampato: `riftbound/data/reference/piltover_archive.json`).

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
