//! py: loop.py — card effects resolving, triggered abilities (pending,
//! finalized, resolving), their costs, unit-wide triggers, "when you
//! choose me".

use serde_json::{Map, Value};

use crate::cards::truthy;
use crate::game::*;
use crate::lp_phases::bf_extra;
use crate::model::*;
use crate::not_ported;
use crate::registry::Spec;
use crate::types::*;

/// py: EffectContext (loop, card, actor, opponent, battlefield, extra).
#[derive(Clone, Debug)]
pub struct Ctx {
    pub card: CardId,
    pub actor: Side,
    pub opponent: Side,
    pub bf: usize,
    pub extra: Extra,
}

impl Ctx {
    pub fn new(card: CardId, actor: Side, bf: usize) -> Ctx {
        Ctx { card, actor, opponent: actor.other(), bf, extra: Extra::default() }
    }
}

pub const ADD_VERBS: [&str; 6] =
    ["gain_energy", "add_power", "gain_power_any_domain", "add_earmarked_energy", "add_earmarked_power", "convert_x"];

pub fn is_add_verb(v: &str) -> bool {
    ADD_VERBS.contains(&v)
}

/// The index of an instruction made in play (py: None in (index, EffectSpec)).
pub const NO_IDX: usize = usize::MAX;

/// py: the instruction index, None for one made in play.
pub fn ix(i: usize) -> Option<usize> {
    if i == NO_IDX { None } else { Some(i) }
}

impl Game {
    // ------------------------------------------------------- card flags ---

    pub fn card_flag_get(&self, c: CardId, k: &str) -> XVal {
        let card = self.gs.card(c);
        match k {
            "_kicker_paid" => card.kicker_paid.map(XVal::Bool).unwrap_or(XVal::None),
            "_showed_off" => card.showed_off.map(XVal::Bool).unwrap_or(XVal::None),
            "_shown" => card.shown.clone().map(XVal::Json).unwrap_or(XVal::None),
            "_hidden_bf" => card.hidden_bf.map(|b| XVal::Int(b as i64)).unwrap_or(XVal::None),
            _ => XVal::None,
        }
    }

    pub fn card_flag_set(&mut self, c: CardId, k: &str, v: &XVal) {
        let card = self.gs.card_mut(c);
        match k {
            "_kicker_paid" => card.set_kicker(match v {
                XVal::Bool(b) => Some(*b),
                _ => None,
            }),
            "_showed_off" => card.set_showed(match v {
                XVal::Bool(b) => Some(*b),
                _ => None,
            }),
            "_shown" => {
                card.shown = match v {
                    XVal::Json(j) => Some(j.clone()),
                    _ => None,
                }
            }
            "_hidden_bf" => {
                card.hidden_bf = match v {
                    XVal::Int(i) => Some(*i as usize),
                    XVal::Bf(b) => Some(*b),
                    _ => None,
                }
            }
            _ => {}
        }
    }

    /// py: _card_flags(card, flags) as a context manager around `f`.
    pub fn with_card_flags<T>(&mut self, c: CardId, flags: &mut Option<Flags>, f: impl FnOnce(&mut Game) -> R<T>)
                              -> R<T> {
        let Some(fl) = flags.as_mut().filter(|f| !f.is_empty()) else { return f(self) };
        let keys: Vec<String> = fl.keys().cloned().collect();
        let saved: Vec<XVal> = keys.iter().map(|k| self.card_flag_get(c, k)).collect();
        for (k, v) in fl.iter() {
            let (k, v) = (k.clone(), v.clone());
            self.card_flag_set(c, &k, &v);
        }
        let out = f(self);
        for k in &keys {
            let v = self.card_flag_get(c, k);
            fl.set(k.clone(), v);
        }
        for (k, v) in keys.iter().zip(saved.iter()) {
            self.card_flag_set(c, k, v);
        }
        out
    }

    // -------------------------------------------------- card effects ---

    /// py: _card_effects(card, worn=None)
    pub fn card_effects(&self, card: CardId, worn: &[CardId]) -> Vec<Spec> {
        let effects: Vec<Spec> = self.gs.spec(card).effects.clone();
        if effects.is_empty() {
            return effects;
        }
        let copies = worn.iter().filter(|&&g| self.has_effect(g, "copy_unit_text")).count();
        let mut out = Vec::with_capacity(effects.len() * (1 + copies));
        for _ in 0..(1 + copies) {
            out.extend(effects.iter().cloned());
        }
        out
    }

