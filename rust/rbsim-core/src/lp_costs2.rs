//! py: loop.py — additional costs (kicker), the action fingerprint, a
//! card's effective cost and every modifier it reads.

use regex::Regex;
use serde_json::{Map, Value};
use std::sync::OnceLock;

use crate::cards::{py_int, truthy};
use crate::game::*;
use crate::lp_phases::py_str;
use crate::lp_triggers::Ctx;
use crate::model::*;
use crate::not_ported;
use crate::types::*;
use crate::lp_abilities::ParsedCost;

/// py: _action_fingerprint's tuple, as a comparable value.
#[derive(Clone, Debug, PartialEq)]
pub struct Fingerprint(pub Vec<i64>, pub Vec<String>);

impl Game {
    /// py: _cost_objects — EK: no additional cost takes objects.
    pub fn cost_objects_any(&self, ac: &Value) -> bool {
        ["kill_friendly_unit", "kill_friendly_gear", "exhaust_friendly_unit", "exhaust_legend", "return_friendly_unit"]
            .iter()
            .any(|k| truthy(ac.get(*k)))
    }

    /// py: _additional_cost_optional
    pub fn additional_cost_optional(&self, card: CardId) -> bool {
        static SPLIT: OnceLock<Regex> = OnceLock::new();
        let text = self.gs.spec(card).raw.get("effect").and_then(|v| v.as_str()).unwrap_or("");
        // re.split(r"(?<=[.)])\s+", text): split after '.' or ')' on whitespace runs
        let _ = SPLIT.get_or_init(|| Regex::new(r"\s+").unwrap());
        let mut sentences: Vec<String> = Vec::new();
        let mut cur = String::new();
        let chars: Vec<char> = text.chars().collect();
        let mut i = 0;
        while i < chars.len() {
            let c = chars[i];
            if c.is_whitespace() && i > 0 && (chars[i - 1] == '.' || chars[i - 1] == ')') {
                sentences.push(std::mem::take(&mut cur));
                while i < chars.len() && chars[i].is_whitespace() {
                    i += 1;
                }
                continue;
            }
            cur.push(c);
            i += 1;
        }
        sentences.push(cur);
        let s: Vec<&String> = sentences.iter().filter(|s| s.to_lowercase().contains("additional cost")).collect();
        s.is_empty() || s.iter().any(|x| x.to_lowercase().contains("you may"))
    }

    /// py: _try_pay_additional_costs(card, ap, bf=None)
    pub fn try_pay_additional_costs(&mut self, card: CardId, ap: Side, bf: Option<usize>) -> R<bool> {
        let specs = self.gs.spec(card).effects.clone();
        if specs.is_empty() {
            return Ok(false);
        }
        let mut seen: Vec<Value> = Vec::new();
        let mut paid = false;
        for es in specs {
            let Some(ac) = es.additional_cost.clone().filter(|v| truthy(Some(v))) else { continue };
            if seen.contains(&ac) {
                continue;
            }
            if truthy(es.params.get("additional_cost_if")) {
                let c = es.params["additional_cost_if"].clone();
                if !self.check_condition(Some(&c), card, ap, Some(&Extra::default()))? {
                    continue;
                }
            }
            seen.push(ac.clone());
            if self.additional_cost_optional(card) && self.pay_one_additional_cost_x(card, ap, &ac, true)? {
                let worth = self.kicker_worth(card, ap, bf)?;
                let got = self.choose("optional:additional_cost", ap, &[Opt::Bool(true), Opt::Bool(false)], Opt::Bool(worth), Some(card))?;
                if got != Opt::Bool(true) {
                    continue;
                }
            }
            if self.pay_one_additional_cost(card, ap, &ac)? {
                self.gs.card_mut(card).set_kicker(Some(true));
                paid = true;
            }
        }
        Ok(paid)
    }

