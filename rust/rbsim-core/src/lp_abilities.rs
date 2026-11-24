//! py: loop.py — activated abilities: the window, the list of entries,
//! timings, FLOW, playing from a zone, whether an entry is usable, ability
//! costs (_parse_activated_cost) and their extra payments, gear leaving play.

use serde_json::{Map, Value};

use crate::cards::{py_int, truthy};
use crate::game::*;
use crate::lp_phases::py_str;
use crate::lp_triggers::Ctx;
use crate::model::*;
use crate::not_ported;
use crate::registry::Spec;
use crate::types::*;

/// py: the dict _parse_activated_cost returns.
#[derive(Clone, Debug, PartialEq, Default)]
pub struct ParsedCost {
    pub energy: i64,
    pub power: i64,
    pub domain: Option<Domain>,
    pub tap: bool,
    pub recycle: i64,
    pub recycle_type: Option<String>,
    pub banish_self: bool,
    pub sacrifice: bool,
    pub spend_xp: i64,
    pub disempower: bool,
    pub banish_from_trash: Option<Value>,
    pub banish_any_trash: bool,
    pub discard: i64,
    pub discard_type: Option<String>,
    pub spend_buff: Option<String>,
    pub kill_other_token: bool,
    pub kill_other_friendly: bool,
    pub kill_friendly_gear: bool,
    pub exhaust_friendly_unit: Option<Value>,
}

/// py: an activatable_abilities entry.
#[derive(Clone, Debug)]
pub enum AbilityEntry {
    Ability { unit: UnitId, bf_idx: Option<usize>, eff: Spec, copy: i64 },
    GearAbility { gear: CardId, eff: Spec },
    BfAbility { bf: usize, eff: Spec },
    Equip { gear: CardId },
    Flow { card: CardId },
    TrashPlay { card: CardId, cost: Option<Value>, cond: Option<Value> },
    BanishedPlay { card: CardId },
}

impl AbilityEntry {
    pub fn type_name(&self) -> &'static str {
        match self {
            AbilityEntry::Ability { .. } => "ability",
            AbilityEntry::GearAbility { .. } => "gear_ability",
            AbilityEntry::BfAbility { .. } => "bf_ability",
            AbilityEntry::Equip { .. } => "equip",
            AbilityEntry::Flow { .. } => "flow",
            AbilityEntry::TrashPlay { .. } => "trash_play",
            AbilityEntry::BanishedPlay { .. } => "banished_play",
        }
    }
    pub fn eff(&self) -> Option<&Spec> {
        match self {
            AbilityEntry::Ability { eff, .. } | AbilityEntry::GearAbility { eff, .. } | AbilityEntry::BfAbility { eff, .. } => Some(eff),
            _ => None,
        }
    }
}

fn timing_of(es: &Spec) -> Option<String> {
    es.timing.as_ref().map(|t| t.to_lowercase()).filter(|t| !t.is_empty())
}

fn allowed_in(window: &str, t: &Option<String>) -> bool {
    match window {
        "main" => t.is_none() || t.as_deref() == Some("action") || t.as_deref() == Some("reaction"),
        "showdown" => matches!(t.as_deref(), Some("action") | Some("reaction")),
        _ => t.as_deref() == Some("reaction"),
    }
}