    /// py: _card_effects(card) with worn = the gear of the unit that is this card.
    pub fn card_effects_auto(&self, card: CardId) -> Vec<Spec> {
        let worn = match self.find_unit_by_card(card) {
            Some(u) => self.gs.unit(u).gear.clone(),
            None => Vec::new(),
        };
        self.card_effects(card, &worn)
    }

    /// py: _has_effect
    pub fn has_effect(&self, card: CardId, verb: &str) -> bool {
        self.gs.spec(card).effects.iter().any(|es| es.effect == verb)
    }

    /// py: _has_trigger
    pub fn has_trigger(&self, card: CardId, trigger: &str) -> bool {
        self.gs.spec(card).effects.iter().any(|es| es.trigger == trigger)
    }

    /// py: _units_at_battlefields_with
    pub fn units_at_battlefields_with(&self, side: Side, verb: &str) -> Vec<UnitId> {
        let mut out = Vec::new();
        for bf in &self.gs.battlefields {
            for &u in bf.units_for(side) {
                if self.has_effect(self.gs.ucard(u), verb) {
                    out.push(u);
                }
            }
        }
        out
    }

    /// py: _locate_unit -> (side, battlefield or None for base)
    pub fn locate_unit(&self, unit: UnitId) -> Option<(Side, Option<usize>)> {
        for side in Side::BOTH {
            for (i, bf) in self.gs.battlefields.iter().enumerate() {
                if bf.units_for(side).contains(&unit) {
                    return Some((side, Some(i)));
                }
            }
            if self.gs.player(side).base_units.contains(&unit) {
                return Some((side, None));
            }
        }
        None
    }

    // ---------------------------------------------- resolve card effects ---

    /// Run a handler; py's try/except around it. Returns Ok(()) also when
    /// the handler raised (skipped) or was ignored (ctx.extra["it"] = []).
    pub fn call_handler(&mut self, ctx: &mut Ctx, verb: &str, params: &Map<String, Value>) -> R<()> {
        match self.run_effect(verb, ctx, params) {
            Ok(()) => Ok(()),
            Err(EngineError::Ignored(_)) => {
                ctx.extra.set("it", XVal::List(Vec::new()));
                Ok(())
            }
            Err(e) if e.swallowable() => Ok(()),
            Err(e) => Err(e),
        }
    }