    /// py: _kicker_worth
    pub fn kicker_worth(&mut self, card: CardId, ap: Side, bf: Option<usize>) -> R<bool> {
        let ctx = Ctx::new(card, ap, bf.unwrap_or(0));
        let specs = self.gs.spec(card).effects.clone();
        let mut checks: Vec<Option<bool>> = Vec::new();
        for es in specs {
            if es.condition.as_ref().and_then(|c| c.get("type")).and_then(|t| t.as_str()) == Some("kicker_paid") {
                let mut p = es.merged.clone();
                p.insert("effect".into(), Value::String(es.effect.clone()));
                checks.push(self.has_valid_target(&ctx, &p)?);
            }
        }
        Ok(checks.is_empty() || checks.iter().any(|c| *c != Some(false)))
    }

    pub fn pay_one_additional_cost(&mut self, card: CardId, ap: Side, ac: &Value) -> R<bool> {
        self.pay_one_additional_cost_x(card, ap, ac, false)
    }

    /// py: _pay_one_additional_cost(card, ap, ac, check_only)
    pub fn pay_one_additional_cost_x(&mut self, card: CardId, ap: Side, ac: &Value, check_only: bool) -> R<bool> {
        let mut energy = ac.get("energy").map(py_int).unwrap_or(0);
        let mut power = ac.get("power").map(py_int).unwrap_or(0);
        let domain = ac.get("domain").filter(|v| truthy(Some(v))).and_then(|v| Domain::from_py(&py_str(v)));
        let discard_n = ac.get("discard_cards").map(py_int).unwrap_or(0);
        if self.additional_cost_optional(card) && self.side_has_passive(ap, "cheaper_optional_costs") {
            if energy != 0 {
                energy -= 1;
            } else if power != 0 {
                power -= 1;
            }
        }
        let xp = ac.get("spend_xp").map(py_int).unwrap_or(0);
        // D83: a cost inside an effect also counts the ready Golds (rules 204.3.a, 430.3, 445.2.c).
        let mut golds_needed = 0;
        if !self.can_pay_energy_and_generic(ap, energy, power, domain) {
            if !self.gs.reg.regole.d83() || power <= 0 || self.gs.player(ap).energy() < energy {
                return Ok(false);
            }
            match self.golds_needed(ap, power, domain)? {
                Some(n) => golds_needed = n,
                None => return Ok(false),
            }
        }
        if xp != 0 && self.gs.get_xp(ap) < xp {
            return Ok(false);
        }
        let in_hand = self.gs.player(ap).hand.contains(&card);
        if discard_n != 0 && (self.gs.player(ap).hand.len() as i64) < discard_n + in_hand as i64 {
            return Ok(false);
        }
        if self.cost_objects_any(ac) {
            not_ported!("_pay_one_additional_cost", "an additional cost taking a unit or gear");
        }
        if check_only {
            return Ok(true);
        }
        if golds_needed == 0 && self.gs.reg.regole.d83() && power > 0 && self.has_agent(ap) {
            // D83: the runes pay, and a ready Gold could pay instead: the seat that asks how to
            // pay (the page's "Come paghi?") is asked; the others get the runes (the default).
            let k = self.gold_lanes(ap)?.len() as i64;
            if k > 0 {
                let k = k.min(power);
                let opts = [Opt::Str("rune".into()), Opt::Str(format!("gold:{k}"))];
                if self.choose("payment:effect", ap, &opts, opts[0].clone(), Some(card))? == opts[1] {
                    golds_needed = k;
                }
            }
        }
        if golds_needed > 0 {
            crate::registry::conta(83);
            self.use_golds(ap, golds_needed, domain)?;
        }
        if !self.pay_energy_and_generic(ap, energy, power, domain)? {
            return Ok(false);
        }
        if xp != 0 {
            self.gs.add_xp(ap, -xp);
        }
        for _ in 0..discard_n {
            let hand: Vec<CardId> = self.gs.player(ap).hand.iter().copied().filter(|&c| c != card).collect();
            if hand.is_empty() {
                return Ok(false);
            }
            let c = self.discard_choice(ap, &hand, Some(card))?;
            self.discard(ap, c)?;
        }
        Ok(true)
    }