/// py: _parse_activated_cost(cost)
pub fn parse_activated_cost(cost: Option<&Value>) -> ParsedCost {
    let mut p = ParsedCost::default();
    let Some(cost) = cost else { return p };
    match cost {
        Value::Object(c) => {
            let gi = |k: &str| c.get(k).map(py_int).unwrap_or(0);
            p.energy = gi("energy");
            p.power = gi("power");
            p.domain = c.get("domain").filter(|v| truthy(Some(v))).and_then(|v| Domain::from_py(&py_str(v)));
            p.tap = truthy(c.get("tap")) || truthy(c.get("exhaust_self")) || truthy(c.get("exhaust"));
            p.recycle = match c.get("recycle_from_trash") {
                Some(v) => py_int(v),
                None => gi("recycle"),
            };
            p.recycle_type = c.get("recycle_type").filter(|v| !v.is_null()).map(py_str);
            p.banish_self = truthy(c.get("banish_self"));
            p.sacrifice = truthy(c.get("sacrifice_self")) || truthy(c.get("kill_friendly"));
            p.spend_xp = gi("spend_xp");
            p.disempower = truthy(c.get("disempower_self"));
            p.banish_from_trash = c.get("banish_from_trash").filter(|v| !v.is_null()).cloned();
            p.banish_any_trash = truthy(c.get("any_trash"));
            p.discard = gi("discard");
            p.discard_type = c.get("discard_type").filter(|v| !v.is_null()).map(py_str);
            p.spend_buff = c.get("spend_buff").filter(|v| !v.is_null()).map(py_str);
            p.kill_other_token = truthy(c.get("kill_other_token"));
            p.kill_other_friendly = truthy(c.get("kill_other_friendly"));
            p.kill_friendly_gear = truthy(c.get("kill_friendly_gear"));
            p.exhaust_friendly_unit = c.get("exhaust_friendly_unit").filter(|v| !v.is_null()).cloned();
        }
        Value::String(s) => {
            for tok in s.split(',') {
                let t = tok.trim().to_lowercase();
                if t == "tap" || t == "exhaust" || t == "exhaust_self" {
                    p.tap = true;
                } else if t.starts_with("recycle") {
                    p.recycle = t.chars().skip_while(|c| !c.is_ascii_digit()).take_while(|c| c.is_ascii_digit())
                        .collect::<String>().parse().unwrap_or(1);
                } else if !t.is_empty() && t.chars().all(|c| c.is_ascii_digit()) {
                    p.energy = t.parse().unwrap_or(0);
                }
            }
        }
        _ => {}
    }
    p
}

impl Game {
    pub fn parse_activated_cost(&self, cost: Option<&Value>) -> R<ParsedCost> {
        Ok(parse_activated_cost(cost))
    }