    /// py: _resolve_card_effects(card, battlefield, actor, opponent)
    pub fn resolve_card_effects(&mut self, card: CardId, bf: usize, actor: Side) -> R<()> {
        let effect_specs: Vec<Spec> = self.gs.spec(card).effects.clone();
        if effect_specs.is_empty() && !self.gs.effects(card).is_empty() {
            not_ported!("_resolve_card_effects", "card effects without a registry spec");
        }
        let mut ctx = Ctx::new(card, actor, bf);
        let play_specs: Vec<Spec> =
            effect_specs.iter().filter(|es| es.trigger == "on_play" || es.trigger == "on_cast").cloned().collect();
        if !self.gs.is_spell(card) {
            if !play_specs.is_empty() {
                let mut flags: Flags = Flags::new();
                // getattr(card, k, False): None once set to None (a _card_flags restore).
                let xb = |v: Option<bool>| v.map(XVal::Bool).unwrap_or(XVal::None);
                flags.set("_kicker_paid".into(), xb(self.gs.card(card).kicker_or_false()));
                flags.set("_showed_off".into(), xb(self.gs.card(card).showed_or_false()));
                flags.set("_shown".into(), self.card_flag_get(card, "_shown"));
                if let Some(h) = self.gs.card(card).hidden_bf {
                    flags.set("_hidden_bf".into(), XVal::Int(h as i64));
                }
                let specs: Vec<(usize, Spec)> = effect_specs
                    .iter()
                    .enumerate()
                    .filter(|(_, es)| es.trigger == "on_play" || es.trigger == "on_cast")
                    .map(|(i, es)| (i, es.clone()))
                    .collect();
                self.trigger(card, "on_play", specs, bf, actor, None, false, false, Some(flags))?;
                let c = self.gs.card_mut(card);
                c.set_kicker(Some(false));
                c.set_showed(Some(false));
                c.shown = None;
            }
            return Ok(());
        }
        if play_specs.is_empty() {
            if effect_specs.is_empty() {
                not_ported!("_resolve_card_effects", "effect-less spell (printed damage)");
            }
            return Ok(());
        }
        let mut runs = 1;
        let c = self.gs.card(card);
        if (self.gs.has_keyword(card, "REPEAT") || truthy(c.granted_repeat.as_ref())) && truthy(c.repeat_paid.as_ref()) {
            let extra = c.repeat_extra.as_ref().map(crate::cards::py_int).unwrap_or(1);
            runs = 1 + extra;
        }
        let outer_slot = self.slot;
        let res: R<()> = (|| {
            for run in 0..runs {
                for (i, es) in play_specs.iter().enumerate() {
                    if truthy(es.params.get("reflexive")) {
                        not_ported!("_resolve_card_effects", "reflexive (then do this)");
                    }
                    if !self.check_condition(es.condition.as_ref(), card, actor, None)? {
                        continue;
                    }
                    if es.cost.is_some() && !self.triggered_cost_affordable(card, actor, es)? {
                        continue;
                    }
                    if !self.wants_optional(actor, card, es)? {
                        continue;
                    }
                    if es.cost.is_some() && !self.pay_triggered_cost(card, actor, es, false)? {
                        continue;
                    }
                    if !crate::effects::exists(&es.effect) {
                        continue;
                    }
                    self.slot = Some([run, i as i64, 0]);
                    let early = self.choices_on_board_as_played(&ctx, es, run, i as i64)?;
                    let has_early = early.as_ref().map_or(false, |e| !e.items.is_empty());
                    if has_early {
                        self.replay = Some(Declaring { card, choices: early.clone().unwrap() });
                    }
                    let params = self.params_now(es, card, actor, None)?;
                    let r = self.call_handler(&mut ctx, &es.effect, &params);
                    if has_early {
                        self.replay = None;
                        if let Some(d) = self.declaring.as_mut() {
                            for (k, v) in early.unwrap().items {
                                if let Some(e) = d.choices.items.iter_mut().find(|(kk, _)| *kk == k) {
                                    e.1 = v;
                                } else {
                                    d.choices.items.push((k, v));
                                }
                            }
                        }
                    }
                    r?;
                }
            }
            Ok(())
        })();
        self.slot = outer_slot;
        let c = self.gs.card_mut(card);
        if c.kicker_paid.unwrap_or(false) {
            c.set_kicker(Some(false));
        }
        c.set_showed(Some(false));
        c.shown = None;
        res
    }

    /// py: _wants_optional
    pub fn wants_optional(&mut self, actor: Side, card: CardId, es: &Spec) -> R<bool> {
        if !es.optional {
            return Ok(true);
        }
        let mut yes = true;
        if let Some(a) = self.agent(actor).filter(|a| a.borrow().has("decide_optional")) {
            yes = a.borrow_mut().decide_optional(self, actor, card, &es.effect)?;
        }
        let kind = format!("optional:{}", es.effect);
        let got = self.choose(&kind, actor, &[Opt::Bool(true), Opt::Bool(false)], Opt::Bool(yes), Some(card))?;
        Ok(got == Opt::Bool(true))
    }

    /// py: _wants_optional_keyword
    pub fn wants_optional_keyword(&mut self, actor: Side, card: CardId, name: &str) -> R<bool> {
        let mut yes = true;
        if let Some(a) = self.agent(actor).filter(|a| a.borrow().has("decide_optional")) {
            yes = a.borrow_mut().decide_optional(self, actor, card, name)?;
        }
        let kind = format!("optional:{name}");
        let got = self.choose(&kind, actor, &[Opt::Bool(true), Opt::Bool(false)], Opt::Bool(yes), Some(card))?;
        Ok(got == Opt::Bool(true))
    }