    /// D83: the lanes (in `activatable_abilities`) of `ap`'s ready Golds (ADD a Power of any domain).
    pub fn gold_lanes(&mut self, ap: Side) -> R<Vec<i64>> {
        let entries = self.activatable_abilities(ap)?;
        let mut out = Vec::new();
        for (i, e) in entries.iter().enumerate() {
            if matches!(e, crate::lp_abilities::AbilityEntry::GearAbility { eff, .. } if eff.effect == "gain_power_any_domain")
                && self.ability_usable(ap, e)?
            {
                out.push(i as i64);
            }
        }
        Ok(out)
    }

    /// D83: the fewest ready Golds that, with the runes, pay `power` Power of `domain` (any domain
    /// if None); Some(0) if the runes already do, None if even all the Golds do not.
    pub fn golds_needed(&mut self, ap: Side, power: i64, domain: Option<Domain>) -> R<Option<i64>> {
        let n = self.gold_lanes(ap)?.len() as i64;
        for k in 0..=n {
            let rest = power - k;
            let ok = match domain {
                _ if rest <= 0 => true,
                Some(d) => self.gs.player(ap).can_pay_cost(0, Some(rest), Some(d)),
                None => self.can_pay_generic_power(ap, rest),
            };
            if ok {
                return Ok(Some(k));
            }
        }
        Ok(None)
    }

    /// D83: activate `n` Golds (kill + tap, ADD of `domain`, or the engine's choice if None).
    pub fn use_golds(&mut self, ap: Side, n: i64, domain: Option<Domain>) -> R<()> {
        for _ in 0..n {
            let Some(&l) = self.gold_lanes(ap)?.first() else { break };
            self.gold_domain = domain;
            let r = self.apply_activated_ability(ap, l);
            self.gold_domain = None;
            r?;
        }
        Ok(())
    }

    /// py: _action_fingerprint(ap, op)
    pub fn action_fingerprint(&self, ap: Side, op: Side) -> Fingerprint {
        let gs = &self.gs;
        let mut nums: Vec<i64> = Vec::new();
        let mut strs: Vec<String> = Vec::new();
        for s in [ap, op] {
            let p = gs.player(s);
            nums.extend([p.hand.len() as i64, p.deck.cards.len() as i64, p.trash.len() as i64, p.banished.len() as i64,
                         p.base_units.len() as i64, p.base_gear.len() as i64, p.energy()]);
            let mut pp: Vec<(String, i64)> = p.power_pool.iter().map(|(d, n)| (d.name().to_string(), *n)).collect();
            pp.sort();
            strs.push(format!("{pp:?}"));
            nums.push(p.total_runes_in_play());
            let mut ready: Vec<String> =
                p.base_units.iter().filter(|&&u| gs.unit(u).ready).map(|&u| gs.name(gs.ucard(u)).to_string()).collect();
            ready.sort();
            strs.push(ready.join("|"));
            nums.push(p.base_units.iter().map(|&u| gs.unit_might(u)).sum());
            nums.push(p.base_gear.iter().filter(|&&g| gs.card(g).tapped).count() as i64);
            strs.push(format!("{:?}", self.legend_units(s).iter().map(|&l| gs.unit(l).ready).collect::<Vec<_>>()));
            nums.extend([p.earmarked_energy_showdown, p.earmarked_power_gear]);
        }
        for bf in &gs.battlefields {
            nums.extend([bf.units[0].len() as i64, bf.units[1].len() as i64,
                         bf.units[0].iter().map(|&u| gs.unit_might(u)).sum(),
                         bf.units[1].iter().map(|&u| gs.unit_might(u)).sum(),
                         bf.units[0].iter().chain(bf.units[1].iter()).filter(|&&u| gs.unit(u).ready).count() as i64]);
        }
        nums.extend([gs.points[0], gs.points[1], gs.chain.len() as i64, gs.xp[0], gs.xp[1]]);
        Fingerprint(nums, strs)
    }

