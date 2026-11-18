# Il bot negli scenari dell'utente (18/11)

La ricerca di oggi (valutazione scritta a mano di `scripts/diag/handwritten_value.py`,
prior uguali, 100 iterazioni) al posto dell'utente in S6-S9 e S11a/b, fino a
fine turno; l'altro posto gioca simple_trade. Script:
`PYTHONPATH=. python scripts/diag/scenari_bot.py S6,S7,S8,S9,S11a,S11b 100 2`.
Due semi: stesse scelte. Le risposte dell'utente sono in `GIUDIZI.md`.

## Cosa fa il bot, accanto all'utente
| Scenario | Utente | Bot |
|---|---|---|
| S11a | gira la Stranger per cercare Star-Crossed (ha l'energia) | la gira (54% contro 46%, come in S11b: non per la pesca), pesca Star-Crossed ma rimanda in mano First Mate: Pyke muore. Con 400 iterazioni rimanda il Kingpin, come l'utente |
| S11b | niente da fare, tiene la coperta | gira la Stranger (+2 Might sul tavolo, la coperta non vale niente per lui) |
| S8 | gira la Companion sul trigger, poi aspetta con Star-Crossed | gira la Companion (giusto), poi spende Gust, Star-Crossed e Hold 'Em |
| S6 | Stranger all'Academy, Pyke lì, Companion nascosta (9, virtualmente 12) | Stranger all'Academy (giusto), Hold 'Em su una conquista senza nemici, niente Pyke, niente coperta |
| S7 | Faefolk, sempre | Traveling Merchant, poi Punch First a vuoto |
| S9 | riportare unità in base e giocarne il più possibile, prima di Vex | passa subito (100% delle visite) |

## Le cause
Della ricerca (indipendenti dalla valutazione):
1. Una mossa mai provata vale 0 (`net_mcts._puct_select`): quando la posizione
   vale già molto (S9: avanti 4-2, due campi) "passa" non viene mai superata.
   Prova: con il valore della posizione per le mosse non provate, in S9 il bot
   gioca Kha'Zix e usa la legend.
2. Le reazioni hanno un quarto delle iterazioni (25 su 100), divise tra copie
   uguali della stessa magia (Star-Crossed "su BF0" e "su BF1") e tutte le
   coppie di bersagli: a parità vince il primo bersaglio (S11a). Con 400
   iterazioni sceglie bene.
3. Le posizioni a metà turno si valutano con i potenziamenti "questo turno"
   ancora attivi: Punch First e Hold 'Em sembrano guadagni (S6, S7, S9). Il
   motore li fa scadere correttamente (verificato: il Merchant torna a 2).
Della valutazione (dai giudizi dell'utente):
4. Le carte coperte valgono 0: il bot gira la Stranger in S11b e non nasconde
   in S6. Pesca e scarto nel turno avversario lasciano uguale il numero di
   carte: il valore della pesca (S11a) non si vede.
5. Le carte in mano valgono poco (0,03 l'una): in S8 spende tre carte dove
   l'utente ne tiene una pronta.
6. I punti contano in modo lineare (`TEORIA_PUNTI.md`); Faefolk e le altre
   minacce di S10 non hanno un valore proprio.

## Dopo le tre correzioni della ricerca (18/11)
Commit "Search: three faults found in the user's scenarios",
`tests/test_search_fixes.py`. Negli scenari: S11a come l'utente (gira la
Stranger, Star-Crossed sul Kingpin, Pyke vive); S9 non passa più (gioca
Kha'Zix, usa la legend); niente più potenziamenti a vuoto (S6, S7, S8). Restano
i difetti della valutazione: S11b gira la Stranger, S8 spende Gust e
Star-Crossed, S7 non gioca Faefolk, S6 gioca la Companion scoperta e nasconde
Evelynn invece di Pyke scoperto e Companion coperta.

Misura base (`handwritten_value.py 200 100`, 400 partite, 20 minuti):
contro simple_trade 0,80 (prima 0,58; Evelynn 0,82, Kha'Zix 0,78), contro
random 0,97 (prima 0,86); turni vuoti 3% (prima 11%). Non misurato quale
delle tre pesi di più. La stessa ricerca ha prodotto le partite del training
della rete (13/11): è possibile che questi difetti spieghino parte della rete
debole (da verificare, non misurato).

