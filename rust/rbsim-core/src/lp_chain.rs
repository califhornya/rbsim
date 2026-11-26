//! py: loop.py — the chain: putting items on it with declared choices (on a
//! copy of the game), priority (_run_chain, D62 kept as in the reference),
//! reaction steps, resolving.

use serde_json::{Map, Value};

use crate::agent::{AIdx, AKind, Action};
use crate::cards::truthy;
use crate::game::*;
use crate::lp_phases::py_str;
use crate::lp_triggers::Ctx;
use crate::model::*;
use crate::registry::Spec;
use crate::types::*;

impl Game {
    /// py: _put_on_chain(item)
    pub fn put_on_chain(&mut self, mut item: ChainItem) -> R<()> {
        if item.uid == 0 {
            item.uid = self.gs.chain_uid;
            self.gs.chain_uid += 1;
        }
        self.gs.chain.push(item);
        let idx = self.gs.chain.len() - 1;
        let declared = self.declare_choices(idx)?;
        self.gs.chain[idx].declared = declared.clone();
        if let Some(d) = declared {
            let mut units: Vec<UnitId> = Vec::new();
            for (_, (_k, _n, got)) in &d.items {
                let xs: Vec<Opt> = match got {
                    Chosen::One(o) => vec![o.clone()],
                    Chosen::Many(v) => v.clone(),
                };
                for x in xs {
                    let x = match x {
                        Opt::Tuple(v) if !v.is_empty() => v.last().unwrap().clone(),
                        o => o,
                    };
                    if let Opt::Unit(u) = x {
                        if !units.contains(&u) {
                            units.push(u);
                        }
                    }
                }
            }
            let (card, player) = (self.gs.chain[idx].card, self.gs.chain[idx].player);
            if !units.is_empty() {
                self.note_chosen(card, player, &units)?;
            }
            self.gs.chain[idx].choices_noted = true;
        }
        if self.gs.chain[idx].ability.is_none() {
            let c = self.gs.chain[idx].card;
            self.spell_finalized(c)?;
        }
        self.flush_triggers(false)
    }

    /// py: _spell_has_targets(card, side, lane)
    pub fn spell_has_targets(&mut self, card: CardId, side: Side, lane: usize) -> R<bool> {
        let specs = self.gs.spec(card).effects.clone();
        if self.gs.battlefields[lane].units_for(side).is_empty()
            && specs.iter().any(|es| es.params.get("battlefield").and_then(|v| v.as_str()) == Some("friendly_units"))
        {
            return Ok(false);
        }
        let text = self.gs.spec(card).raw.get("effect").map(py_str).unwrap_or_default().to_lowercase();
        if text.contains("up to") {
            return Ok(true);
        }
        let ctx = Ctx::new(card, side, lane);
        let (mut plain, mut conditional): (Vec<bool>, Vec<bool>) = (Vec::new(), Vec::new());
        for es in specs {
            if !(es.trigger == "on_play" || es.trigger == "on_cast") || es.optional {
                continue;
            }
            let mut params: Map<String, Value> = es.merged.clone();
            if params.get("target").and_then(|v| v.as_str()) == Some("it") {
                continue;
            }
            params.insert("effect".into(), Value::String(es.effect.clone()));
            if let Some(ok) = self.has_valid_target(&ctx, &params)? {
                if es.condition.as_ref().map_or(false, |c| truthy(Some(c))) {
                    conditional.push(ok);
                } else {
                    plain.push(ok);
                }
            }
        }
        if !plain.is_empty() {
            return Ok(plain.iter().all(|&b| b));
        }
        Ok(if conditional.is_empty() { true } else { conditional.iter().any(|&b| b) })
    }

    /// A copy of this game for a declaration (py: GameLoop(gs2) on a
    /// deepcopy of the state, agents replaced by _ModeAsker): the loop's own
    /// state is fresh (no _choices_noted, _replay, _in_many... of this
    /// loop); no chooser of its own yet.
    fn declaration_copy(&self) -> Game {
        let mut g2 = Game::new(self.gs.clone());
        g2.real = Some(self.real.unwrap_or(&self.gs as *const GameState));
        g2.copied_at = Some((self.gs.cards.len(), self.gs.units.len(), self.gs.dgear.len()));
        // _ModeAsker for the players whose agent has decide_mode; None for the others.
        for s in Side::BOTH {
            if let Some(a) = self.agents[s.idx()].clone() {
                if a.borrow().has("decide_mode") {
                    g2.agents[s.idx()] = Some(std::rc::Rc::new(std::cell::RefCell::new(ModeAsker { inner: a })));
                }
            }
        }
        g2
    }