    /// py: _effective_cost(card, actor, lane=None, from_zone="hand") -> (energy, power)
    pub fn effective_cost(&mut self, card: CardId, side: Side, lane: Option<i64>) -> R<(i64, Option<i64>)> {
        self.effective_cost_z(card, side, lane, "hand")
    }

    pub fn effective_cost_z(&mut self, card: CardId, side: Side, lane: Option<i64>, from_zone: &str)
                            -> R<(i64, Option<i64>)> {
        let printed = self.gs.cost_energy(card);
        let mut energy = printed - self.cost_reduction(card, side, false)?;
        let mut power = self.gs.cost_power(card);
        if from_zone != "hand" && self.has_effect(card, "reduce_cost_not_from_hand") {
            energy -= 2;
        }
        let extras = self.cost_extras(card, side)?;
        energy -= extras.get("energy").map(py_int).unwrap_or(0);
        if let Some(p) = power.filter(|&p| p != 0) {
            power = Some((p - extras.get("power").map(py_int).unwrap_or(0)).max(0));
        }
        if self.gs.is_gear(card) && self.orianna_discount_ready(side) {
            energy -= 1;
            if let Some(p) = power.filter(|&p| p != 0) {
                power = Some((p - 1).max(0));
            }
        }
        if self.gs.is_spell(card) {
            energy += self.vex_cheerless_delta(side, energy);
        }
        if self.gs.is_spell(card) {
            if let Some(l) = lane {
                let (e_red, p_red) = self.bf_cost_reduction(card, l);
                energy -= e_red;
                if power.is_some() && p_red != 0 {
                    power = Some((power.unwrap() - p_red).max(0));
                }
            }
        }
        let (aura, floor) = self.aura_reduction(card, side, false)?;
        if aura != 0 {
            energy = energy.min(floor).max(energy - aura);
        }
        if self.gs.is_spell(card) {
            energy += self.enemy_spell_tax(side);
        }
        energy += self.turn_cost_change(card, side);
        if self.gs.has_keyword(card, "REACTION") && self.gs.showdown_active {
            if let Some(sb) = self.gs.showdown_bf_idx {
                if let Some(sc) = self.gs.battlefields[sb].card {
                    if self.has_effect(sc, "reaction_tax_in_showdown") {
                        energy += 1;
                    }
                }
            }
        }
        if let Some(p) = power.filter(|&p| p != 0) {
            power = Some((p - self.aura_power_reduction(card, side)? - self.cost_reduction(card, side, true)?).max(0));
        }
        if let Some(d) = self.next_card_discount(card, side) {
            energy -= d.get("energy").map(py_int).unwrap_or(0);
            if let Some(p) = power.filter(|&p| p != 0) {
                power = Some((p - d.get("power").map(py_int).unwrap_or(0)).max(0));
            }
        }
        Ok((energy.max(0), power))
    }

    /// py: _cost_extras(card, side) — what a card lets you spend as you play it
    /// to cost less: "spend a buff and ignore this spell's cost" (Call to Glory).
    /// The other kinds are not ported.
    pub fn cost_extras(&mut self, card: CardId, side: Side) -> R<Map<String, Value>> {
        let mut out: Map<String, Value> = Map::new();
        let specs = self.gs.spec(card).effects.clone();
        for es in specs.iter() {
            if matches!(es.effect.as_str(), "spend_buffs_for_power" | "kill_units_for_power" | "spend_xp_for_energy"
                | "discard_for_energy" | "return_gear_for_energy")
            {
                not_ported!("_cost_extras", "{}", es.effect);
            }
            if es.effect == "spend_buff_free"
                && self.friendly_units_of(side).iter().any(|&u| self.gs.unit(u).might_counters > 0)
            {
                out.insert("energy".into(), Value::from(self.gs.cost_energy(card)));
                out.insert("power".into(), Value::from(self.gs.cost_power(card).unwrap_or(0)));
                out.insert("buffs".into(), Value::from(1));
            }
            if truthy(es.params.get("less_if_chosen")) {
                not_ported!("_cost_extras", "less_if_chosen");
            }
        }
        Ok(out)
    }