    /// py: _resolve_triggered_effects(card, trigger, battlefield, actor, opponent, context_extra)
    pub fn resolve_triggered_effects(&mut self, card: CardId, trigger: &str, bf: usize, actor: Side,
                                     extra: Option<Extra>) -> R<()> {
        let dead = extra.as_ref().and_then(|e| e.card("died_card")) == Some(card);
        let specs_all = if dead {
            let worn: Vec<CardId> = match extra.as_ref().and_then(|e| e.get("died_gear")) {
                Some(XVal::List(v)) => v.iter().filter_map(|x| if let XVal::Card(c) = x { Some(*c) } else { None }).collect(),
                _ => Vec::new(),
            };
            self.card_effects(card, &worn)
        } else {
            self.card_effects_auto(card)
        };
        let specs: Vec<(usize, Spec)> =
            specs_all.into_iter().enumerate().filter(|(_, es)| es.trigger == trigger).collect();
        if !specs.is_empty() {
            self.trigger(card, trigger, specs, bf, actor, extra, true, true, None)?;
        }
        Ok(())
    }

    /// py: _kicker_gate
    pub fn kicker_gate(es: &Spec, additional: bool) -> bool {
        additional
            && es.condition.as_ref().and_then(|c| c.get("type")).and_then(|t| t.as_str()) == Some("kicker_paid")
    }

    /// py: _trigger
    pub fn trigger(&mut self, card: CardId, trigger: &str, specs: Vec<(usize, Spec)>, bf: usize, side: Side,
                   extra: Option<Extra>, additional: bool, once: bool, flags: Option<Flags>) -> R<()> {
        let mut flags: Option<Flags> = Some(match flags {
            Some(f) => f,
            None => {
                let mut f = Flags::new();
                f.set("_kicker_paid".into(), XVal::Bool(false));
                f
            }
        });
        if once
            && specs.iter().all(|(_, es)| truthy(es.params.get("once_per_turn")))
            && specs.iter().any(|(i, es)| self.once_used(card, *i, es))
        {
            return Ok(());
        }
        let ex2 = extra.clone();
        let lead = self.with_card_flags(card, &mut flags, |g| {
            for (n, (i, es)) in specs.iter().enumerate() {
                if once && g.once_used(card, *i, es) {
                    continue;
                }
                if truthy(es.params.get("effect_condition"))
                    || Game::kicker_gate(es, additional)
                    || g.check_condition(es.condition.as_ref(), card, side, ex2.as_ref())?
                {
                    return Ok(Some(n));
                }
            }
            Ok(None)
        })?;
        let Some(lead) = lead else { return Ok(()) };
        self.pending_triggers.push(PendingTrigger {
            card,
            trigger: trigger.to_string(),
            side,
            bf,
            specs: specs[lead..].to_vec(),
            extra,
            additional,
            flags,
            once,
            replay: None,
        });
        if self.task_depth == 0 {
            self.flush_triggers(true)?;
        }
        Ok(())
    }

    /// py: _once_used (an instruction made in play, index None: key (card, None))
    pub fn once_used(&self, card: CardId, i: usize, es: &Spec) -> bool {
        let key = match ix(i) {
            Some(i) => OnceKey::Idx(i as i64),
            None => OnceKey::Str("None".into()),
        };
        truthy(es.params.get("once_per_turn")) && self.gs.once_per_turn_used.get(&OnceK::Card(card, key)) == Some(&self.gs.turn)
    }

    /// py: _reflexive(ctx, then, extra=None) — a reflexive trigger of the
    /// resolving spell or ability ("do this:", §388): `then` (an effect dict or
    /// a list of them) goes on the chain once that is done (§389), sharing the
    /// resolving one's information ("it", `extra`).
    pub fn reflexive(&mut self, ctx: &Ctx, then: &Value, extra: Option<&Extra>) -> R<()> {
        let list: Vec<Value> = match then {
            Value::Array(a) => a.clone(),
            v => vec![v.clone()],
        };
        let mut specs: Vec<(usize, Spec)> = Vec::new();
        for es in list {
            let Value::Object(mut m) = es else { not_ported!("_reflexive", "an EffectSpec instance") };
            m.insert("trigger".into(), Value::String("reflexive".into()));
            match crate::registry::EffectSpec::from_dict(&m) {
                Ok(spec) => specs.push((NO_IDX, std::rc::Rc::new(spec))),
                Err(e) => not_ported!("_reflexive", "{e}"),
            }
        }
        let mut ex = ctx.extra.clone();
        if let Some(e) = extra {
            for (k, v) in e.items.iter() {
                ex.set(k, v.clone());
            }
        }
        let mut flags = Flags::new();
        let kp = self.gs.card(ctx.card).kicker_paid;
        flags.set("_kicker_paid".into(), XVal::Bool(kp.unwrap_or(false)));
        self.trigger(ctx.card, "reflexive", specs, ctx.bf, ctx.actor, Some(ex), true, false, Some(flags))
    }

