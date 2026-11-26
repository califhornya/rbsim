"""Linee di Matteo e variante con Armory su Sett, per il confronto guidato."""
import json
from riftbound.rs import decisione_esp as E, decisione_rs as D

def pick(labels, query, default=None):
    return next((i for i, s in enumerate(labels) if query.casefold() in s.casefold()), default)

class Plan:

    def __init__(self, arm, timing, rescue, early_target):
        self.arm = arm
        self.timing = timing
        self.rescue = rescue
        self.early_target = early_target
        self.stage = 0
        self.closed = False
        self.gear = False
        self.vi = False
        self.pf = None
        self.reply = False
        self.stun = None
        self.log = []
        self.saves = []
        self.menus = []
        self.lastpoints = []

    def ask(self, data):
        e = json.loads(data)
        k = e['k']
        if k == 'decision':
            m = e['menu']
            point = e['point']
            default = pick(m, 'Pass', 0)

            def play(q):
                i = pick(m, q)
                if i is not None:
                    self.log.append([point, m[i]])
                return i
            if point == 'turn_action':
                if not self.gear:
                    i = play('Play gear Pillaged Armory @BF0')
                    if i is None:
                        raise ValueError(('armory', m))
                    self.gear = True
                    return i
                if self.stage == 0:
                    i = play('Move Kinkou Initiate base→BF0')
                    if i is None:
                        raise ValueError(('kinkou', m))
                    self.stage = 1
                    self.closed = False
                    return i
                if not self.closed:
                    self.closed = True
                    return default
                if self.stage == 1:
                    i = play('Move Sett Kingpin base→BF0')
                    if i is None:
                        self.menus.append(m)
                        return default
                    self.stage = 2
                    self.closed = False
                    return i
                self.menus.append(m)
                for s in m:
                    if ('→BF1' in s or 'to BF1' in s) and (s.startswith('Move ') or s.startswith('Play ')):
                        return play(s)
                return default
            if self.stage == 2 and (not self.vi) and self.closed:
                i = play('AMBUSH Vi Peacekeeper @BF0')
                if i is not None:
                    self.vi = True
                    return i
            if self.stage == 1 and self.pf is None and (point == 'showdown_action') and (pick(m, 'Showdown Punch First @BF0') is not None):
                early = self.timing == 'early' or (self.timing == 'reported' and self.reply)
                if self.timing == 'if_needed':
                    p = D.riassunto(e['state_raw'], 'B')['campi'][0]
                    me = dict(p['campione']['unita'])
                    op = dict(p['avversario']['unita'])
                    early = 'Kinkou Initiate' in me and 'Vex Apathetic' in op and (op['Vex Apathetic'] > me['Kinkou Initiate'])
                if early:
                    self.pf = 'Kinkou'
                    return play('Showdown Punch First @BF0')
            if self.stage == 2 and self.pf is None and self.vi and (point == 'showdown_action') and (pick(m, 'Showdown Punch First @BF0') is not None):
                self.pf = 'Sett'
                return play('Showdown Punch First @BF0')
            return default
        if k == 'choice':
            kind = e['kind']
            labels = E.etichette_scelta(e)
            idx = e['default']
            if kind == 'target:buff_unit':
                idx = pick(labels, self.arm, idx)
            elif kind == 'target:stun_unit':
                idx = pick(labels, "K'Sante", idx)
                self.stun = labels[idx]
            elif kind == 'target:grant_temporary_might':
                idx = pick(labels, self.pf or 'Sett', idx)
            elif kind == 'combat_damage_order':
                ranking = ['Vex Apathetic', self.early_target, 'Reckless', 'Momentary', "K'Sante", 'Pyke'] if self.stage == 1 else ['Vex Apathetic', 'Momentary', 'Reckless', "K'Sante", 'Pyke']
                idx = pick(labels, 'Vex Apathetic', idx) if self.stage == 1 and self.timing == 'reported' else next((pick(labels, s) for s in ranking if pick(labels, s) is not None), idx)
            elif kind == 'optional:sett_save':
                use = self.stage == 2 or self.rescue
                idx = pick(labels, 'sì' if use else ': no', idx)
                self.saves.append([self.stage, labels[idx]])
            self.log.append([kind, labels[idx]])
            return idx
        if k == 'decide_optional':
            return True
        if k == 'decide_mode':
            return None
        if k == 'decide_mulligan':
            return []
        if k == 'decide_predict_recycle':
            return False
        raise ValueError(k)