    /// py: _choose_cost_extras(card, ap, extras, energy, power) — how much of
    /// `extras` the player spends (baseline: all of it). Each buff not spent is
    /// one Power back on the cost; only affordable amounts are offered.
    pub fn choose_cost_extras(&mut self, card: CardId, ap: Side, extras: Map<String, Value>, energy: i64,
                              power: Option<i64>) -> R<(Map<String, Value>, i64, Option<i64>)> {
        if extras.is_empty() || (self.chooser.is_none() && !extras.contains_key("kills")) {
            return Ok((extras, energy, power));
        }
        let mut options: Vec<(Map<String, Value>, i64, Option<i64>)> = vec![(extras.clone(), energy, power)];
        let key = if extras.contains_key("buffs") {
            Some("buffs")
        } else if extras.contains_key("kills") {
            Some("kills")
        } else {
            None
        };
        if let Some(key) = key {
            let n = extras.get(key).map(py_int).unwrap_or(0);
            for k in (0..n).rev() {
                let back = n - k;
                let less: Map<String, Value> = if k != 0 {
                    let mut m = extras.clone();
                    m.insert(key.into(), Value::from(k));
                    m.insert("power".into(), Value::from(k));
                    m
                } else {
                    extras.iter().filter(|(x, _)| x.as_str() != key && x.as_str() != "power").map(|(x, v)| (x.clone(), v.clone())).collect()
                };
                if k == 0 && key == "buffs" && extras.contains_key("energy") && self.gs.reg.regole.d81() {
                    // D81: "spend a buff; if you do, ignore this spell's cost" (spend_buff_free): without
                    // the buff the cost comes back whole (it is not spend_buffs_for_power's 1 Power per buff).
                    let less: Map<String, Value> = less
                        .into_iter()
                        .filter(|(x, _)| x.as_str() != "energy")
                        .collect();
                    let x_power = extras.get("power").map(py_int).unwrap_or(0);
                    let p2 = if x_power != 0 { Some(power.unwrap_or(0) + x_power) } else { power };
                    crate::registry::conta(81);
                    options.push((less, energy + extras.get("energy").map(py_int).unwrap_or(0), p2));
                    continue;
                }
                options.push((less, energy, Some(power.unwrap_or(0) + back)));
            }
        }
        if ["xp", "discards", "gear_returns", "picks"].iter().any(|k| extras.contains_key(*k)) {
            not_ported!("_choose_cost_extras", "xp / discards / gear_returns / picks");
        }
        let mut kept = vec![options[0].clone()];
        for o in options.into_iter().skip(1) {
            if self.can_pay_card(ap, card, o.1, o.2, true, None, None)? {
                kept.push(o);
            }
        }
        if key == Some("kills") {
            not_ported!("_choose_cost_extras", "kills (Commander Ledros)");
        }
        let opt_of = |o: &(Map<String, Value>, i64, Option<i64>)| {
            Opt::Tuple(vec![Opt::Json(Value::Object(o.0.clone())), Opt::Int(o.1), o.2.map(Opt::Int).unwrap_or(Opt::None)])
        };
        let opts: Vec<Opt> = kept.iter().map(opt_of).collect();
        let got = self.choose("cost_extras", ap, &opts, opts[0].clone(), Some(card))?;
        let i = opts.iter().position(|o| *o == got).expect("cost_extras chose an option");
        Ok(kept.swap_remove(i))
    }

