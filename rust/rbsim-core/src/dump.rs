//! The raw state tree, in the format of riftbound/rs/canon.py RawDumper: the
//! same field names and value encodings, so the Python canonicalizer turns
//! both engines' dumps into comparable trees.

use serde_json::{json, Map, Value};

use crate::game::Game;
use crate::model::*;
use crate::pydict::PyDict;
use crate::types::*;

pub struct Dumper<'a> {
    g: &'a Game,
    objs: Map<String, Value>,
}

fn side(s: Side) -> Value {
    Value::String(s.name().into())
}
fn oside(s: Option<Side>) -> Value {
    s.map(side).unwrap_or(Value::Null)
}
fn sides_dict<T, F: Fn(&T) -> Value>(a: &[T; 2], f: F) -> Value {
    json!({"A": f(&a[0]), "B": f(&a[1])})
}
fn side_map<V: Clone, F: Fn(&V) -> Value>(d: &PyDict<Side, V>, f: F) -> Value {
    let mut m = Map::new();
    for (k, v) in d.iter() {
        m.insert(k.name().into(), f(v));
    }
    Value::Object(m)
}

impl<'a> Dumper<'a> {
    fn card(&mut self, c: CardId) -> Value {
        let key = format!("c{}", c.0);
        if !self.objs.contains_key(&key) {
            self.objs.insert(key.clone(), Value::Object(Map::new()));
            let v = self.card_fields(c);
            self.objs.insert(key.clone(), v);
        }
        json!({"$ref": key})
    }
    fn ocard(&mut self, c: Option<CardId>) -> Value {
        match c {
            Some(c) => self.card(c),
            None => Value::Null,
        }
    }
    fn unit(&mut self, u: UnitId) -> Value {
        let key = format!("u{}", u.0);
        if !self.objs.contains_key(&key) {
            self.objs.insert(key.clone(), Value::Object(Map::new()));
            let v = self.unit_fields(u);
            self.objs.insert(key.clone(), v);
        }
        json!({"$ref": key})
    }
    fn ounit(&mut self, u: Option<UnitId>) -> Value {
        match u {
            Some(u) => self.unit(u),
            None => Value::Null,
        }
    }
    fn dgear(&mut self, d: GearId) -> Value {
        let key = format!("g{}", d.0);
        if !self.objs.contains_key(&key) {
            let dg = &self.g.gs.dgear[d.i()];
            let (c, t) = (dg.card, dg.is_token);
            self.objs.insert(key.clone(), Value::Object(Map::new()));
            let cv = self.card(c);
            self.objs.insert(key.clone(), json!({"$t": "DeployedGear", "card": cv, "is_token": t}));
        }
        json!({"$ref": key})
    }
    fn bf(&mut self, b: usize) -> Value {
        let key = format!("b{b}");
        if !self.objs.contains_key(&key) {
            self.objs.insert(key.clone(), Value::Object(Map::new()));
            let v = self.bf_fields(b);
            self.objs.insert(key.clone(), v);
        }
        json!({"$ref": key})
    }
    fn cards(&mut self, v: &[CardId]) -> Value {
        Value::Array(v.iter().map(|&c| self.card(c)).collect())
    }
    fn units(&mut self, v: &[UnitId]) -> Value {
        Value::Array(v.iter().map(|&u| self.unit(u)).collect())
    }

