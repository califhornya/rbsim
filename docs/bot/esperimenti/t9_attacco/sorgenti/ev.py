import argparse
import copy
import json
import pickle
import random
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from exact import Plan
from riftbound.core.state import determinize
from riftbound.rs import decisione_esp as E, decisione_rs as D, vista_rs
from riftbound.rs.canon import Canon

folder = Path(__file__).resolve().parent
P, root = pickle.load((folder / "position.pkl").open("rb"))
base = P["seed"] * 100_003 + 10 * 1009
original_raw = None
def start_tree(mode, seed):
    rng = random.Random(seed)
    if mode == "fisse":
        state = copy.deepcopy(root)
        for side in ("A","B"):
            pl = state["root"][side]["$v"]
            deck = pl["deck"]["$v"]
            assert not deck["known_top"]
            rng.shuffle(deck["cards"])
            rd = pl["rune_deck"]["$v"]
            n = rd["unseen"] if rd["unseen"] is not None else len(rd["runes"])
            first = rd["runes"][:n]
            rng.shuffle(first)
            rd["runes"][:n] = first
        return state
    global original_raw
    if original_raw is None:
        original_raw = json.loads(E.gioco(P, root, 0).raw_dump())
    c = Canon()
    state = c.canonical(original_raw)
    gs, objects = vista_rs.carica(original_raw)
    to_ref = {id(obj): "#"+c.ids[rid] for rid,obj in objects.items() if rid in c.ids}
    runes = {}
    original_cards = {}
    for side,pl in (("A",gs.A),("B",gs.B)):
        player = state["root"][side]["$v"]
        assert not player["deck"]["$v"]["known_top"] and not player["hand_public"]
        runes[side] = {id(r):x for r,x in zip(pl.rune_deck.runes, player["rune_deck"]["$v"]["runes"])}
        slots = [fd.card for bf in gs.battlefields for fd in bf.facedowns if fd.owner==side]
        original_cards[side] = sorted(to_ref[id(o)] for o in pl.hand+pl.deck.cards+slots)
    before = [(fd.owner,fd.turn_hidden) for b in gs.battlefields for fd in b.facedowns]
    fixed = [to_ref[id(x)] for x in gs.B.hand]
    determinize(gs,"B",rng)
    assert before == [(fd.owner,fd.turn_hidden) for b in gs.battlefields for fd in b.facedowns]
    assert fixed == [to_ref[id(x)] for x in gs.B.hand]
    for side,pl in (("A",gs.A),("B",gs.B)):
        player = state["root"][side]["$v"]
        player["hand"] = [to_ref[id(x)] for x in pl.hand]
        player["deck"]["$v"]["cards"] = [to_ref[id(x)] for x in pl.deck.cards]
        player["rune_deck"]["$v"]["runes"] = [runes[side][id(r)] for r in pl.rune_deck.runes]
        slots = [fd.card for bf in gs.battlefields for fd in bf.facedowns if fd.owner==side]
        assert original_cards[side] == sorted(to_ref[id(o)] for o in pl.hand+pl.deck.cards+slots)
    for i,bf in enumerate(gs.battlefields):
        for fd,dest in zip(bf.facedowns,state["objs"]["bf"+str(i)]["facedowns"]):
            if fd.owner=="A":
                assert fd.card.has_keyword("HIDDEN")
                dest["$v"]["card"]=to_ref[id(fd.card)]
    return state

class Release(Exception): pass
class Turn:
    def __init__(self,kind):
        self.kind=kind
        self.stage=0
        self.resumed=None
        self.complete=False
        self.reason=None
        self.attack=None if kind=="valley" else (Plan("Kinkou","reported",True,"Reckless") if kind=="matteo" else Plan("Sett Kingpin","early",False,"Momentary"))
    def release(self,e,done,why=None):
        self.resumed=e["state_raw"]
        self.complete=done
        self.reason=why
        raise Release()
    def ask(self,event):
        e=json.loads(event)
        if self.attack is not None:
            p=self.attack
            if e["k"]=="decision" and e.get("point")=="turn_action":
                if p.stage==2 and p.closed:
                    self.release(e,p.vi and p.stun is not None,"mancata AMBUSH/stun" if not(p.vi and p.stun) else None)
                if p.stage==1 and p.closed and "Move Sett Kingpin base→BF0" not in e["menu"]:
                    self.release(e,False,"secondo attacco impedito")
                if p.gear and p.stage==0 and "Move Kinkou Initiate base→BF0" not in e["menu"]:
                    self.release(e,False,"primo attacco impedito")
            return p.ask(event)
        if e["k"]=="decision":
            m=e["menu"]; idx=next((i for i,z in enumerate(m) if z.startswith("Pass")),0)
            if e["point"]=="turn_action":
                seq=("Play Vi Peacekeeper","Move Sett Kingpin base→BF1","Pass")
                if self.stage==len(seq): self.release(e,True)
                label=seq[self.stage]
                if label not in m: self.release(e,False,label)
                self.stage+=1; return m.index(label)
            return idx
        if e["k"]=="choice":return e["default"]
        if e["k"]=="decide_optional":return True
        if e["k"]=="decide_mode":return None
        if e["k"]=="decide_mulligan":return []
        if e["k"]=="decide_predict_recycle":return False
        raise ValueError(e["k"])
    def watch(self,ev):
        if self.attack is None or '"k":"decision"' not in ev[:60]:return
        d=json.loads(ev)
        a=self.attack
        if a.stage==1 and a.closed and d.get("seat")=="A" and d.get("point")!="turn_action" and (d.get("win") or {}).get("showdown")==0 and d.get("action") and d["action"][0]!="PASS":
            a.reply=True