    /// py: _params_now
    pub fn params_now(&mut self, es: &Spec, card: CardId, actor: Side, extra: Option<&Extra>) -> R<Map<String, Value>> {
        let mut params = es.merged.clone();
        let instead = params.remove("instead");
        if let Some(instead) = instead {
            if truthy(Some(&instead)) {
                let cond = instead.get("condition").cloned();
                if self.check_condition(cond.as_ref(), card, actor, extra)? {
                    if let Some(o) = instead.as_object() {
                        for (k, v) in o {
                            if k != "condition" {
                                params.insert(k.clone(), v.clone());
                            }
                        }
                    }
                }
            }
        }
        Ok(params)
    }

    /// py: _instruction_runs
    pub fn instruction_runs(&mut self, card: CardId, i: Option<usize>, es: &Spec, actor: Side, extra: Option<&Extra>,
                            additional: bool, once: bool, checked: bool) -> R<bool> {
        if once {
            if let Some(i) = i {
                if self.once_used(card, i, es) {
                    return Ok(false);
                }
            } else if truthy(es.params.get("once_per_turn")) {
                // (card, None) never matches an int key: not used
            }
        }
        let gate = Game::kicker_gate(es, additional);
        if !checked && !gate && !self.check_condition(es.condition.as_ref(), card, actor, extra)? {
            return Ok(false);
        }
        if es.cost.is_some() && !self.triggered_cost_affordable(card, actor, es)? {
            return Ok(false);
        }
        if !self.wants_optional(actor, card, es)? {
            return Ok(false);
        }
        if !self.pay_triggered_cost(card, actor, es, additional)? {
            return Ok(false);
        }
        if gate && !self.check_condition(es.condition.as_ref(), card, actor, extra)? {
            return Ok(false);
        }
        if !crate::effects::exists(&es.effect) {
            return Ok(false);
        }
        if once && truthy(es.params.get("once_per_turn")) {
            let key = match i {
                Some(i) => OnceKey::Idx(i as i64),
                None => OnceKey::Str("None".into()),
            };
            let t = self.gs.turn;
            self.gs.once_per_turn_used.set(OnceK::Card(card, key), t);
        }
        Ok(true)
    }

    /// py: _flush_triggers(run=True)
    pub fn flush_triggers(&mut self, run: bool) -> R<()> {
        if self.flushing || self.pending_triggers.is_empty() {
            return Ok(());
        }
        let opened = self.gs.chain.is_empty();
        self.flushing = true;
        let res: R<()> = (|| {
            while !self.pending_triggers.is_empty() {
                let batch: Vec<PendingTrigger> = std::mem::take(&mut self.pending_triggers);
                let active = self.gs.active;
                for side in [active, active.other()] {
                    let mut mine: Vec<PendingTrigger> = batch.iter().filter(|p| p.side == side).cloned().collect();
                    if mine.len() > 1 {
                        let opts: Vec<Opt> = (0..mine.len()).map(Opt::Trigger).collect();
                        self.trigger_menu = mine.clone();
                        let got = self.choose_many("trigger_order", side, &opts, &opts.clone(), None, None, None);
                        self.trigger_menu.clear();
                        let got = got?;
                        mine = got
                            .iter()
                            .map(|o| match o {
                                Opt::Trigger(i) => mine[*i].clone(),
                                _ => unreachable!(),
                            })
                            .collect();
                    }
                    for p in mine.into_iter().rev() {
                        let Some(item) = self.finalize_trigger(p)? else { continue };
                        let ab = item.ability.as_ref().unwrap();
                        if ab.kind == "triggered"
                            && is_add_verb(&ab.eff.as_ref().unwrap().effect)
                            && ab.rest.iter().all(|(_, es)| is_add_verb(&es.effect))
                        {
                            self.resolve_ability(item)?;
                            continue;
                        }
                        self.put_on_chain(item)?;
                    }
                }
            }
            Ok(())
        })();
        self.flushing = false;
        res?;
        if run && opened && !self.gs.chain.is_empty() && self.resolving_item.is_none() {
            let p = self.gs.chain.last().unwrap().player;
            self.run_chain(p)?;
        }
        Ok(())
    }