    fn card_fields(&mut self, c: CardId) -> Value {
        let card = self.g.gs.card(c).clone();
        let mut m = Map::new();
        m.insert("$t".into(), "Card".into());
        m.insert("name".into(), Value::String(self.g.gs.name(c).to_string()));
        m.insert("tapped".into(), Value::Bool(card.tapped));
        let mut put = |m: &mut Map<String, Value>, k: &str, v: Option<Value>| {
            if let Some(v) = v {
                if !v.is_null() {
                    m.insert(k.into(), v);
                }
            }
        };
        if let Some(u) = card.attached_to {
            let v = self.unit(u);
            put(&mut m, "_attached_to", Some(v));
        }
        put(&mut m, "_attached_turn", card.attached_turn.map(Value::from));
        if let Some(cc) = card.chosen_card {
            let v = self.card(cc);
            put(&mut m, "_chosen_card", Some(v));
        }
        put(&mut m, "_graceful_from", card.graceful_from.map(|_| json!({"$set": []})));
        if let Some(owed) = card.graceful_owed.clone() {
            let v = self.units(&owed);
            put(&mut m, "_graceful_owed", Some(v));
        }
        put(&mut m, "_graceful_prepaid", card.graceful_prepaid.clone());
        put(&mut m, "_granted_repeat", card.granted_repeat.clone());
        put(&mut m, "_kicker_paid", card.kicker_paid.map(Value::Bool));
        put(&mut m, "_owner", card.owner.map(side));
        put(&mut m, "_play_pending", card.play_pending.clone());
        put(&mut m, "_played_from", card.played_from.clone().map(Value::String));
        put(&mut m, "_power_paid", card.power_paid.map(Value::from));
        put(&mut m, "_repeat_extra", card.repeat_extra.clone());
        put(&mut m, "_repeat_paid", card.repeat_paid.clone());
        put(&mut m, "_showed_off", card.showed_off.map(Value::Bool));
        put(&mut m, "_shown", card.shown.clone());
        put(&mut m, "_spent", card.spent.map(Value::from));
        put(&mut m, "_hidden_bf", card.hidden_bf.map(|b| Value::from(b as i64)));
        put(&mut m, "_temporary", card.temporary.map(Value::Bool));
        put(&mut m, "empowered", card.empowered.map(Value::Bool));
        put(&mut m, "_flow_banish", card.flow_banish.map(Value::Bool));
        put(&mut m, "is_token", card.is_token.map(Value::Bool));
        Value::Object(m)
    }

    fn spec(&self, s: &crate::registry::Spec) -> Value {
        json!({"$spec": s.spec_ref})
    }

    fn unit_fields(&mut self, u: UnitId) -> Value {
        let x = self.g.gs.unit(u).clone();
        let cv = self.card(x.card);
        let gv = self.cards(&x.gear);
        let ta: Vec<Value> = x.turn_abilities.iter().map(|(t, s)| json!([t, self.spec(s)])).collect();
        let copied = self.ocard(x.copied_from);
        json!({
            "$t": "UnitInPlay", "card": cv, "damage": x.damage, "ready": x.ready, "bonus_might": x.bonus_might,
            "temporary_might": x.temporary_might, "gear": gv, "stunned": x.stunned, "might_counters": x.might_counters,
            "aura_might": x.aura_might, "passive_might": x.passive_might, "passive_keywords": x.passive_keywords,
            "hidden": x.hidden, "empowered": x.empowered, "empower_times": x.empower_times, "is_token": x.is_token,
            "no_combat_damage": x.no_combat_damage, "turn_keywords": x.turn_keywords, "granted_keywords": x.granted_keywords,
            "combat_keywords": x.combat_keywords, "combat_might": x.combat_might, "doomed_turn": x.doomed_turn,
            "ward_turn": x.ward_turn, "prevent_next_turn": x.prevent_next_turn, "was_mighty": x.was_mighty,
            "ward_free": x.ward_free, "banish_if_dies_turn": x.banish_if_dies_turn, "death_bonus": x.death_bonus,
            "damaged_turn": x.damaged_turn, "unmovable_by_enemies": x.unmovable_by_enemies, "turn_abilities": ta,
            "win_xp_turn": x.win_xp_turn, "cant_move_turn": x.cant_move_turn, "equip_bonus_mult": x.equip_bonus_mult,
            "base_might_override": x.base_might_override, "moves_this_turn": x.moves_this_turn,
            "unchoosable": x.unchoosable, "cant_be_chosen_turn": x.cant_be_chosen_turn,
            "no_move_to_base": x.no_move_to_base, "cant_ready": x.cant_ready, "spell_immune": x.spell_immune,
            "double_damage_turn": x.double_damage_turn, "damage_shield": x.damage_shield,
            "conquered_turn": x.conquered_turn, "borrowed": x.borrowed.map(|(s, t)| json!([s.name(), t])),
            "extra_tags": x.extra_tags, "copied_from": copied, "gear_unit": x.gear_unit,
        })
    }