    /// py: _spend_cost_extras(extras, side, card) — pay what _cost_extras said the play spends.
    pub fn spend_cost_extras(&mut self, extras: &Map<String, Value>, side: Side, _card: CardId) -> R<()> {
        for _ in 0..extras.get("buffs").map(py_int).unwrap_or(0) {
            if let Some(holder) = self.buff_to_spend(side, None, "any")? {
                self.spend_buff(holder, Some(side))?;
            }
        }
        if ["kills", "xp", "discards", "gear_returns", "picks"].iter().any(|k| extras.get(*k).map_or(false, |v| truthy(Some(v)))) {
            not_ported!("_spend_cost_extras", "kills / xp / discards / gear_returns / picks");
        }
        Ok(())
    }

    /// py: _adjust_ability_cost
    pub fn adjust_ability_cost(&self, unit: Option<UnitId>, eff: &crate::registry::Spec, parsed: &ParsedCost, side: Side)
                               -> R<ParsedCost> {
        let mut parsed = parsed.clone();
        if truthy(eff.params.get("less_per_temporary")) || truthy(eff.params.get("less_per_rune"))
            || truthy(eff.params.get("less_if_runes_at_most"))
        {
            not_ported!("_adjust_ability_cost", "ability cost reductions");
        }
        if eff.effect != "empower_self" || unit.is_none() {
            return Ok(parsed);
        }
        let _ = (&mut parsed, side);
        not_ported!("_adjust_ability_cost", "empower_self discount")
    }

    /// py: _orianna_discount_ready
    pub fn orianna_discount_ready(&self, side: Side) -> bool {
        self.units_at_battlefields_with(side, "gear_discount_once").iter().any(|&u| {
            self.gs.once_per_turn_used.get(&OnceK::Card(self.gs.ucard(u), OnceKey::Str("orianna".into())))
                != Some(&self.gs.turn)
        })
    }

    /// py: _use_gear_discount
    pub fn use_gear_discount(&mut self, side: Side) {
        for u in self.units_at_battlefields_with(side, "gear_discount_once") {
            let key = OnceK::Card(self.gs.ucard(u), OnceKey::Str("orianna".into()));
            if self.gs.once_per_turn_used.get(&key) != Some(&self.gs.turn) {
                let t = self.gs.turn;
                self.gs.once_per_turn_used.set(key, t);
                break;
            }
        }
    }

    /// py: _vex_cheerless_delta
    pub fn vex_cheerless_delta(&self, side: Side, energy: i64) -> i64 {
        let gs = &self.gs;
        if !gs.showdown_active || gs.showdown_bf_idx.is_none() {
            return 0;
        }
        let bf = &gs.battlefields[gs.showdown_bf_idx.unwrap()];
        let mut delta = 0;
        for s in Side::BOTH {
            if bf.units_for(s).iter().any(|&u| self.has_effect(gs.ucard(u), "vex_cheerless")) {
                delta += if s == side { -(2.min((energy - 1).max(0))) } else { 2 };
            }
        }
        delta
    }

    /// py: _destination_surcharge
    pub fn destination_surcharge(&mut self, card: CardId, dst: Option<i64>, side: Side) -> i64 {
        let Some(dst) = dst else { return 0 };
        let bf = dst as usize;
        if let Some(c) = self.gs.battlefields[bf].card {
            if self.has_effect(c, "dragon_roost") && self.gs.tags(card).iter().any(|t| t == "Dragon")
                && self.gs.battlefields[bf].control() != Some(side)
            {
                return 2;
            }
        }
        0
    }

    /// py: _turn_cost_change
    pub fn turn_cost_change(&self, _card: CardId, side: Side) -> i64 {
        let _ = side;
        // EK: nothing makes turn_cost_changes (Vaults of Helia).
        0
    }

    /// py: _destination_discount
    pub fn destination_discount(&self, card: CardId, dst: Option<i64>, side: Side) -> R<i64> {
        let Some(dst) = dst else { return Ok(0) };
        let bf = &self.gs.battlefields[dst as usize];
        let Some(bc) = bf.card else { return Ok(0) };
        if !self.has_effect(bc, "first_play_here_discount") || self.gs.active != side
            || !(self.gs.is_unit_card(card) || self.gs.is_gear_card(card))
        {
            return Ok(0);
        }
        let (turn, n) = bf.plays_here.get(&side).copied().unwrap_or((-1, 0));
        Ok(if turn == self.gs.turn && n != 0 { 0 } else { 1 })
    }

