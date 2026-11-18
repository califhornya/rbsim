// Registratore per RiftAtlas (play.riftatlas.com). Provato il 18/11 da Claude
// in Chrome su una Solo Room (Goldfish); cosa deve salvare: docs/bot/PARTITA_LIVE.md,
// "Registrazione".
//
// Come viaggia la partita (visto il 18/11): un WebSocket (PartyKit)
//   wss://realtime.riftatlas-workers.com/parties/match/<STANZA>
// In entrata:
//   authoritative_snapshot      stato intero (tavolo, mani, rune, punteggio...), con `sequence`
//   authoritative_patch_commit  una modifica numerata: baseSequence -> sequence, `action`,
//                               patch.operations (set_room_fields, set_player_fields,
//                               zone_insert / zone_remove / zone_reorder, log_insert, ...)
//   room_shell_sync             la stanza (formato, fase, chi c'è)
// In uscita: action_intent (le azioni di chi registra).
// Le zone nascoste arrivano già coperte dal server ("__hidden_zone__:...", isPlaceholder).
//
// Si salva SOLO questo (elenco IN / OUT sotto). Mai: il socket dell'account
// (/parties/account/, manda il token), resume_game (authToken), auth_session,
// ping, presenza. L'indirizzo del socket si salva senza la query.
//
// Quando incollarlo: nella scheda della stanza (/game) appena aperta, PRIMA di
// scegliere i campi. Host Room / Solo Room / Join ricaricano la pagina: incollato
// nella lobby si perde. Il socket già aperto si aggancia al primo invio della
// pagina (un ping ogni ~20 s): status().agganciato. Lo stato intero arriva con
// gli snapshot della preparazione; da lì le modifiche sono numerate e
// status().buchi elenca quelle perse. Pagina ricaricata a metà partita: va
// reincollato, e lo stato intero manca fino al prossimo snapshot.
//
// Uso: __rbRec.status(); __rbRec.export() scarica il JSON (da mettere in
// docs/bot/partite/).
(() => {
  if (window.__rbRec) { console.log("registratore già attivo", window.__rbRec.status()); return; }
  const MATCH = "/parties/match/";
  const IN = new Set(["authoritative_snapshot", "authoritative_patch_commit", "room_shell_sync",
                      "authoritative_resume_ack", "rewind_confirmation_state", "chat_sync"]);
  const OUT = new Set(["action_intent"]);
  const HIDDEN = new Set(["hand", "deck", "runeDeck"]);

  const rec = {
    started: new Date().toISOString(), net: [], log: {}, hooked: 0, me: null,
    room() {
      const m = rec.net.find((x) => x.room);
      return m ? m.room : null;
    },
    status() {
      const patches = [...new Set(rec.net.filter((m) => m.type === "authoritative_patch_commit").map((m) => m.seq))];
      const snaps = rec.net.filter((m) => m.type === "authoritative_snapshot").map((m) => m.seq);
      const last = Math.max(-1, ...patches, ...snaps);
      const from = snaps.length ? Math.min(...snaps) : null;
      const have = new Set(patches), buchi = [];
      if (from !== null) for (let s = from + 1; s <= last && buchi.length < 20; s++) if (!have.has(s)) buchi.push(s);
      return {
        agganciato: rec.hooked > 0, stanza: rec.room(), messaggi: rec.net.length,
        snapshot: snaps.length, ultima: last,
        buchi: from === null ? "manca lo stato intero (nessuno snapshot)" : buchi,
        avversarioScoperto: rec.leaks().length,
        log: Object.fromEntries(Object.entries(rec.log).map(([k, v]) => [k, Object.keys(v).length])),
      };
    },
    // Carte dell'avversario arrivate scoperte in mano o nel mazzo: devono essere 0
    // (lo dice il server). Se non lo sono, non si guarda il file: PARTITA_LIVE, regola 4.
    leaks() {
      if (!rec.me) return [];
      const out = [];
      const check = (pid, zone, cards) => {
        if (pid !== rec.me && HIDDEN.has(zone))
          for (const c of cards || []) if (c && c.isPlaceholder === false) out.push(`${zone}`);
      };
      for (const m of rec.net) {
        if (m.type === "authoritative_snapshot")
          for (const p of m.msg.snapshot.players || []) for (const z of HIDDEN) check(p.id, z, (p.board || {})[z]);
        if (m.type === "authoritative_patch_commit")
          for (const o of m.msg.patch.operations) if (o.op === "zone_insert") check(o.playerId, o.zone, o.cards);
      }
      return out;
    },
    json() {
      return JSON.stringify({ started: rec.started, saved: new Date().toISOString(), me: rec.me,
                              room: rec.room(), net: rec.net, log: rec.log });
    },
    export() {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([rec.json()], { type: "application/json" }));
      a.download = `riftatlas_${rec.room() || "stanza"}_${Date.now()}.json`;
      a.click();
    },
  };
  window.__rbRec = rec;

  // 1. Rete: solo il socket della partita, solo i tipi in IN / OUT.
  const push = (dir, ws, raw) => {
    if (typeof raw !== "string") return;
    let msg;
    try { msg = JSON.parse(raw); } catch { return; }
    if (!(dir === "in" ? IN : OUT).has(msg.type)) return;
    if (dir === "out" && msg.actorPlayerId) rec.me = msg.actorPlayerId;
    if (msg.type === "room_shell_sync" && msg.sessionDoc && msg.sessionDoc.viewer && msg.sessionDoc.viewer.playerId)
      rec.me = rec.me || msg.sessionDoc.viewer.playerId;
    rec.net.push({ t: Date.now(), dir, type: msg.type, seq: msg.sequence ?? null,
                   room: msg.gameInstanceId || null, url: ws.url.split("?")[0], msg });
  };
  const hook = (ws) => {
    if (ws.__rb) return;
    ws.__rb = true;
    if (!String(ws.url).includes(MATCH)) return;
    rec.hooked += 1;
    ws.addEventListener("message", (e) => push("in", ws, e.data));
  };
  const send = WebSocket.prototype.send;
  WebSocket.prototype.send = function (d) {
    hook(this);
    if (String(this.url).includes(MATCH)) push("out", this, d);
    return send.call(this, d);
  };
  const Orig = window.WebSocket;
  window.WebSocket = function (...args) { const ws = new Orig(...args); hook(ws); return ws; };
  window.WebSocket.prototype = Orig.prototype;
  Object.assign(window.WebSocket, { CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3 });

  // 2. Pannello del log (riserva, se la rete ha perso qualcosa): blocchi per
  //    "TURN n·NOME", per stanza; un turno già salvato si aggiorna solo se il
  //    testo nuovo è più lungo (il pannello tiene ~5 turni). Taglia la coda
  //    dell'interfaccia (Chain, CHAT).
  const TURN = /TURN\s+(\d+)\s*[·•]\s*([^\n]+)/g;
  const cut = (s) => { const i = s.search(/\n[▾▴]?\s*Chain\s*\n|\nCHAT\n/); return i < 0 ? s : s.slice(0, i); };
  let timer = null;
  const read = () => {
    timer = null;
    const text = document.body.innerText;
    const room = rec.room() || (text.match(/ROOM:\s*([A-Z0-9]{4,8})/) || [])[1] || "?";
    const marks = [...text.matchAll(TURN)];
    const byTurn = (rec.log[room] = rec.log[room] || {});
    marks.forEach((m, i) => {
      const block = cut(text.slice(m.index, i + 1 < marks.length ? marks[i + 1].index : undefined)).trim();
      const key = `${m[1]}·${m[2].trim()}`;
      if (!byTurn[key] || block.length > byTurn[key].length) byTurn[key] = block;
    });
  };
  new MutationObserver(() => { if (!timer) timer = setTimeout(read, 500); })
    .observe(document.body, { childList: true, subtree: true, characterData: true });
  read();
  console.log("registratore attivo", rec.status());
})();