    fn bf_fields(&mut self, b: usize) -> Value {
        let bf = self.g.gs.battlefields[b].clone();
        let ua = self.units(&bf.units[0]);
        let ub = self.units(&bf.units[1]);
        let card = self.ocard(bf.card);
        let replaced = self.ocard(bf.replaced);
        let fds: Vec<Value> = bf
            .facedowns
            .iter()
            .map(|f| {
                let c = self.card(f.card);
                json!({"$v": {"$t": "FacedownCard", "card": c, "owner": f.owner.name(), "turn_hidden": f.turn_hidden}})
            })
            .collect();
        let cd: Vec<Value> = bf.combat_designated.iter().map(|&u| self.unit(u)).collect();
        let ga: Vec<Value> = bf.gear[0].iter().map(|&d| self.dgear(d)).collect();
        let gb: Vec<Value> = bf.gear[1].iter().map(|&d| self.dgear(d)).collect();
        let mut m = json!({
            "$t": "Battlefield", "units_A": ua, "units_B": ub, "contested_this_turn": bf.contested_this_turn,
            "scored_this_turn_A": bf.scored_this_turn[0], "scored_this_turn_B": bf.scored_this_turn[1],
            "first_unit_here_A": bf.first_unit_here[0], "first_unit_here_B": bf.first_unit_here[1],
            "plays_here": side_map(&bf.plays_here, |(t, n)| json!([t, n])),
            "last_controller": oside(bf.last_controller), "held_by": oside(bf.held_by),
            "gained_control": oside(bf.gained_control), "contested_by": oside(bf.contested_by),
            "showdown_pending": bf.showdown_pending, "card": card, "replaced": replaced, "facedowns": fds,
            "conquered_turn": side_map(&bf.conquered_turn, |t| json!(t)),
            "excess_damage": side_map(&bf.excess_damage, |(t, n)| json!([t, n])),
            "combat_designated": {"$set": cd}, "combat_started": bf.combat_started,
            "combat_attacker": oside(bf.combat_attacker), "gear_A": ga, "gear_B": gb,
            "kills_A": bf.kills[0], "kills_B": bf.kills[1], "deaths_A": bf.deaths[0], "deaths_B": bf.deaths[1],
        });
        if let Some(pc) = bf.prev_controller {
            m["prev_controller"] = oside(pc);
        }
        m
    }

    fn domain_dict<V: Clone, F: Fn(&V) -> Value>(d: &PyDict<Domain, V>, f: F) -> Value {
        if d.is_empty() {
            return json!({});
        }
        json!({"$dict": d.iter().map(|(k, v)| json!([k.name(), f(v)])).collect::<Vec<_>>()})
    }