    /// py: _finalize_trigger
    pub fn finalize_trigger(&mut self, mut p: PendingTrigger) -> R<Option<ChainItem>> {
        let (card, side) = (p.card, p.side);
        let bf_idx = p.bf;
        if p.replay.is_some() {
            not_ported!("_finalize_trigger", "reflexive replay (Death from Below)");
        }
        let specs = p.specs.clone();
        let extra = p.extra.clone();
        let (additional, once) = (p.additional, p.once);
        let mut flags = p.flags.take();
        let found = self.with_card_flags(card, &mut flags, |g| {
            for (n, (i, es)) in specs.iter().enumerate() {
                if g.instruction_runs(card, ix(*i), es, side, extra.as_ref(), additional, once, n == 0)? {
                    return Ok(Some(n));
                }
            }
            Ok(None)
        })?;
        let Some(n) = found else { return Ok(None) };
        let mut ab = Ability::new("triggered");
        ab.eff = Some(specs[n].1.clone());
        ab.extra = p.extra.clone().unwrap_or_default();
        ab.bf = Some(p.bf);
        ab.rest = specs[n + 1..].to_vec();
        ab.flags = flags;
        ab.trigger = Some(p.trigger.clone());
        ab.additional = p.additional;
        ab.once = p.once;
        ab.cond_extra = p.extra.clone();
        Ok(Some(ChainItem { uid: 0,
            player: side,
            card,
            bf_idx,
            declared: None,
            choices_noted: false,
            owner: None,
            ability: Some(ab),
        }))
    }

    /// py: _resolve_trigger
    pub fn resolve_trigger(&mut self, item: &mut ChainItem) -> R<()> {
        let card = item.card;
        let actor = item.player;
        let ab = item.ability.as_mut().unwrap();
        let mut ctx = Ctx::new(card, actor, ab.bf.unwrap_or(0));
        ctx.extra = ab.extra.clone();
        let outer_slot = self.slot;
        let mut instructions: Vec<(Option<usize>, Spec)> = vec![(None, ab.eff.clone().unwrap())];
        instructions.extend(ab.rest.iter().map(|(i, s)| (ix(*i), s.clone())));
        let cond_extra = ab.cond_extra.clone();
        let (additional, once) = (ab.additional, ab.once);
        let mut flags = ab.flags.take();
        let res = self.with_card_flags(card, &mut flags, |g| {
            let r: R<()> = (|| {
                for (n, (i, es)) in instructions.iter().enumerate() {
                    if n > 0 && truthy(es.params.get("reflexive")) {
                        not_ported!("_resolve_trigger", "reflexive (then you may do this)");
                    }
                    if n > 0 && !g.instruction_runs(card, *i, es, actor, cond_extra.as_ref(), additional, once, false)? {
                        continue;
                    }
                    if n == 0 && truthy(es.params.get("effect_condition"))
                        && !g.check_condition(es.condition.as_ref(), card, actor, cond_extra.as_ref())?
                    {
                        continue;
                    }
                    g.slot = Some([0, n as i64, 0]);
                    let early = g.choices_on_board_as_played(&ctx, es, 0, n as i64)?;
                    let has_early = early.as_ref().map_or(false, |e| !e.items.is_empty());
                    if has_early {
                        g.replay = Some(Declaring { card, choices: early.clone().unwrap() });
                    }
                    let params = g.params_now(es, card, actor, cond_extra.as_ref())?;
                    let r = g.call_handler(&mut ctx, &es.effect, &params);
                    if has_early {
                        g.replay = None;
                        if let Some(d) = g.declaring.as_mut() {
                            for (k, v) in early.unwrap().items {
                                if let Some(e) = d.choices.items.iter_mut().find(|(kk, _)| *kk == k) {
                                    e.1 = v;
                                } else {
                                    d.choices.items.push((k, v));
                                }
                            }
                        }
                    }
                    r?;
                }
                Ok(())
            })();
            g.slot = outer_slot;
            r
        });
        item.ability.as_mut().unwrap().flags = flags;
        res
    }