    /// py: _declare_choices(item) — on the chain item at index `idx`.
    pub fn declare_choices(&mut self, idx: usize) -> R<Option<Declared>> {
        let item = self.gs.chain[idx].clone();
        if let Some(ab) = &item.ability {
            if ab.kind == "equip" {
                let mut d = Declared::default();
                d.items.push(((0, 0, 0), ("equip".into(), 1, Chosen::One(Opt::Unit(ab.target.unwrap())))));
                return Ok(Some(d));
            }
        }
        if self.dry_run || self.lookahead
            || (item.ability.is_none() && !self.gs.is_spell(item.card))
            || item.ability.as_ref().map_or(false, |a| a.kind == "reflexive")
        {
            return Ok(None);
        }
        let owed: Vec<UnitId> = self.gs.card(item.card).graceful_owed.clone().unwrap_or_default();
        if !owed.is_empty() {
            crate::not_ported!("_declare_choices", "Irelia Graceful owed choice");
        }
        let mut g2 = self.declaration_copy();
        g2.real_game = Some(self.real_game.unwrap_or(self as *mut Game));
        g2.dry_run = true;
        // The copy's chooser: only declared choices of this spell are the real
        // player's (through this loop's chooser), the rest are the baseline.
        let real = self.chooser.clone();
        g2.chooser = Some(std::rc::Rc::new(std::cell::RefCell::new(DeclChooser { real, real_loop: self as *mut Game })));
        g2.declaring = Some(Declaring { card: item.card, choices: Declared::default() });
        g2.task_depth = 1;
        let item2 = g2.gs.chain.pop().unwrap();
        g2.declare_board = Some(g2.presence_lists());
        let r: R<()> = if item2.ability.is_some() {
            g2.resolve_ability(item2)
        } else {
            g2.resolve_card_effects(item2.card, item2.bf_idx, item2.player)
        };
        if let Err(e) = r {
            if !e.swallowable() {
                return Err(e);
            }
        }
        let declared = g2.declaring.take().unwrap().choices;
        let mapped = self.map_back(&g2, declared);
        Ok(Some(mapped))
    }

    /// py: _mapped — a copy's objects are this game's (same ids); objects the
    /// copy created after it was made are foreign (they match nothing here).
    pub fn map_back(&self, _g2: &Game, d: Declared) -> Declared {
        let (nc, nu, ng) = (self.gs.cards.len(), self.gs.units.len(), self.gs.dgear.len());
        let nch = self.gs.chain_uid;
        let mb = |o: Opt| -> Opt { m(o, nc, nu, ng, nch) };
        fn m(o: Opt, nc: usize, nu: usize, ng: usize, nch: usize) -> Opt {
            match o {
                Opt::Chain(c) if c >= nch => Opt::Str(format!("$foreign-chain-{c}")),
                Opt::Unit(u) if u.i() >= nu => Opt::Str(format!("$foreign-unit-{}", u.0)),
                Opt::Card(c) if c.i() >= nc => Opt::Str(format!("$foreign-card-{}", c.0)),
                Opt::Gear(g) if g.i() >= ng => Opt::Str(format!("$foreign-gear-{}", g.0)),
                Opt::Tuple(v) => Opt::Tuple(v.into_iter().map(|x| m(x, nc, nu, ng, nch)).collect()),
                o => o,
            }
        }
        Declared {
            items: d
                .items
                .into_iter()
                .map(|(k, (kind, n, got))| {
                    let got = match got {
                        Chosen::One(o) => Chosen::One(mb(o)),
                        Chosen::Many(v) => Chosen::Many(v.into_iter().map(mb).collect()),
                    };
                    (k, (kind, n, got))
                })
                .collect(),
        }
    }