    fn player(&mut self, s: Side) -> Value {
        let p = self.g.gs.player(s).clone();
        let hand = self.cards(&p.hand);
        let hp = self.cards(&p.hand_public);
        let dc = self.cards(&p.deck.cards);
        let dk = self.cards(&p.deck.known_top);
        let trash = self.cards(&p.trash);
        let ban = self.cards(&p.banished);
        let bg = self.cards(&p.base_gear);
        let bu = self.units(&p.base_units);
        let runes: Vec<Value> = p.rune_deck.runes.iter().map(|r| json!({"$v": {"$t": "Rune", "domain": r.domain.name(), "ready": r.ready}})).collect();
        let mut m = json!({"$t": "Player", "name": s.name(), "hp": p.hp, "hand": hand, "hand_public": hp,
            "deck": {"$v": {"$t": "Deck", "cards": dc, "known_top": dk}},
            "trash": trash, "banished": ban, "base_gear": bg, "rune_energy": p.rune_energy, "pool_energy": p.pool_energy,
            "earmarked_energy_showdown": p.earmarked_energy_showdown, "earmarked_power_gear": p.earmarked_power_gear,
            "earmarked_power_spell": p.earmarked_power_spell, "earmarked_power_permanent": p.earmarked_power_permanent,
            "earmarked_energy_spell": p.earmarked_energy_spell, "earmarked_energy_unit": p.earmarked_energy_unit,
            "rune_deck": {"$v": {"$t": "RuneDeck", "runes": runes, "unseen": p.rune_deck.unseen}},
            "rune_pool": Self::domain_dict(&p.rune_pool, |rs: &Vec<Rune>| Value::Array(rs.iter().map(|r| json!({"$v": {"$t": "Rune", "domain": r.domain.name(), "ready": r.ready}})).collect())),
            "power_pool": Self::domain_dict(&p.power_pool, |n| json!(n)),
            "floating_power": Self::domain_dict(&p.floating_power, |n| json!(n)),
            "power_spent_this_turn": p.power_spent_this_turn, "draws_this_turn": p.draws_this_turn, "base_units": bu,
        });
        if let Some(n) = p.runes_recycled {
            m["runes_recycled"] = json!(n);
        }
        if self.g.agents[s.idx()].is_some() || p.has_agent {
            // GameLoop.__init__: agent.player.battlefields = gs.battlefields
            let bfs: Vec<Value> = (0..self.g.gs.battlefields.len()).map(|b| self.bf(b)).collect();
            m["battlefields"] = Value::Array(bfs);
        }
        json!({"$v": m})
    }

    fn xval(&mut self, v: &XVal) -> Value {
        match v {
            XVal::Bf(b) => self.bf(*b),
            XVal::Unit(u) => self.unit(*u),
            XVal::Card(c) => self.card(*c),
            XVal::Side(s) => side(*s),
            XVal::Int(i) => json!(i),
            XVal::Bool(b) => json!(b),
            XVal::Str(s) => json!(s),
            XVal::None => Value::Null,
            XVal::Json(j) => j.clone(),
            XVal::List(l) => Value::Array(l.iter().map(|x| self.xval(x)).collect()),
        }
    }

    fn extra(&mut self, e: &Extra) -> Value {
        let mut m = Map::new();
        for (k, v) in e.items.iter() {
            let vv = self.xval(v);
            m.insert(k.clone(), vv);
        }
        Value::Object(m)
    }

    fn opt(&mut self, o: &Opt) -> Value {
        match o {
            Opt::Unit(u) => self.unit(*u),
            Opt::Card(c) => self.card(*c),
            Opt::Bf(b) => self.bf(*b),
            Opt::Gear(g) => self.dgear(*g),
            Opt::Bool(b) => json!(b),
            Opt::Int(i) => json!(i),
            Opt::Domain(d) => json!(d.name()),
            Opt::Side(s) => side(*s),
            Opt::Chain(i) => json!({"$chain": i}),
            Opt::Trigger(i) => match self.g.trigger_menu.get(*i).cloned() {
                Some(p) => self.pending(&p),
                None => json!({"$trigger": i}),
            },
            Opt::NoMore => json!("$NO_MORE"),
            Opt::Str(s) => json!(s),
            Opt::Tuple(v) => Value::Array(v.iter().map(|x| self.opt(x)).collect()),
            Opt::None => Value::Null,
        }
    }