    /// py: _ability_window
    pub fn ability_window(&self, side: Side) -> &'static str {
        if !self.gs.chain.is_empty() {
            "reaction"
        } else if self.gs.showdown_active {
            "showdown"
        } else if side == self.gs.active {
            "main"
        } else {
            "reaction"
        }
    }

    /// py: _once_key(src, eff, entry)
    pub fn once_key(src: CardId, eff: &Spec, copy: i64) -> OnceK {
        let tag = if copy != 0 { format!("activated|{}|{}", eff.effect, copy) } else { format!("activated|{}", eff.effect) };
        OnceK::Card(src, OnceKey::Str(tag))
    }

    /// py: activatable_abilities(side)
    pub fn activatable_abilities(&mut self, side: Side) -> R<Vec<AbilityEntry>> {
        let window = self.ability_window(side);
        let mut out: Vec<AbilityEntry> = Vec::new();
        let abilities = |g: &Game, card: CardId| -> Vec<Spec> {
            g.gs.spec(card)
                .effects
                .iter()
                .filter(|e| e.trigger == "activated" && truthy(e.cost.as_ref()) && allowed_in(window, &timing_of(e)))
                .cloned()
                .collect()
        };
        let add_unit = |g: &mut Game, out: &mut Vec<AbilityEntry>, unit: UnitId, bf_idx: Option<usize>| -> R<()> {
            let t = g.gs.turn;
            for (turn, eff) in g.gs.unit(unit).turn_abilities.clone() {
                if turn == t && allowed_in(window, &timing_of(&eff)) {
                    out.push(AbilityEntry::Ability { unit, bf_idx, eff, copy: 0 });
                }
            }
            let copies = g.gs.unit(unit).gear.iter().filter(|&&gc| g.has_effect(gc, "copy_unit_text")).count() as i64;
            for eff in abilities(g, g.gs.ucard(unit)) {
                if eff.effect == "empower_self" && g.gs.unit(unit).empowered
                    && g.gs.unit(unit).empower_times.max(1) >= eff.params.get("max_times").map(py_int).unwrap_or(1)
                {
                    continue;
                }
                out.push(AbilityEntry::Ability { unit, bf_idx, eff: eff.clone(), copy: 0 });
                if truthy(eff.params.get("once_per_turn")) {
                    for c in 1..=copies {
                        out.push(AbilityEntry::Ability { unit, bf_idx, eff: eff.clone(), copy: c });
                    }
                }
            }
            if g.has_effect(g.gs.ucard(unit), "copy_tap_abilities") {
                not_ported!("activatable_abilities", "copy_tap_abilities (Heimerdinger Inventor)");
            }
            Ok(())
        };
        let add_gear = |g: &Game, out: &mut Vec<AbilityEntry>, gear: CardId| {
            for eff in abilities(g, gear) {
                if crate::effects::exists(&eff.effect) {
                    out.push(AbilityEntry::GearAbility { gear, eff });
                }
            }
        };
        for bf_idx in 0..self.gs.battlefields.len() {
            for unit in self.gs.battlefields[bf_idx].units_for(side).clone() {
                add_unit(self, &mut out, unit, Some(bf_idx))?;
                if let Some(bc) = self.gs.battlefields[bf_idx].card {
                    for e in self.gs.spec(bc).effects.iter() {
                        if e.trigger == "granted_to_units_here" && truthy(e.cost.as_ref()) && allowed_in(window, &timing_of(e)) {
                            not_ported!("activatable_abilities", "granted_to_units_here");
                        }
                    }
                }
            }
            if let Some(bc) = self.gs.battlefields[bf_idx].card {
                if window == "main" {
                    for eff in abilities(self, bc) {
                        out.push(AbilityEntry::BfAbility { bf: bf_idx, eff });
                    }
                }
            }
        }
        for unit in self.gs.player(side).base_units.clone() {
            add_unit(self, &mut out, unit, None)?;
        }
        for lu in self.legend_units(side) {
            add_unit(self, &mut out, lu, None)?;
            let mut granters: Vec<CardId> = Vec::new();
            for i in 0..self.gs.battlefields.len() {
                if let Some(c) = self.gs.battlefields[i].card {
                    if self.gs.battlefields[i].control() == Some(side) {
                        granters.push(c);
                    }
                }
            }
            let lc = self.gs.ucard(lu);
            granters.extend(self.sources_in_play(side).into_iter().map(|(s, _)| s).filter(|&s| s != lc));
            for src in granters {
                for eff in self.gs.spec(src).effects.iter() {
                    if eff.trigger == "granted_to_legend" && allowed_in(window, &timing_of(eff)) {
                        not_ported!("activatable_abilities", "granted_to_legend");
                    }
                }
            }
        }
        for gear in self.gs.player(side).base_gear.clone() {
            if window == "main" && self.equip_cost(gear).is_some() {
                out.push(AbilityEntry::Equip { gear });
            }
            add_gear(self, &mut out, gear);
        }
        for gear in self.controlled_attached_gear(side) {
            add_gear(self, &mut out, gear);
        }
        for card in self.gs.player(side).trash.clone() {
            if self.gs.is_spell(card) && self.flow_cost(card, side)?.is_some() {
                let timing = if self.gs.has_keyword(card, "REACTION") {
                    Some("reaction".to_string())
                } else if self.gs.has_keyword(card, "ACTION") {
                    Some("action".to_string())
                } else {
                    None
                };
                if allowed_in(window, &timing) {
                    out.push(AbilityEntry::Flow { card });
                }
            }
        }
        for card in self.gs.player(side).trash.clone() {
            for (cost, cond) in self.trash_plays(card) {
                if allowed_in(window, &self.card_timing(card).map(|s| s.to_string())) {
                    out.push(AbilityEntry::TrashPlay { card, cost: Some(cost), cond });
                }
            }
        }
        if self.side_has_passive(side, "play_from_trash") {
            not_ported!("activatable_abilities", "play_from_trash (Endless Riches)");
        }
        // banished_play: EK never makes a card playable from banishment.
        Ok(out)
    }

    /// py: _card_timing
    pub fn card_timing(&self, card: CardId) -> Option<&'static str> {
        if self.gs.has_keyword(card, "REACTION") || (self.gs.is_gear_card(card) && self.gs.has_keyword(card, "QUICK-DRAW")) {
            return Some("reaction");
        }
        if self.gs.has_keyword(card, "ACTION") { Some("action") } else { None }
    }

    /// py: _play_timing
    pub fn play_timing(&self, card: CardId, side: Side) -> Option<&'static str> {
        let timing = self.card_timing(card);
        if timing != Some("reaction") && self.has_reaction(card, side) {
            return Some("reaction");
        }
        if timing.is_none() && self.gs.is_gear_card(card) && self.gs.has_keyword(card, "DEPLOY")
            && self.side_has_passive(side, "deploy_gear_action")
        {
            return Some("action");
        }
        if timing.is_none() && self.quick_draw(card, side) {
            return Some("reaction");
        }
        timing
    }

    /// py: _has_reaction
    pub fn has_reaction(&self, card: CardId, side: Side) -> bool {
        if self.gs.has_keyword(card, "REACTION") {
            return true;
        }
        if !self.gs.is_spell(card) || !self.gs.showdown_active || self.gs.showdown_bf_idx.is_none() {
            return false;
        }
        self.gs.battlefields[self.gs.showdown_bf_idx.unwrap()]
            .units_for(side)
            .iter()
            .any(|&u| self.has_effect(self.gs.ucard(u), "spells_reaction_in_showdown"))
    }

    /// py: _quick_draw
    pub fn quick_draw(&self, card: CardId, side: Side) -> bool {
        self.gs.is_gear_card(card)
            && (self.gs.has_keyword(card, "QUICK-DRAW")
                || (self.equip_cost(card).is_some() && self.side_has_passive(side, "equipment_quick_draw")))
    }

    /// py: _trash_plays -> (cost, condition)
    pub fn trash_plays(&self, card: CardId) -> Vec<(Value, Option<Value>)> {
        self.gs
            .spec(card)
            .effects
            .iter()
            .filter(|es| es.trigger == "from_trash")
            .map(|es| (es.cost.clone().unwrap_or(Value::Object(Map::new())), es.condition.clone()))
            .collect()
    }

    /// py: _play_from_zone_now
    pub fn play_from_zone_now(&mut self, ap: Side, card: CardId, zone: &str) -> R<()> {
        if self.gs.is_unit_card(card) {
            self.play_unit(card, ap, None, zone)?;
        } else if self.gs.is_gear_card(card) {
            self.play_gear(card, ap, 0, zone)?;
        } else if self.gs.is_spell(card) {
            let lane = self.zone_play_lane();
            if !self.gs.chain.is_empty() {
                self.spell_played(card, ap, zone)?;
                self.put_on_chain(ChainItem { uid: 0, player: ap, card, bf_idx: lane, declared: None, choices_noted: false, owner: None, ability: None })?;
            } else {
                self.cast_spell_now(card, ap, lane, zone)?;
            }
        }
        Ok(())
    }

    /// py: _zone_play_lane
    pub fn zone_play_lane(&self) -> usize {
        if self.gs.showdown_active {
            if let Some(s) = self.gs.showdown_bf_idx {
                return s;
            }
        }
        0
    }

    /// py: _flow_cost -> (energy, power, domain)
    pub fn flow_cost(&mut self, card: CardId, side: Side) -> R<Option<(i64, i64, Option<Domain>)>> {
        let cost = self.gs.inst(card).flow_cost.clone();
        if !truthy(Some(&cost)) {
            return Ok(None);
        }
        let (aura, floor) = self.aura_reduction(card, side, true)?;
        let mut energy = cost.get("energy").map(py_int).unwrap_or(0);
        if aura != 0 {
            energy = energy.min(floor).max(energy - aura);
        }
        let domain = cost.get("domain").filter(|v| truthy(Some(v))).and_then(|v| Domain::from_py(&py_str(v)));
        Ok(Some((energy, cost.get("power").map(py_int).unwrap_or(0), domain)))
    }

    /// py: _can_pay_flow
    pub fn can_pay_flow(&mut self, card: CardId, side: Side) -> R<bool> {
        let Some((energy, power, domain)) = self.flow_cost(card, side)? else { return Ok(false) };
        if !self.gs.player(side).trash.contains(&card) || self.play_forbidden(side, card)? {
            return Ok(false);
        }
        if energy > 0 && self.songstress_offer(side, card)? {
            unreachable!();
        }
        let p = self.gs.player(side);
        if p.energy() < (energy - p.earmarked_energy_spell).max(0) {
            return Ok(false);
        }
        let power = (power - p.earmarked_power_spell).max(0);
        if power == 0 {
            return Ok(true);
        }
        Ok(match domain {
            Some(d) => p.can_pay_cost(0, Some(power), Some(d)),
            None => self.can_pay_generic_power(side, power),
        })
    }

    /// py: _play_with_flow
    pub fn play_with_flow(&mut self, card: CardId, side: Side) -> R<()> {
        if !self.can_pay_flow(card, side)? {
            return Ok(());
        }
        let (energy, mut power, domain) = self.flow_cost(card, side)?.unwrap();
        self.spell_energy_paid = Some(energy);
        {
            let p = self.gs.player_mut(side);
            let fe = energy.min(p.earmarked_energy_spell);
            p.earmarked_energy_spell -= fe;
            let e = p.energy() - (energy - fe);
            p.set_energy(e);
            let fe = power.min(p.earmarked_power_spell);
            p.earmarked_power_spell -= fe;
            power -= fe;
        }
        if power != 0 {
            match domain {
                Some(d) => {
                    self.gs.player_mut(side).pay_cost(0, Some(power), Some(d));
                }
                None => {
                    self.pay_generic_power(side, power)?;
                }
            }
        }
        self.drain_rune_recycles()?;
        self.gs.player_mut(side).trash.retain(|&c| c != card);
        self.gs.card_mut(card).flow_banish = Some(true);
        self.play_from_zone_now(side, card, "trash")
    }

    /// py: _spell_to_trash
    pub fn spell_to_trash(&mut self, owner: Side, card: CardId) -> R<()> {
        let legend = self.legend_with(owner, "jhin_pile", false);
        if self.gs.card(card).flow_banish.unwrap_or(false) {
            self.gs.card_mut(card).flow_banish = Some(false);
            self.gs.player_mut(owner).banished.push(card);
            self.note_banished(owner)?;
        } else if legend.is_some() && self.gs.card(card).spent.unwrap_or(0) >= 4 {
            not_ported!("_spell_to_trash", "Jhin Virtuoso");
        } else {
            self.put_in_trash(owner, card, false)?;
        }
        Ok(())
    }

    /// py: _ability_usable(ap, entry)
    pub fn ability_usable(&mut self, ap: Side, entry: &AbilityEntry) -> R<bool> {
        let side = ap;
        match entry {
            AbilityEntry::Equip { gear } => {
                let Some(mut cost) = self.equip_cost(*gear) else { return Ok(false) };
                cost.energy = (cost.energy - self.gear_ability_discount(side)).max(0);
                if !self.gs.player(ap).base_gear.contains(gear) {
                    return Ok(false);
                }
                return Ok(!self.equip_targets(ap, *gear, &cost)?.is_empty());
            }
            AbilityEntry::Flow { card } => {
                let lane = self.zone_play_lane();
                return Ok(self.can_pay_flow(*card, side)? && self.spell_has_targets(*card, side, lane)?);
            }
            AbilityEntry::TrashPlay { .. } => not_ported!("_ability_usable", "trash_play"),
            AbilityEntry::BanishedPlay { .. } => not_ported!("_ability_usable", "banished_play"),
            _ => {}
        }
        let eff = entry.eff().unwrap().clone();
        if !crate::effects::exists(&eff.effect) {
            return Ok(false);
        }
        if let AbilityEntry::BfAbility { .. } = entry {
            not_ported!("_ability_usable", "battlefield ability (Black Market)");
        }
        if truthy(eff.params.get("once_per_turn")) {
            let (src, copy) = match entry {
                AbilityEntry::GearAbility { gear, .. } => (*gear, 0),
                AbilityEntry::Ability { unit, copy, .. } => (self.gs.ucard(*unit), *copy),
                _ => unreachable!(),
            };
            if self.gs.once_per_turn_used.get(&Game::once_key(src, &eff, copy)) == Some(&self.gs.turn) {
                return Ok(false);
            }
        }
        let mut parsed = self.parse_activated_cost(eff.cost.as_ref())?;
        let (source, unit, bf_idx) = match entry {
            AbilityEntry::GearAbility { gear, .. } => {
                let gear = *gear;
                parsed.energy = (parsed.energy - self.gear_ability_discount(side)).max(0);
                if !self.controls_gear(ap, gear) {
                    return Ok(false);
                }
                if parsed.tap && self.gs.card(gear).tapped {
                    return Ok(false);
                }
                if parsed.disempower {
                    return Ok(false);
                }
                if !self.can_pay_gear(ap, parsed.energy, Some(parsed.power), parsed.domain) {
                    return Ok(false);
                }
                if parsed.recycle != 0 && (self.recyclable(ap, &parsed.recycle_type).len() as i64) < parsed.recycle {
                    return Ok(false);
                }
                if parsed.banish_from_trash.is_some() && self.trash_card_to_banish(ap, &parsed).is_none() {
                    return Ok(false);
                }
                if parsed.discard != 0 && (self.discardable(ap, &parsed).len() as i64) < parsed.discard {
                    return Ok(false);
                }
                if parsed.spend_buff.is_some() {
                    not_ported!("_ability_usable", "spend_buff on a gear ability");
                }
                if parsed.spend_xp != 0 && self.gs.get_xp(side) < parsed.spend_xp {
                    return Ok(false);
                }
                if parsed.kill_other_friendly || parsed.kill_friendly_gear || parsed.exhaust_friendly_unit.is_some() {
                    not_ported!("_ability_usable", "gear ability kill/exhaust cost");
                }
                (gear, None, None)
            }
            AbilityEntry::Ability { unit, bf_idx, .. } => {
                let parsed2 = self.adjust_ability_cost(Some(*unit), &eff, &parsed, side)?;
                let uc = self.unit_ability_cost(ap, *unit, &parsed2);
                if !self.activated_affordable(ap, Some(*unit), &uc)? {
                    return Ok(false);
                }
                (self.gs.ucard(*unit), Some(*unit), *bf_idx)
            }
            _ => unreachable!(),
        };
        let bf = bf_idx.unwrap_or(0);
        let ex = crate::lp_phases::bf_extra(bf);
        if !self.check_condition(eff.condition.as_ref(), source, ap, Some(&ex))? {
            return Ok(false);
        }
        self.ability_has_target(ap, source, unit, &eff, bf)
    }

    /// py: _ability_has_target
    pub fn ability_has_target(&mut self, ap: Side, source: CardId, unit: Option<UnitId>, eff: &Spec, bf: usize) -> R<bool> {
        let mut params: Map<String, Value> = eff.merged.clone();
        params.insert("effect".into(), Value::String(eff.effect.clone()));
        if eff.effect == "swap_position" {
            let named = params.get("with_name").filter(|v| truthy(Some(v))).map(py_str);
            let Some(where_) = unit.and_then(|u| self.locate_unit(u)) else { return Ok(false) };
            let ok = self.friendly_units_of(ap).into_iter().any(|u| {
                Some(u) != unit
                    && match &named {
                        Some(n) => self.gs.name(self.gs.ucard(u)) == n,
                        None => !self.gs.unit(u).is_token,
                    }
                    && self.locate_unit(u).map(|w| w.1) != Some(where_.1)
            });
            return Ok(ok);
        }
        let ctx = Ctx::new(source, ap, bf);
        let ok = self.has_valid_target(&ctx, &params)?;
        let target = params.get("target").map(py_str).unwrap_or_default().to_lowercase();
        if ok == Some(false) && !truthy(params.get("where")) && crate::effects::SINGLE_UNIT_TARGETS.contains(&target.as_str())
            && !matches!(params.get("effect").and_then(|v| v.as_str()), Some("move_unit") | Some("move_units_to_base"))
        {
            let mut units = self.fallback_units(&ctx, &target, "none")?;
            if let Some(tf) = params.get("target_filter").filter(|v| truthy(Some(v))).cloned() {
                let mut kept = Vec::new();
                for u in units {
                    if self.passes_filter(u, &tf, &ctx)? {
                        kept.push(u);
                    }
                }
                units = kept;
            }
            return Ok(!self.choosable(&ctx, &units)?.is_empty());
        }
        Ok(ok != Some(false))
    }

    /// py: _gear_left_board
    pub fn gear_left_board(&mut self, card: CardId, side: Side) -> R<()> {
        self.gs.friendly_gear_died_this_turn[side.idx()] = true;
        self.resolve_triggered_effects(card, "on_death", 0, side, Some(crate::lp_phases::bf_extra(0)))?;
        self.fire_leaves_board(card, side, 0)
    }

    /// py: _remove_gear(gear, ap, banish=False)
    pub fn remove_gear(&mut self, gear: CardId, ap: Side) -> R<()> {
        if self.gs.player(ap).base_gear.contains(&gear) {
            self.gs.player_mut(ap).base_gear.retain(|&g| g != gear);
        } else {
            let mut us: Vec<UnitId> = Vec::new();
            for b in &self.gs.battlefields {
                us.extend(b.units_for(ap).iter().copied());
            }
            us.extend(self.gs.player(ap).base_units.iter().copied());
            for u in us {
                if self.gs.unit(u).gear.contains(&gear) {
                    self.gs.unit_mut(u).gear.retain(|&g| g != gear);
                    break;
                }
            }
        }
        self.to_trash(ap, gear)?;
        self.gear_left_board(gear, ap)
    }

    /// py: _controlled_attached_gear
    pub fn controlled_attached_gear(&self, side: Side) -> Vec<CardId> {
        let mut out: Vec<CardId> = Vec::new();
        for &u in &self.gs.player(side).base_units {
            out.extend(self.gs.unit(u).gear.iter().copied());
        }
        for bf in &self.gs.battlefields {
            for &u in bf.units_for(side) {
                out.extend(self.gs.unit(u).gear.iter().copied());
            }
        }
        out
    }

    /// py: _controls_gear
    pub fn controls_gear(&self, ap: Side, gear: CardId) -> bool {
        self.gs.player(ap).base_gear.contains(&gear) || self.controlled_attached_gear(ap).contains(&gear)
    }

    /// py: _friendly_units_of
    pub fn friendly_units_of(&self, side: Side) -> Vec<UnitId> {
        let mut out: Vec<UnitId> = Vec::new();
        for bf in &self.gs.battlefields {
            out.extend(bf.units_for(side).iter().copied());
        }
        out.extend(self.gs.player(side).base_units.iter().copied());
        out
    }

    /// py: _discardable
    pub fn discardable(&self, ap: Side, parsed: &ParsedCost) -> Vec<CardId> {
        let hand = &self.gs.player(ap).hand;
        match parsed.discard_type.as_deref() {
            Some("gear") => hand.iter().copied().filter(|&c| self.gs.is_gear(c)).collect(),
            Some("spell") => hand.iter().copied().filter(|&c| self.gs.is_spell(c)).collect(),
            _ => hand.clone(),
        }
    }

    /// py: _trash_banish_options
    pub fn trash_banish_options(&self, ap: Side, parsed: &ParsedCost) -> Vec<CardId> {
        let Some(kind) = parsed.banish_from_trash.as_ref().filter(|v| truthy(Some(v))) else { return Vec::new() };
        let mut spec = Map::new();
        if kind.is_string() {
            spec.insert("filter".into(), kind.clone());
        } else {
            spec.insert("target_filter".into(), kind.clone());
        }
        let mut trash: Vec<CardId> = self.gs.player(ap).trash.clone();
        if parsed.banish_any_trash {
            let mut t = self.gs.player(ap.other()).trash.clone();
            t.extend(trash);
            trash = t;
        }
        trash.into_iter().filter(|&c| self.zone_effect_card_ok(c, &spec)).collect()
    }

    /// py: _trash_card_to_banish
    pub fn trash_card_to_banish(&self, ap: Side, parsed: &ParsedCost) -> Option<CardId> {
        let cands = self.trash_banish_options(ap, parsed);
        if cands.is_empty() {
            return None;
        }
        let theirs: Vec<CardId> = cands.iter().copied().filter(|c| !self.gs.player(ap).trash.contains(c)).collect();
        let pool = if theirs.is_empty() { cands } else { theirs };
        let mut best = pool[0];
        for &c in &pool[1..] {
            if self.gs.cost_energy(c) < self.gs.cost_energy(best) {
                best = c;
            }
        }
        Some(best)
    }

    /// py: _pay_discard_and_banish(ap, parsed, unit=None)
    pub fn pay_discard_and_banish(&mut self, ap: Side, parsed: &ParsedCost, unit: Option<UnitId>) -> R<()> {
        if parsed.banish_from_trash.as_ref().map_or(false, |v| truthy(Some(v))) {
            let mut card = self.trash_card_to_banish(ap, parsed);
            if let Some(c) = card {
                let opts: Vec<Opt> = self.trash_banish_options(ap, parsed).into_iter().map(Opt::Card).collect();
                match self.choose("cost_banish", ap, &opts, Opt::Card(c), None)? {
                    Opt::Card(x) => card = Some(x),
                    _ => unreachable!(),
                }
            }
            let owner = match card {
                None => ap,
                Some(c) if self.gs.player(ap).trash.contains(&c) => ap,
                _ => ap.other(),
            };
            self.banish_from_trash(owner, card)?;
        }
        if parsed.discard != 0 {
            not_ported!("_pay_discard_and_banish", "discard cost");
        }
        if let Some(sb) = parsed.spend_buff.clone().filter(|s| !s.is_empty()) {
            if let Some(holder) = self.buff_to_spend(ap, unit, &sb)? {
                self.spend_buff(holder, Some(ap))?;
            }
        }
        if parsed.kill_other_token || parsed.kill_other_friendly {
            not_ported!("_pay_discard_and_banish", "kill cost");
        }
        Ok(())
    }
}