    /// py: _presence_lists
    pub fn presence_lists(&self) -> Vec<(PresenceKey, Vec<Obj>)> {
        let gs = &self.gs;
        let mut out: Vec<(PresenceKey, Vec<Obj>)> = vec![(PresenceKey::Chain, gs.chain.iter().map(|c| Obj::Chain(c.uid)).collect())];
        let mut units: Vec<UnitId> = Vec::new();
        for (j, bf) in gs.battlefields.iter().enumerate() {
            out.push((PresenceKey::Units(j, Side::A), bf.units[0].iter().map(|&u| Obj::Unit(u)).collect()));
            out.push((PresenceKey::Units(j, Side::B), bf.units[1].iter().map(|&u| Obj::Unit(u)).collect()));
            out.push((PresenceKey::Gear(j, Side::A), bf.gear[0].iter().map(|&g| Obj::Gear(g)).collect()));
            out.push((PresenceKey::Gear(j, Side::B), bf.gear[1].iter().map(|&g| Obj::Gear(g)).collect()));
            units.extend(bf.units[0].iter().copied());
            units.extend(bf.units[1].iter().copied());
        }
        for s in Side::BOTH {
            let p = gs.player(s);
            out.push((PresenceKey::Base(s), p.base_units.iter().map(|&u| Obj::Unit(u)).collect()));
            out.push((PresenceKey::BaseGear(s), p.base_gear.iter().map(|&c| Obj::Card(c)).collect()));
            units.extend(p.base_units.iter().copied());
        }
        for u in units {
            out.push((PresenceKey::Worn(u), gs.unit(u).gear.iter().map(|&c| Obj::Card(c)).collect()));
        }
        out
    }

    /// py: _board_changed
    pub fn board_changed(&self) -> bool {
        let mut now: Vec<Obj> = self.presence_lists().into_iter().flat_map(|(_, l)| l).collect();
        let mut then: Vec<Obj> = self.declare_board.as_ref().unwrap().iter().flat_map(|(_, l)| l.iter().copied()).collect();
        now.sort_by_key(obj_key);
        now.dedup();
        then.sort_by_key(obj_key);
        then.dedup();
        now != then
    }

    /// py: _choices_on_board_as_played(context, es, run, i)
    pub fn choices_on_board_as_played(&mut self, ctx: &Ctx, es: &Spec, run: i64, i: i64) -> R<Option<Declared>> {
        let Some(d) = &self.declaring else { return Ok(None) };
        if self.declare_board.is_none() || ctx.card != d.card || !self.board_changed() {
            return Ok(None);
        }
        let mut g3 = self.clone();
        g3.loop_id = new_loop_id();
        let ghosts = g3.restore_declared_board()?;
        g3.ghost_ids = Some(ghosts);
        g3.declaring = Some(Declaring { card: ctx.card, choices: Declared::default() });
        g3.replay = None;
        g3.slot = Some([run, i, 0]);
        let mut ctx3 = ctx.clone();
        match g3.run_effect(&es.effect, &mut ctx3, &es.merged) {
            Ok(()) => {}
            Err(e) if e.swallowable() => {}
            Err(e) => return Err(e),
        }
        let d = g3.declaring.take().unwrap().choices;
        Ok(Some(self.map_back(&g3, d)))
    }

    /// py: _restore_declared_board — what left the board since the spell was
    /// played goes back (last), what came goes; returns what went back.
    pub fn restore_declared_board(&mut self) -> R<Vec<Obj>> {
        let now: Vec<Obj> = self.presence_lists().into_iter().flat_map(|(_, l)| l).collect();
        let board = self.declare_board.clone().unwrap();
        let then: Vec<Obj> = board.iter().flat_map(|(_, l)| l.iter().copied()).collect();
        let mut back_in: Vec<Obj> = Vec::new();
        for (key, before) in &board {
            for &x in before {
                if !now.contains(&x) {
                    let present = self.presence_list_get(key).map_or(true, |l| l.contains(&x));
                    if self.presence_list_get(key).is_none() {
                        continue;
                    }
                    if !present {
                        self.presence_list_push(key, x)?;
                        back_in.push(x);
                    }
                }
            }
        }
        let keys: Vec<PresenceKey> = self.presence_lists().into_iter().map(|(k, _)| k).collect();
        for k in keys {
            let l = self.presence_list_get(&k).unwrap();
            let kept: Vec<Obj> = l.into_iter().filter(|x| then.contains(x)).collect();
            self.presence_list_set(&k, kept)?;
        }
        Ok(back_in)
    }