    fn chain_item(&mut self, it: &ChainItem) -> Value {
        let card = self.card(it.card);
        let declared = match &it.declared {
            None => Value::Null,
            Some(d) if d.items.is_empty() => json!({}),
            Some(d) => {
                let rows: Vec<Value> = d
                    .items
                    .iter()
                    .map(|(k, (kind, n, got))| {
                        let g = match got {
                            Chosen::One(o) => self.opt(o),
                            Chosen::Many(v) => Value::Array(v.iter().map(|o| self.opt(o)).collect()),
                        };
                        json!([[k.0, k.1, k.2], [kind, n, g]])
                    })
                    .collect();
                json!({"$dict": rows})
            }
        };
        let ability = match &it.ability {
            None => Value::Null,
            Some(a) => {
                let mut m = Map::new();
                m.insert("eff".into(), a.eff.as_ref().map(|s| self.spec(s)).unwrap_or(Value::Null));
                m.insert("kind".into(), json!(a.kind));
                m.insert("energy".into(), json!(a.energy));
                let ex = self.extra(&a.extra);
                m.insert("extra".into(), ex);
                let t = self.ounit(a.target);
                m.insert("target".into(), t);
                if a.kind == "triggered" {
                    let bf = self.bf(a.bf.unwrap_or(0));
                    m.insert("bf".into(), bf);
                    let rest: Vec<Value> = a.rest.iter().map(|(i, s)| json!([i, self.spec(s)])).collect();
                    m.insert("rest".into(), Value::Array(rest));
                    let fl = match &a.flags {
                        Some(f) => {
                            let mut fm = Map::new();
                            for (k, v) in f.iter() {
                                let vv = self.xval(v);
                                fm.insert(k.clone(), vv);
                            }
                            Value::Object(fm)
                        }
                        None => Value::Null,
                    };
                    m.insert("flags".into(), fl);
                    m.insert("trigger".into(), a.trigger.clone().map(Value::String).unwrap_or(Value::Null));
                    m.insert("additional".into(), json!(a.additional));
                    m.insert("once".into(), json!(a.once));
                    let ce = match &a.cond_extra {
                        Some(e) => self.extra(e),
                        None => Value::Null,
                    };
                    m.insert("cond_extra".into(), ce);
                }
                Value::Object(m)
            }
        };
        json!({"$v": {"$t": "ChainItem", "player": it.player.name(), "card": card, "bf_idx": it.bf_idx,
                       "declared": declared, "choices_noted": it.choices_noted, "owner": oside(it.owner), "ability": ability}})
    }

    fn pending(&mut self, p: &PendingTrigger) -> Value {
        let card = self.card(p.card);
        let bf = self.bf(p.bf);
        let specs: Vec<Value> = p.specs.iter().map(|(i, s)| json!([i, self.spec(s)])).collect();
        let extra = match &p.extra {
            Some(e) => self.extra(e),
            None => Value::Null,
        };
        let flags = match &p.flags {
            Some(f) => {
                let mut fm = Map::new();
                for (k, v) in f.iter() {
                    let vv = self.xval(v);
                    fm.insert(k.clone(), vv);
                }
                Value::Object(fm)
            }
            None => Value::Null,
        };
        json!({"$v": {"$t": "PendingTrigger", "card": card, "trigger": p.trigger, "side": p.side.name(), "bf": bf,
                       "specs": specs, "extra": extra, "additional": p.additional, "flags": flags, "once": p.once,
                       "replay": p.replay}})
    }

    fn once_key(&mut self, k: &OnceK) -> Value {
        match k {
            OnceK::Card(c, OnceKey::Idx(i)) => {
                let cv = self.card(*c);
                json!([cv, i])
            }
            OnceK::Card(c, OnceKey::Str(s)) => {
                let cv = self.card(*c);
                let mut v = vec![cv];
                for p in s.split('|') {
                    match p.parse::<i64>() {
                        Ok(n) => v.push(json!(n)),
                        Err(_) => v.push(json!(p)),
                    }
                }
                Value::Array(v)
            }
            OnceK::Card(c, OnceKey::Json(j)) => {
                let cv = self.card(*c);
                json!([cv, j])
            }
            OnceK::Named(s, sd) => json!([s, sd.name()]),
        }
    }
}

