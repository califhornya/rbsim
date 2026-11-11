# Istruzioni di lavoro

## Contesto
- A inizio sessione leggi STATO.md prima di qualsiasi altra cosa.
- Se STATO.md non esiste, crealo alla prima fase completata.

## Comunicazione in chat
- Niente narrazione dei passaggi. Scrivi solo per: risultati, domande, decisioni da prendere, problemi bloccanti.
- Risposte brevi e dirette. Niente riepiloghi di quello che hai appena fatto.
- Non ristampare codice o contenuti di file in chat: modifica i file e indica quale file e cosa è cambiato in una riga.

## Uso del contesto
- Leggi solo le parti di file che servono (offset/limit, grep), non file interi se non necessario.
- Non rileggere file già letti in questa sessione a meno che non siano cambiati.
- Filtra sempre gli output dei comandi (head, tail, grep, wc). Niente log o dump completi.
- Per test e build mostra solo l'esito e gli errori rilevanti.

## STATO.md
Aggiornalo a fine di ogni fase, sovrascrivendo (non accodando). Contenuto:
- Obiettivo
- Decisioni prese (e perché, una riga)
- Fatto
- In corso
- Prossimi passi
- File principali e a cosa servono

Tienilo sotto le 100 righe.