    fn presence_list_get(&self, key: &PresenceKey) -> Option<Vec<Obj>> {
        let gs = &self.gs;
        Some(match key {
            PresenceKey::Chain => gs.chain.iter().map(|c| Obj::Chain(c.uid)).collect(),
            PresenceKey::Worn(u) => gs.unit(*u).gear.iter().map(|&c| Obj::Card(c)).collect(),
            PresenceKey::Base(s) => gs.player(*s).base_units.iter().map(|&u| Obj::Unit(u)).collect(),
            PresenceKey::BaseGear(s) => gs.player(*s).base_gear.iter().map(|&c| Obj::Card(c)).collect(),
            PresenceKey::Units(j, s) => gs.battlefields.get(*j)?.units_for(*s).iter().map(|&u| Obj::Unit(u)).collect(),
            PresenceKey::Gear(j, s) => gs.battlefields.get(*j)?.gear[s.idx()].iter().map(|&g| Obj::Gear(g)).collect(),
        })
    }

    fn presence_list_push(&mut self, key: &PresenceKey, x: Obj) -> R<()> {
        match (key, x) {
            (PresenceKey::Worn(u), Obj::Card(c)) => self.gs.unit_mut(*u).gear.push(c),
            (PresenceKey::Base(s), Obj::Unit(u)) => self.gs.player_mut(*s).base_units.push(u),
            (PresenceKey::BaseGear(s), Obj::Card(c)) => self.gs.player_mut(*s).base_gear.push(c),
            (PresenceKey::Units(j, s), Obj::Unit(u)) => self.gs.battlefields[*j].units_for_mut(*s).push(u),
            (PresenceKey::Gear(j, s), Obj::Gear(g)) => self.gs.battlefields[*j].gear[s.idx()].push(g),
            _ => crate::not_ported!("_restore_declared_board", "a chain item back on the chain"),
        }
        Ok(())
    }

    fn presence_list_set(&mut self, key: &PresenceKey, v: Vec<Obj>) -> R<()> {
        let cards = |v: &[Obj]| v.iter().filter_map(|o| if let Obj::Card(c) = o { Some(*c) } else { None }).collect::<Vec<_>>();
        let units = |v: &[Obj]| v.iter().filter_map(|o| if let Obj::Unit(u) = o { Some(*u) } else { None }).collect::<Vec<_>>();
        match key {
            PresenceKey::Chain => {
                if v.len() != self.gs.chain.len() {
                    crate::not_ported!("_restore_declared_board", "a chain item that came since");
                }
            }
            PresenceKey::Worn(u) => self.gs.unit_mut(*u).gear = cards(&v),
            PresenceKey::Base(s) => self.gs.player_mut(*s).base_units = units(&v),
            PresenceKey::BaseGear(s) => self.gs.player_mut(*s).base_gear = cards(&v),
            PresenceKey::Units(j, s) => *self.gs.battlefields[*j].units_for_mut(*s) = units(&v),
            PresenceKey::Gear(j, s) => {
                self.gs.battlefields[*j].gear[s.idx()] = v.iter().filter_map(|o| if let Obj::Gear(g) = o { Some(*g) } else { None }).collect()
            }
        }
        Ok(())
    }

    /// py: _run_chain(caster)
    pub fn run_chain(&mut self, caster: Side) -> R<()> {
        self.run_chain_from(caster, 0)
    }

    /// The chain's priority loop from a given point: `active` is asked next, `passes` passes in a
    /// row so far (run_chain starts it at (caster, 0)). Each time an agent is asked, (side,
    /// passes) is recorded in `win_chain`, for a search started from inside the window.
    pub fn run_chain_from(&mut self, active: Side, passes: i32) -> R<()> {
        let mut active = active;
        let mut passes = passes;
        let mut rounds = 0;
        while passes < 2 && !self.gs.chain.is_empty() && rounds < PRIORITY_ROUNDS_CAP && !self.all_pass
            && self.gs.winner.is_none()
        {
            rounds += 1;
            let Some(agent) = self.agent(active).filter(|a| a.borrow().has("decide_reaction")) else {
                passes += 1;
                active = active.other();
                continue;
            };
            self.win_chain = Some((active, passes));
            let action = agent.borrow_mut().decide_reaction(self, active)?;
            (active, passes) = self.chain_apply(active, passes, &action)?;
        }
        self.resolve_chain()
    }