    /// py: _note_play_here
    pub fn note_play_here(&mut self, bf: usize, side: Side, _card: CardId) {
        let t = self.gs.turn;
        let b = &mut self.gs.battlefields[bf];
        let (turn, n) = b.plays_here.get(&side).copied().unwrap_or((-1, 0));
        b.plays_here.set(side, (t, (if turn == t { n } else { 0 }) + 1));
    }

    /// py: _battlefield_sources
    pub fn battlefield_sources(&self) -> Vec<(CardId, usize)> {
        self.gs.battlefields.iter().enumerate().filter_map(|(i, b)| b.card.map(|c| (c, i))).collect()
    }

    /// py: _controls_bf_with
    pub fn controls_bf_with(&mut self, side: Side, verb: &str) -> bool {
        for i in 0..self.gs.battlefields.len() {
            if let Some(c) = self.gs.battlefields[i].card {
                if self.gs.battlefields[i].control() == Some(side) && self.has_effect(c, verb) {
                    return true;
                }
            }
        }
        false
    }

    /// py: _gear_ability_discount
    pub fn gear_ability_discount(&mut self, side: Side) -> i64 {
        if self.gs.once_per_turn_used.get(&OnceK::Named("gear_ability".into(), side)) == Some(&self.gs.turn) {
            return 0;
        }
        if self.controls_bf_with(side, "first_gear_ability_discount") { 1 } else { 0 }
    }

    /// py: _note_gear_ability
    pub fn note_gear_ability(&mut self, side: Side) {
        let t = self.gs.turn;
        self.gs.once_per_turn_used.set(OnceK::Named("gear_ability".into(), side), t);
    }

    /// py: _enemy_spell_tax
    pub fn enemy_spell_tax(&self, side: Side) -> i64 {
        let mut total = 0;
        for (src, _) in self.sources_in_play(side.other()) {
            for es in self.card_effects_auto(src) {
                if es.effect == "enemy_spell_tax" {
                    total += es.params.get("amount").map(py_int).unwrap_or(1);
                    if self.is_empowered(src) {
                        total += es.params.get("empowered_extra").map(py_int).unwrap_or(0);
                    }
                }
            }
        }
        total
    }

    /// py: _aura_reduction(card, actor, flow=False) -> (total, floor)
    pub fn aura_reduction(&mut self, card: CardId, side: Side, flow: bool) -> R<(i64, i64)> {
        let (mut total, mut floor) = (0, 0);
        let mut sources = self.sources_in_play(side);
        sources.extend(self.battlefield_sources());
        for (src, bf) in sources {
            if src == card {
                continue;
            }
            for es in self.card_effects_auto(src) {
                if es.trigger != "cost_aura" || es.effect != "reduce_cost" {
                    continue;
                }
                if truthy(es.params.get("flow_only")) && !flow {
                    continue;
                }
                let f = es.params.get("filter").cloned().filter(|v| truthy(Some(v))).unwrap_or(Value::Object(Map::new()));
                if !self.zone_effect_card_ok_tf(card, &f) {
                    continue;
                }
                let mut ex = crate::lp_phases::bf_extra(bf);
                ex.set("triggering_card", XVal::Card(card));
                if !self.check_condition(es.condition.as_ref(), src, side, Some(&ex))? {
                    continue;
                }
                total += es.params.get("amount").map(py_int).unwrap_or(1);
                floor = floor.max(es.params.get("min_cost").map(py_int).unwrap_or(0));
            }
        }
        Ok((total, floor))
    }