    /// py: _triggered_cost_affordable
    pub fn triggered_cost_affordable(&mut self, card: CardId, actor: Side, es: &Spec) -> R<bool> {
        let parsed = self.parse_activated_cost(es.cost.as_ref())?;
        if es.effect == "play_self_from_trash" {
            not_ported!("_triggered_cost_affordable", "play_self_from_trash");
        }
        let unit = self.find_unit_by_card(card);
        self.activated_affordable(actor, unit, &parsed)
    }

    /// py: _pay_triggered_cost
    pub fn pay_triggered_cost(&mut self, card: CardId, actor: Side, es: &Spec, additional: bool) -> R<bool> {
        let cost = es.cost.clone().filter(|c| truthy(Some(c)));
        let ac = if additional { es.additional_cost.clone().filter(|c| truthy(Some(c))) } else { None };
        if cost.is_none() && ac.is_none() {
            return Ok(true);
        }
        let unit = self.find_unit_by_card(card);
        if let Some(ac) = ac {
            if !self.pay_one_additional_cost(card, actor, &ac)? {
                return Ok(false);
            }
            self.gs.card_mut(card).set_kicker(Some(true));
        }
        if let Some(cost) = cost {
            let parsed = self.parse_activated_cost(Some(&cost))?;
            if es.effect == "play_self_from_trash" {
                not_ported!("_pay_triggered_cost", "play_self_from_trash");
            }
            if !self.activated_affordable(actor, unit, &parsed)? {
                return Ok(false);
            }
            let gear = if unit.is_none() && self.gs.is_gear_card(card) { Some(card) } else { None };
            if parsed.tap && gear.map_or(false, |g| self.gs.card(g).tapped) {
                return Ok(false);
            }
            if !self.pay_energy_and_generic(actor, parsed.energy, parsed.power, parsed.domain.clone())? {
                return Ok(false);
            }
            if parsed.tap {
                if let Some(u) = unit {
                    self.exhaust(u, None, None)?;
                }
                if let Some(g) = gear {
                    self.exhaust_gear(g, actor)?;
                }
            }
            self.recycle_from_trash(actor, parsed.recycle, &parsed.recycle_type)?;
            self.pay_discard_and_banish(actor, &parsed, unit)?;
            if parsed.spend_xp != 0 {
                self.gs.add_xp(actor, -parsed.spend_xp);
            }
            if parsed.sacrifice {
                if let Some(u) = unit {
                    self.remove_unit_from_play(u, actor)?;
                    let c = self.gs.ucard(u);
                    self.to_trash(actor, c)?;
                }
            }
            self.gs.card_mut(card).set_kicker(Some(true));
        }
        Ok(true)
    }

    /// py: _fire_units_trigger (a task)
    pub fn fire_units_trigger(&mut self, trigger: &str, side: Side, exclude_card: Option<CardId>,
                              triggering_card: Option<CardId>, extra: Option<Extra>) -> R<()> {
        self.as_task(|g| {
            let trig = triggering_card.or(exclude_card);
            let mk = |bf: usize| {
                let mut ex = Extra::default();
                ex.set("battlefield", XVal::Bf(bf));
                ex.set("triggering_card", match trig { Some(c) => XVal::Card(c), None => XVal::None });
                match &extra {
                    Some(e) => ex.merged(e),
                    None => ex,
                }
            };
            for i in 0..g.gs.battlefields.len() {
                for u in g.gs.battlefields[i].units_for(side).clone() {
                    let c = g.gs.ucard(u);
                    if Some(c) == exclude_card {
                        continue;
                    }
                    g.resolve_triggered_effects(c, trigger, i, side, Some(mk(i)))?;
                }
            }
            for u in g.gs.player(side).base_units.clone() {
                let c = g.gs.ucard(u);
                if Some(c) == exclude_card {
                    continue;
                }
                g.resolve_triggered_effects(c, trigger, 0, side, Some(mk(0)))?;
            }
            let mut listeners: Vec<CardId> = g.gs.player(side).base_gear.clone();
            listeners.extend(g.legend_units(side).iter().map(|&lu| g.gs.ucard(lu)));
            for c in listeners {
                if Some(c) == exclude_card {
                    continue;
                }
                g.resolve_triggered_effects(c, trigger, 0, side, Some(mk(0)))?;
            }
            Ok(())
        })
    }