    /// What the chain loop does with the action `active` chose, with `passes` in a row so far:
    /// the new (active, passes) the loop goes on with.
    pub fn chain_apply(&mut self, active: Side, passes: i32, action: &Action) -> R<(Side, i32)> {
        if let Some(j) = self.journal.as_mut() {
            j.push(JEntry::Decision(active, "reaction".into(), action.clone()));
        }
        let depth = self.gs.chain.len();
        let mut step = if action.kind == AKind::Pass { "pass" } else { self.reaction_step(active, action)? };
        self.flush_triggers(false)?;
        if step != "pass" && self.gs.chain.len() > depth {
            step = "acted";
        }
        if step == "kept" {
            return Ok((active, passes)); // D62 (reference behaviour): the pass streak is not reset
        }
        if step == "acted" {
            let active = self.gs.chain.last().map_or(active, |top| top.player);
            Ok((active, 0))
        } else {
            Ok((active.other(), passes + 1))
        }
    }

    /// py: _reaction_step(player, side, action) -> "acted" | "kept" | "noop"
    pub fn reaction_step(&mut self, side: Side, action: &Action) -> R<&'static str> {
        let hand_len = self.gs.player(side).hand.len() as i64;
        let idx = action.idx_int();
        match action.kind {
            AKind::Spell => {
                if let Some(i) = idx.filter(|&i| 0 <= i && i < hand_len) {
                    let card = self.gs.player(side).hand[i as usize];
                    if self.gs.is_spell(card) && self.has_reaction(card, side) {
                        let lane = match action.lane {
                            Some(l) if 0 <= l && (l as usize) < self.gs.battlefields.len() => l as usize,
                            _ => 0,
                        };
                        let (e, p) = self.effective_cost(card, side, Some(lane as i64))?;
                        if self.spell_has_targets(card, side, lane)? && self.pay_card(side, card, e, p, Some(lane as i64))? {
                            self.gs.player_mut(side).hand.remove(i as usize);
                            self.spell_played(card, side, "hand")?;
                            self.put_on_chain(ChainItem { uid: 0, player: side, card, bf_idx: lane, declared: None, choices_noted: false, owner: None, ability: None })?;
                            return Ok("acted");
                        }
                    }
                }
            }
            AKind::Gear => {
                if let Some(i) = idx.filter(|&i| 0 <= i && i < hand_len) {
                    let card = self.gs.player(side).hand[i as usize];
                    if self.gs.is_gear_card(card) && self.play_timing(card, side) == Some("reaction") {
                        let before = self.gs.player(side).hand.len();
                        let a = Action::new(AKind::Gear, AIdx::Int(i), Some(action.lane.unwrap_or(0)), None, String::new());
                        let a = Action { len4: true, ..a };
                        self.apply_action(side, &a, 0)?;
                        if self.gs.player(side).hand.len() < before {
                            return Ok("acted");
                        }
                    }
                }
            }
            AKind::Champion => {
                if self.deploy_ambush_champion(side, action.lane.unwrap_or(0).max(0) as usize)? {
                    return Ok("acted");
                }
            }
            AKind::Unit if action.len4 => {
                if self.play_ambush_unit(side, idx.unwrap_or(-1), action.dst.unwrap_or(-1))? {
                    return Ok("acted");
                }
            }
            AKind::HiddenPlay => {
                let slot = idx.unwrap_or(0);
                if self.play_from_hidden(side, action.lane.unwrap_or(0) as usize, slot as usize)? {
                    return Ok("acted");
                }
            }
            AKind::Ability => {
                let depth = self.gs.chain.len();
                if self.use_ability_now(side, &action.index, action.lane)? {
                    return Ok(if self.gs.chain.len() == depth { "kept" } else { "acted" });
                }
            }
            _ => {}
        }
        Ok("noop")
    }

    /// py: _resolve_chain
    pub fn resolve_chain(&mut self) -> R<()> {
        let Some(item) = self.gs.chain.pop() else { return Ok(()) };
        if self.gs.chain.is_empty() {
            self.gs.chain_gone.clear();
        } else {
            self.gs.chain_gone.push(item.clone());
        }
        self.task_depth += 1;
        let r = self.resolve_item(item);
        self.task_depth -= 1;
        r?;
        self.flush_triggers(false)?;
        if let Some(top) = self.gs.chain.last() {
            let p = top.player;
            self.run_chain(p)?;
        } else if !self.dry_run {
            self.cleanup_hidden_cards()?;
        }
        Ok(())
    }

    /// py: _resolve_chain_passing
    pub fn resolve_chain_passing(&mut self) -> R<()> {
        let outer = self.all_pass;
        self.all_pass = true;
        let mut r = Ok(());
        while !self.gs.chain.is_empty() {
            r = self.resolve_chain();
            if r.is_err() {
                break;
            }
        }
        self.all_pass = outer;
        r
    }

    /// py: _resolve_item(item)
    pub fn resolve_item(&mut self, item: ChainItem) -> R<()> {
        let (actor, bf, card) = (item.player, item.bf_idx, item.card);
        let outer = self.replay.take();
        let outer_noted = self.choices_noted;
        let outer_item = self.resolving_item;
        self.resolving_item = Some(card);
        self.replay = match &item.declared {
            Some(d) if !d.items.is_empty() => Some(Declaring { card, choices: d.clone() }),
            _ => None,
        };
        self.choices_noted = item.choices_noted;
        let is_ability = item.ability.is_some();
        let owner = item.owner;
        let r = if is_ability { self.resolve_ability(item) } else { self.resolve_card_effects(card, bf, actor) };
        self.replay = outer;
        self.choices_noted = outer_noted;
        self.resolving_item = outer_item;
        r?;
        if is_ability {
            return Ok(());
        }
        self.spells_cast += 1;
        if self.gs.is_spell(card) && !self.gs.chain.iter().any(|it| it.card == card) {
            self.spell_to_trash(owner.unwrap_or(actor), card)?;
        }
        Ok(())
    }
}

