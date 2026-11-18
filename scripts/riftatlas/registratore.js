// Registratore per RiftAtlas (play.riftatlas.com). BOZZA del 18/11: scritta
// senza poter aprire la pagina (sessione cloud), da provare nella prossima
// sessione sul PC dell'utente. Cosa deve salvare: docs/bot/PARTITA_LIVE.md,
// "Registrazione".
//
// Si incolla nella console della scheda della partita (o la esegue Claude in
// Chrome). Due fonti, tenute separate:
//  1. rete: ogni messaggio WebSocket in entrata e in uscita. Se RiftAtlas
//     sincronizza la partita così, lì c'è lo stato strutturato (tavolo, Might,
//     esauste, buff, coperte, rune, conteggi; la mano solo di chi registra),
//     senza indovinare l'HTML. Da verificare: che usi WebSocket e cosa manda.
//  2. pannello del log: il testo, diviso per "TURN n·NOME", con la stanza
//     ("ROOM: XXXXX"), come il registratore usato il 17/11. Il pannello tiene
//     solo gli ultimi ~5 turni: si salva man mano.
// Un'istantanea del tavolo dall'HTML (fonte 3) va scritta guardando la pagina,
// solo se la rete non basta.
//
// Uso: __rbRec.status() conta cosa c'è; __rbRec.export() scarica un file JSON
// (rete + log) da mettere in docs/bot/partite/.
(() => {
  if (window.__rbRec) { console.log("registratore già attivo", window.__rbRec.status()); return; }
  const rec = {
    started: new Date().toISOString(), net: [], log: {}, sockets: 0,
    status() {
      return { net: rec.net.length, sockets: rec.sockets,
               log: Object.fromEntries(Object.entries(rec.log).map(([k, v]) => [k, Object.keys(v).length])) };
    },
    export() {
      const blob = new Blob([JSON.stringify({ started: rec.started, saved: new Date().toISOString(),
                                              net: rec.net, log: rec.log }, null, 1)],
                            { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `riftatlas_${rec.room() || "stanza"}_${Date.now()}.json`;
      a.click();
    },
    room() { const m = document.body.innerText.match(/ROOM:\s*([A-Z0-9]{4,8})/); return m ? m[1] : null; },
  };
  window.__rbRec = rec;

  // 1. Rete. Le connessioni già aperte si agganciano al loro prossimo invio.
  const hook = (ws) => {
    if (ws.__rb) return;
    ws.__rb = true; rec.sockets += 1;
    ws.addEventListener("message", (e) => rec.net.push({ t: Date.now(), dir: "in", url: ws.url,
      data: typeof e.data === "string" ? e.data : `[binario ${e.data.size ?? e.data.byteLength} byte]` }));
  };
  const send = WebSocket.prototype.send;
  WebSocket.prototype.send = function (d) {
    hook(this);
    rec.net.push({ t: Date.now(), dir: "out", url: this.url, data: typeof d === "string" ? d : "[binario]" });
    return send.call(this, d);
  };
  const Orig = window.WebSocket;
  window.WebSocket = function (...args) { const ws = new Orig(...args); hook(ws); return ws; };
  window.WebSocket.prototype = Orig.prototype;
  Object.assign(window.WebSocket, { CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3 });

  // 2. Pannello del log: blocchi per turno, per stanza; un turno già salvato
  //    si aggiorna solo se il testo nuovo è più lungo (il pannello lo taglia).
  const TURN = /TURN\s+(\d+)\s*[·•]\s*([^\n]+)/g;
  let timer = null;
  const read = () => {
    timer = null;
    const text = document.body.innerText, room = rec.room() || "?";
    const marks = [...text.matchAll(TURN)];
    const byTurn = (rec.log[room] = rec.log[room] || {});
    marks.forEach((m, i) => {
      const block = text.slice(m.index, i + 1 < marks.length ? marks[i + 1].index : undefined).trim();
      const key = `${m[1]}·${m[2].trim()}`;
      if (!byTurn[key] || block.length > byTurn[key].length) byTurn[key] = block;
    });
  };
  new MutationObserver(() => { if (!timer) timer = setTimeout(read, 500); })
    .observe(document.body, { childList: true, subtree: true, characterData: true });
  read();
  console.log("registratore attivo", rec.status());
})();
