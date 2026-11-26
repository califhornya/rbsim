# Istruzioni di lavoro

## Contesto
- A inizio sessione leggi STATO.md prima di qualsiasi altra cosa.
- Se STATO.md non esiste, crealo alla prima fase completata.

## Comunicazione in chat
- Niente narrazione dei passaggi. Scrivi solo per: risultati, domande, decisioni da prendere, problemi bloccanti.
- Risposte brevi e dirette. Niente riepiloghi di quello che hai appena fatto.
- Non ristampare codice o contenuti di file in chat: modifica i file e indica quale file e cosa è cambiato in una riga.
- Ricorda sempre a Matteo, alla fine di ogni risposta che chiude un lavoro, come lanciare la pagina (Matteo, 25/11):
  dalla cartella del repo `scripts/allenatore.command` (Mac, anche doppio clic nel Finder) o `scripts\allenatore.bat`
  (Windows); apre http://127.0.0.1:8765. Serve `uv`; con Rust installato (https://rustup.rs) l'estensione si compila
  all'avvio e la pagina gioca sulle regole `6427b90+D72-D82`, senza resta su Python. Se il lavoro è su un ramo non ancora
  unito, prima il `git fetch` + `git checkout` di quel ramo.
- Matteo fa sempre pull dal ramo principale `rust`, non usa altri rami (Matteo, 25/11): quando c'è qualcosa che deve
  lanciare o provare (pagina, `.command`), apri la PR verso `rust` senza aspettare che la chieda; lui la unisce.
- Matteo non usa il doppio clic sui `.command`: dagli sempre il comando completo da incollare nel Terminale
  (`cd ~/projects/rbsim2026/rbsim-rust && git checkout rust && git pull && bash scripts/...`).

- I file per Astra (domande, note) non vanno mai nel repo né su GitHub (Matteo, 26/11): un file nella scratchpad,
  mandato a Matteo con SendUserFile; lui lo porta ad Astra.

## Uso del contesto
- Leggi solo le parti di file che servono (offset/limit, grep), non file interi se non necessario.
- Non rileggere file già letti in questa sessione a meno che non siano cambiati.
- Filtra sempre gli output dei comandi (head, tail, grep, wc). Niente log o dump completi.
- Per test e build mostra solo l'esito e gli errori rilevanti.

## Divisione del lavoro (Matteo, 25/11)
- Il modello principale progetta, scrive specifiche brevi e controlla i risultati.
- Il lavoro meccanico (scrivere codice da una specifica, test, verifiche, partite di prova) va a subagenti Sonnet con sforzo medio, con output già filtrato.

## STATO.md
Aggiornalo a fine di ogni fase, sovrascrivendo (non accodando). Contenuto:
- Obiettivo
- Decisioni prese (e perché, una riga)
- Fatto
- In corso
- Prossimi passi
- File principali e a cosa servono

Tienilo sotto le 100 righe.