impl Game {
    /// The raw dump {"root": ..., "objs": ...} (canon.raw_state's format).
    pub fn raw_dump(&self) -> Value {
        let mut d = Dumper { g: self, objs: Map::new() };
        let gs = &self.gs;
        let pa = d.player(Side::A);
        let pb = d.player(Side::B);
        let champ = [d.ocard(gs.champion[0]), d.ocard(gs.champion[1])];
        let leg = [d.ocard(gs.legend[0]), d.ocard(gs.legend[1])];
        let lu = [d.ounit(gs.legend_unit[0]), d.ounit(gs.legend_unit[1])];
        let el = [d.cards(&gs.extra_legends[0]), d.cards(&gs.extra_legends[1])];
        let al: Vec<Value> = (0..2)
            .map(|i| Value::Array(gs.added_legends[i].iter().map(|(a, b)| json!([d.unit(*a), d.unit(*b)])).collect()))
            .collect();
        let bfs: Vec<Value> = (0..gs.battlefields.len()).map(|b| d.bf(b)).collect();
        let chain: Vec<Value> = gs.chain.iter().map(|it| d.chain_item(it)).collect();
        let played = [d.cards(&gs.played_cards_this_turn[0]), d.cards(&gs.played_cards_this_turn[1])];
        let once = if gs.once_per_turn_used.is_empty() {
            json!({})
        } else {
            let rows: Vec<Value> = gs.once_per_turn_used.iter().map(|(k, t)| json!([d.once_key(k), t])).collect();
            json!({"$dict": rows})
        };
        let modes = if gs.modes_chosen.is_empty() {
            json!({})
        } else {
            let rows: Vec<Value> = gs.modes_chosen.iter().map(|((c, t), v)| json!([[d.card(*c), t], {"$set": v}])).collect();
            json!({"$dict": rows})
        };
        let held: Vec<Value> = gs.held_hostage.iter().map(|(s, c)| json!([s.name(), d.card(*c)])).collect();
        let jhin = side_map(&gs.jhin_pile, |v: &Vec<CardId>| json!(v.iter().map(|c| format!("c{}", c.0)).collect::<Vec<_>>()));
        let cr: Vec<Value> = gs.conquer_return.iter().map(|(u, t)| json!([d.unit(*u), t])).collect();
        let mut rab = Map::new();
        for (k, v) in gs.runes_at_beginning.1.iter() {
            rab.insert(k.name().into(), json!(v));
        }
        let root = json!({
            "$t": "GameState", "A": pa, "B": pb, "turn": gs.turn, "max_turns": gs.max_turns, "active": gs.active.name(),
            "champion_A": champ[0], "champion_B": champ[1], "legend_A": leg[0], "legend_B": leg[1],
            "legend_unit_A": lu[0], "legend_unit_B": lu[1],
            "extra_legends": {"A": el[0], "B": el[1]}, "added_legends": {"A": al[0], "B": al[1]},
            "points_A": gs.points[0], "points_B": gs.points[1], "victory_score": gs.victory_score,
            "winner": oside(gs.winner), "battlefields": bfs,
            "champion_A_deployed": gs.champion_deployed[0], "champion_B_deployed": gs.champion_deployed[1],
            "chain": chain, "pending_move": gs.pending_move.map(|(b, s)| json!([b, s.name()])),
            "staged_showdowns": gs.staged_showdowns.iter().map(|(b, s)| json!([b, s.name()])).collect::<Vec<_>>(),
            "showdown_active": gs.showdown_active, "showdown_bf_idx": gs.showdown_bf_idx,
            "showdown_attacker": oside(gs.showdown_attacker), "focus_player": oside(gs.focus_player),
            "xp_A": gs.xp[0], "xp_B": gs.xp[1],
            "cards_played_this_turn": sides_dict(&gs.cards_played_this_turn, |n| json!(n)),
            "spells_played_this_turn": sides_dict(&gs.spells_played_this_turn, |n| json!(n)),
            "played_cards_this_turn": {"A": played[0], "B": played[1]},
            "enemy_choices_this_turn": sides_dict(&gs.enemy_choices_this_turn, |n| json!(n)),
            "next_card_discounts": sides_dict(&gs.next_card_discounts, |v| json!(v)),
            "delayed_effects": gs.delayed_effects, "delayed_main": gs.delayed_main,
            "once_per_turn_used": once,
            "xp_gained_turn": side_map(&gs.xp_gained_turn, |t| json!(t)),
            "no_spell_damage_turn": gs.no_spell_damage_turn, "decree_turn": gs.decree_turn,
            "next_spell_bonus": side_map(&gs.next_spell_bonus, |t| json!(t)),
            "modes_chosen": modes,
            "next_unit_any_bf": side_map(&gs.next_unit_any_bf, |t| json!(t)),
            "next_unit_accelerate": side_map(&gs.next_unit_accelerate, |t| json!(t)),
            "next_spell_repeat": side_map(&gs.next_spell_repeat, |t| json!(t)),
            "held_hostage": held,
            "move_group": gs.move_group.map(|(t, s, dst, c)| json!([t, s.name(), dst, c])),
            "jhin_pile": jhin,
            "spell_spent": side_map(&gs.spell_spent, |(t, n)| json!([t, n])),
            "turn_cost_changes": gs.turn_cost_changes,
            "extra_turns": gs.extra_turns.iter().map(|s| s.name()).collect::<Vec<_>>(),
            "free_hide": side_map(&gs.free_hide, |t| json!(t)),
            "buff_bonus_turn": side_map(&gs.buff_bonus_turn, |t| json!(t)),
            "rally_turn": side_map(&gs.rally_turn, |t| json!(t)),
            "conquer_return": cr,
            "cant_play_spells_turn": side_map(&gs.cant_play_spells_turn, |t| json!(t)),
            "next_unit_ready_buff": side_map(&gs.next_unit_ready_buff, |t| json!(t)),
            "died_in_beginning": side_map(&gs.died_in_beginning, |t| json!(t)),
            "in_beginning_phase": gs.in_beginning_phase,
            "runes_at_beginning": [gs.runes_at_beginning.0, Value::Object(rab)],
            "in_ending_phase": gs.in_ending_phase,
            "turns_taken": sides_dict(&gs.turns_taken, |n| json!(n)),
            "cant_play_cards_turn": side_map(&gs.cant_play_cards_turn, |t| json!(t)),
            "unit_play_draws": side_map(&gs.unit_play_draws, |(t, n)| json!([t, n])),
            "units_enter_ready_turn": sides_dict(&gs.units_enter_ready_turn, |n| json!(n)),
            "next_units_enter_ready": sides_dict(&gs.next_units_enter_ready, |n| json!(n)),
            "friendly_unit_died_this_turn": sides_dict(&gs.friendly_unit_died_this_turn, |b| json!(b)),
            "friendly_gear_died_this_turn": sides_dict(&gs.friendly_gear_died_this_turn, |b| json!(b)),
            "discarded_this_turn": sides_dict(&gs.discarded_this_turn, |b| json!(b)),
            "cards_burned_this_turn": sides_dict(&gs.cards_burned_this_turn, |n| json!(n)),
            "conquered_this_turn": sides_dict(&gs.conquered_this_turn, |n| json!(n)),
            "hold_points_this_turn": sides_dict(&gs.hold_points_this_turn, |n| json!(n)),
            "$rng": gs.rng.digest(),
        });
        json!({"root": root, "objs": Value::Object(d.objs)})
    }

    /// An option of a choice, raw (for the trace).
    pub fn raw_opt(&self, o: &Opt) -> Value {
        let mut d = Dumper { g: self, objs: Map::new() };
        let v = d.opt(o);
        json!({"root": {"o": v}, "objs": Value::Object(d.objs)})
    }
}