fn obj_key(o: &Obj) -> (u8, u32) {
    match o {
        Obj::Unit(u) => (0, u.0),
        Obj::Card(c) => (1, c.0),
        Obj::Gear(g) => (2, g.0),
        Obj::Chain(i) => (3, *i as u32),
    }
}

/// py: _ModeAsker — a player's agent on a declaration's copy: only decide_mode.
pub struct ModeAsker {
    pub inner: std::rc::Rc<std::cell::RefCell<dyn crate::agent::Agent>>,
}

impl crate::agent::Agent for ModeAsker {
    fn decide_action(&mut self, _: &mut Game, _: Side, _: i64) -> R<Action> {
        Err(EngineError::Py("AttributeError: decide_action".into()))
    }
    fn decide_reaction(&mut self, _: &mut Game, _: Side) -> R<Action> {
        Err(EngineError::Py("AttributeError: decide_reaction".into()))
    }
    fn decide_showdown_action(&mut self, _: &mut Game, _: Side, _: usize) -> R<Action> {
        Err(EngineError::Py("AttributeError: decide_showdown_action".into()))
    }
    fn decide_mulligan(&mut self, _: &mut Game, _: Side) -> R<Vec<i64>> {
        Err(EngineError::Py("AttributeError: decide_mulligan".into()))
    }
    fn decide_optional(&mut self, _: &mut Game, _: Side, _: CardId, _: &str) -> R<bool> {
        Err(EngineError::Py("AttributeError: decide_optional".into()))
    }
    fn decide_mode(&mut self, g: &mut Game, side: Side, card: CardId, n: i64) -> R<Option<i64>> {
        self.inner.borrow_mut().decide_mode(g, side, card, n)
    }
    fn decide_predict_recycle(&mut self, _: &mut Game, _: Side, _: CardId) -> R<bool> {
        Err(EngineError::Py("AttributeError: decide_predict_recycle".into()))
    }
    fn has(&self, method: &str) -> bool {
        method == "decide_mode"
    }
}

/// The chooser of a declaration's copy (py: the closure in _declare_choices).
pub struct DeclChooser {
    pub real: Option<std::rc::Rc<std::cell::RefCell<dyn crate::agent::Chooser>>>,
    pub real_loop: *mut Game,
}

impl crate::agent::Chooser for DeclChooser {
    fn choose(&mut self, g: &mut Game, kind: &str, side: Side, options: &[Opt], default: usize, source: Option<CardId>)
              -> R<Option<usize>> {
        let spell = g.declaring.as_ref().map(|d| d.card);
        if source.is_none() || source != spell || !is_declared_kind(kind) || g.slot.is_none() {
            return Ok(None);
        }
        let Some(real) = self.real.clone() else { return Ok(None) };
        // py: self._consult(_loop, ...): the real chooser, asked with the copy,
        // the answer journaled on the real loop.
        let i = real.borrow_mut().choose(g, kind, side, options, default, source)?;
        // SAFETY: the real loop is the frame running this declaration; only its
        // journal is touched, which the copy does not alias.
        let rl = unsafe { &mut *self.real_loop };
        if let Some(j) = rl.journal.as_mut() {
            j.push(JEntry::Choice(side, kind.to_string(), options.len(), i.unwrap_or(default)));
        }
        Ok(i)
    }
}