    /// py: _aura_power_reduction
    pub fn aura_power_reduction(&mut self, card: CardId, side: Side) -> R<i64> {
        let mut total = 0;
        let mut sources = self.sources_in_play(side);
        sources.extend(self.battlefield_sources());
        for (src, bf) in sources {
            if src == card {
                continue;
            }
            for es in self.card_effects_auto(src) {
                if es.trigger == "cost_aura" && es.effect == "reduce_cost" && truthy(es.params.get("power")) {
                    let f = es.params.get("filter").cloned().filter(|v| truthy(Some(v))).unwrap_or(Value::Object(Map::new()));
                    if !self.zone_effect_card_ok_tf(card, &f) {
                        continue;
                    }
                    let mut ex = crate::lp_phases::bf_extra(bf);
                    ex.set("triggering_card", XVal::Card(card));
                    if self.check_condition(es.condition.as_ref(), src, side, Some(&ex))? {
                        total += py_int(&es.params["power"]);
                    }
                }
            }
        }
        Ok(total)
    }

    /// py: _sources_in_play -> (card, battlefield) (base: battlefields[0])
    pub fn sources_in_play(&self, side: Side) -> Vec<(CardId, usize)> {
        let gs = &self.gs;
        let mut out = Vec::new();
        for (i, bf) in gs.battlefields.iter().enumerate() {
            for &u in bf.units_for(side) {
                out.push((gs.ucard(u), i));
                out.extend(gs.unit(u).gear.iter().map(|&g| (g, i)));
            }
            out.extend(bf.gear[side.idx()].iter().map(|&dg| (gs.dgear[dg.i()].card, i)));
        }
        for &u in &gs.player(side).base_units {
            out.push((gs.ucard(u), 0));
            out.extend(gs.unit(u).gear.iter().map(|&g| (g, 0)));
        }
        out.extend(gs.player(side).base_gear.iter().map(|&g| (g, 0)));
        out.extend(self.legend_units(side).iter().map(|&l| (gs.ucard(l), 0)));
        out
    }

    /// py: _next_card_discount
    pub fn next_card_discount(&self, card: CardId, side: Side) -> Option<Value> {
        for d in &self.gs.next_card_discounts[side.idx()] {
            let f = d.get("filter").cloned().filter(|v| truthy(Some(v))).unwrap_or(Value::Object(Map::new()));
            if self.zone_effect_card_ok_tf(card, &f) {
                return Some(d.clone());
            }
        }
        None
    }

    /// py: _power_domains
    pub fn power_domains(&self, card: CardId) -> Vec<Domain> {
        let raw = self.gs.spec(card).raw.get("cost_power_domain").map(|v| if v.is_null() { String::new() } else { py_str(v) }).unwrap_or_default();
        let out: Vec<Domain> = raw.split('/').filter_map(|p| Domain::from_py(p.trim())).collect();
        if out.is_empty() { Domain::ALL.to_vec() } else { out }
    }

    /// py: _songstress (Seraphine): None unless her legend is ready.
    pub fn songstress_offer(&self, side: Side, card: CardId) -> R<bool> {
        if !self.gs.is_spell(card) {
            return Ok(false);
        }
        if self.legend_with(side, "songstress_discount", true).is_none() {
            return Ok(false);
        }
        not_ported!("_songstress", "Seraphine Starry-Eyed Songstress")
    }

    /// py: _alt_cost — EK: no card has play_me_for.
    pub fn alt_cost_offered(&self, card: CardId) -> R<bool> {
        if self.gs.spec(card).effects.iter().any(|e| e.effect == "play_me_for") {
            not_ported!("_alt_cost", "play_me_for");
        }
        Ok(false)
    }

    /// py: _kill_discounts — EK: no card has kill_unit_for_discount.
    pub fn kill_discount_offered(&self, card: CardId) -> R<bool> {
        if self.gs.is_unit_card(card) && self.has_effect(card, "kill_unit_for_discount") {
            not_ported!("_kill_discounts", "Atakhan");
        }
        Ok(false)
    }

    /// py: _is_empowered
    pub fn is_empowered(&self, card: CardId) -> bool {
        match self.find_unit_by_card(card) {
            Some(u) => self.gs.unit(u).empowered,
            None => false,
        }
    }
}