def setup(g,seed):
    for side in ("A","B"):
        E._agente_campione(g,P,side,seed*2+(side=="B")+1_000_003)
    g.set_side_chooser()
def table(g):
    raw=json.loads(g.raw_dump())
    p=D.riassunto(raw,"B")
    return {"points":p["punti"],"t":p["turno"],"fields":[f["controlla"] for f in p["campi"]],"theirs":[v[0] for v in p["campi"][0]["avversario"]["unita"]],"ours":[v[0] for v in p["campi"][0]["campione"]["unita"]],"base_B":[v[0] for v in p["base"]["campione"]["unita"]]}
def finish(st,kind,i,mode,controller=None):
    seed=base+i
    fd_field = st["objs"]["bf0"]["facedowns"]
    facedown=st["objs"][fd_field[0]["$v"]["card"][1:]]["name"] if fd_field else None
    g=E.gioco(P,st,seed)
    E._agente_campione(g,P,"A",seed*2+1_000_003)
    turn=Turn(kind) if controller is None else controller
    g.set_human_agent("B",turn.ask,False,None);g.set_side_chooser()
    if turn.attack is not None:g.trace_on(turn.watch)
    try: w=g.run_actions_end()
    except Release:
        # At a clean main-phase action. This is the project's handoff protocol.
        g=E.gioco(P,E.albero(turn.resumed),seed+555)
        setup(g,seed)
        w=g.run_actions_end()
    end9=table(g)
    assert w is not None or end9["t"]==10
    if w is None:
        setup(g,seed+7411)
        w=g.run_begin()
    start10=E._punti(json.loads(g.raw_dump()))
    if w is None:w=g.run_actions_end()
    end10=E._punti(json.loads(g.raw_dump()))
    r=E._finisci(g,P,w,i,time.time(),end10)
    assert r["vince"] in ("A","B","DRAW")
    return {"world":i,"set":mode,"line":kind,"face":facedown,"prefix_ok":turn.complete,"fallback":turn.reason,"vi":turn.attack.vi if turn.attack else None,"t9":end9,"start10_A_B":start10,"end10_A_B":end10,"winner":r["vince"],"end_A_B":r["punti_fine"],"turns":r["turni"],"returns":1.0 if r["vince"]=="B" else 0.5 if r["vince"]=="DRAW" else 0.0}
def play(args):
    i,mode=args
    st=start_tree(mode,base+i)
    return [finish(st,k,i,mode) for k in ("valley","matteo","buff_sett")]
if __name__=="__main__":
    import multiprocessing as mp
    ap=argparse.ArgumentParser()
    ap.add_argument("kind",choices=["fisse","ignote"])
    ap.add_argument("n",type=int)
    ap.add_argument("--jobs",type=int,default=4)
    ap.add_argument("--start",type=int,default=0)
    a=ap.parse_args()
    tasks=[(i,a.kind) for i in range(a.start,a.start+a.n)]
    path=folder/f"{a.kind}_{a.start}_{a.n}.jsonl"
    # Store all paired results per seed together.
    with path.open("w") as f:
        if a.jobs==1: iterator=map(play,tasks)
        else:
            pool=ProcessPoolExecutor(max_workers=a.jobs,mp_context=mp.get_context("spawn"))
            iterator=pool.map(play,tasks)
        for k,rows in enumerate(iterator,1):
            f.write(json.dumps(rows,ensure_ascii=False)+"\n");f.flush()
            if k==1 or k%25==0: print(a.kind,k,flush=True)
        if a.jobs>1:pool.shutdown()