    /// py: _fire_readied
    pub fn fire_readied(&mut self, unit: UnitId, side: Side) -> R<()> {
        let bf = self.locate_unit(unit).and_then(|(_, b)| b).unwrap_or(0);
        self.resolve_triggered_effects(self.gs.ucard(unit), "on_readied", bf, side, Some(bf_extra(bf)))?;
        let mut ex = Extra::default();
        ex.set("triggering_unit", XVal::Unit(unit));
        let c = self.gs.ucard(unit);
        self.fire_units_trigger("on_friendly_unit_readied", side, None, Some(c), Some(ex))
    }

    /// py: _note_chosen
    pub fn note_chosen(&mut self, source: CardId, chooser: Side, units: &[UnitId]) -> R<()> {
        if self.declaring.is_some() || self.choices_noted {
            return Ok(());
        }
        let enemy = chooser.other();
        let located: Vec<(UnitId, Option<(Side, Option<usize>)>)> = units.iter().map(|&u| (u, self.locate_unit(u))).collect();
        let mut tax = 0;
        for &u in units {
            tax += self.deflect_tax(u, chooser, Some(source))?;
        }
        tax = self.graceful_discount(Some(source), chooser, &located, tax)?;
        if tax != 0 {
            self.pay_generic_power(chooser, tax)?;
        }
        let from_spell_or_unit = self.gs.is_spell(source) || self.gs.is_unit_card(source);
        if from_spell_or_unit && located.iter().any(|(_, w)| w.map_or(false, |w| w.0 == enemy)) {
            self.gs.enemy_choices_this_turn[chooser.idx()] += 1;
        }
        for (unit, where_) in located {
            let Some((ws, wbf)) = where_ else { continue };
            if ws != chooser || self.gs.ucard(unit) == source {
                continue;
            }
            let mut ex = Extra::default();
            ex.set("triggering_unit", XVal::Unit(unit));
            self.fire_units_trigger("on_friendly_chosen", chooser, None, Some(source), Some(ex))?;
            let bf = wbf.unwrap_or(0);
            let mut ex = Extra::default();
            ex.set("battlefield", XVal::Bf(bf));
            ex.set("triggering_card", XVal::Card(source));
            self.resolve_triggered_effects(self.gs.ucard(unit), "on_chosen", bf, chooser, Some(ex))?;
        }
        Ok(())
    }

    /// py: _note_gear_chosen
    pub fn note_gear_chosen(&mut self, source: CardId, chooser: Side, gear_side: Side) {
        if self.declaring.is_none() && gear_side != chooser && (self.gs.is_spell(source) || self.gs.is_unit_card(source)) {
            self.gs.enemy_choices_this_turn[chooser.idx()] += 1;
        }
    }

    /// py: _graceful_discount (Irelia Graceful) — the EK part: no unit has the
    /// discount, the spell's `_graceful_from` is set to an empty set.
    pub fn graceful_discount(&mut self, source: Option<CardId>, chooser: Side,
                             located: &[(UnitId, Option<(Side, Option<usize>)>)], tax: i64) -> R<i64> {
        let Some(src) = source.filter(|&s| self.gs.is_spell(s)) else { return Ok(tax) };
        if self.gs.card(src).graceful_from.is_none() {
            self.gs.card_mut(src).graceful_from = Some(Value::Array(Vec::new()));
        }
        for (u, w) in located {
            let Some((ws, _)) = w else { continue };
            if *ws != chooser {
                continue;
            }
            if self.graceful_count(*u) != 0 {
                not_ported!("_graceful_discount", "Irelia Graceful");
            }
        }
        Ok(tax)
    }

    /// py: _graceful_count
    pub fn graceful_count(&self, unit: UnitId) -> i64 {
        self.card_effects_auto(self.gs.ucard(unit)).iter().filter(|es| es.effect == "cheaper_spells_choosing_me").count()
            as i64
    }
}
