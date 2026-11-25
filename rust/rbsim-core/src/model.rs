//! The game state: py core/state.py, player.py, cards.py, combat.py
//! (UnitInPlay), battlefield.py. Objects with identity live in arenas of
//! `GameState` (cards, units, deployed gear); lists hold their ids.

use serde_json::Value;
use std::rc::Rc;

use crate::pydict::PyDict;
use crate::registry::{Registry, Spec};
use crate::rng::PyRandom;
use crate::types::*;

// ---------------------------------------------------------------- cards ---

/// py: cards.Card (and subclasses). Static data comes from the registry spec
/// (`spec`); the fields here are what play changes or sets on the instance.
#[derive(Clone, Debug)]
pub struct Card {
    pub spec: u32,
    pub tapped: bool,
    /// `card.might = n` (a token made with a given Might).
    pub might_override: Option<i64>,
    pub is_token: Option<bool>,
    // Dynamic attributes (None: absent or None in Python).
    pub attached_to: Option<UnitId>,
    pub attached_turn: Option<i64>,
    pub chosen_card: Option<CardId>,
    pub graceful_from: Option<Value>,
    pub graceful_owed: Option<Vec<UnitId>>,
    pub graceful_prepaid: Option<Value>,
    pub granted_repeat: Option<Value>,
    pub kicker_paid: Option<bool>,
    /// py: the attribute `_kicker_paid` exists on the card (set once, to anything,
    /// even None): getattr(card, "_kicker_paid", False) is False only before.
    pub kicker_set: bool,
    pub owner: Option<Side>,
    pub play_pending: Option<Value>,
    pub played_from: Option<String>,
    /// py: Card._named_spell ("Name a spell": Fallen Feline)
    pub named_spell: Option<String>,
    pub power_paid: Option<i64>,
    pub repeat_extra: Option<Value>,
    pub repeat_paid: Option<Value>,
    pub showed_off: Option<bool>,
    /// py: the attribute `_showed_off` exists (as kicker_set).
    pub showed_set: bool,
    pub shown: Option<Value>,
    pub spent: Option<i64>,
    pub hidden_bf: Option<usize>,
    pub temporary: Option<bool>,
    pub empowered: Option<bool>,
    pub flow_banish: Option<bool>,
    /// py: Card.uuid (uuid4 at creation, kept by every copy of the game): what
    /// a card's repr names it by (the search's trigger labels).
    pub uuid: u64,
}

impl Card {
    /// py: card._kicker_paid = v
    pub fn set_kicker(&mut self, v: Option<bool>) {
        self.kicker_paid = v;
        self.kicker_set = true;
    }
    /// py: card._showed_off = v
    pub fn set_showed(&mut self, v: Option<bool>) {
        self.showed_off = v;
        self.showed_set = true;
    }
    /// py: getattr(card, "_kicker_paid", False)
    pub fn kicker_or_false(&self) -> Option<bool> {
        if self.kicker_set { self.kicker_paid } else { Some(false) }
    }
    /// py: getattr(card, "_showed_off", False)
    pub fn showed_or_false(&self) -> Option<bool> {
        if self.showed_set { self.showed_off } else { Some(false) }
    }
}

static CARD_UUIDS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(1);

impl Card {
    pub fn new(spec: u32) -> Card {
        Card {
            uuid: CARD_UUIDS.fetch_add(1, std::sync::atomic::Ordering::Relaxed),
            spec,
            tapped: false,
            might_override: None,
            is_token: None,
            attached_to: None,
            attached_turn: None,
            chosen_card: None,
            graceful_from: None,
            graceful_owed: None,
            graceful_prepaid: None,
            granted_repeat: None,
            kicker_paid: None,
            kicker_set: false,
            owner: None,
            play_pending: None,
            played_from: None,
            named_spell: None,
            power_paid: None,
            repeat_extra: None,
            repeat_paid: None,
            showed_off: None,
            showed_set: false,
            shown: None,
            spent: None,
            hidden_bf: None,
            temporary: None,
            empowered: None,
            flow_banish: None,
        }
    }
}

// ---------------------------------------------------------------- units ---

/// py: combat.UnitInPlay.
#[derive(Clone, Debug)]
pub struct Unit {
    pub card: CardId,
    pub damage: i64,
    pub ready: bool,
    pub bonus_might: i64,
    pub temporary_might: i64,
    pub gear: Vec<CardId>,
    pub stunned: bool,
    pub might_counters: i64,
    pub aura_might: i64,
    pub passive_might: i64,
    pub passive_keywords: Vec<String>,
    pub hidden: bool,
    pub empowered: bool,
    pub empower_times: i64,
    pub is_token: bool,
    pub no_combat_damage: bool,
    pub turn_keywords: Vec<String>,
    pub granted_keywords: Vec<String>,
    pub combat_keywords: Vec<String>,
    pub combat_might: i64,
    pub doomed_turn: i64,
    pub ward_turn: i64,
    pub prevent_next_turn: i64,
    pub was_mighty: bool,
    pub ward_free: bool,
    pub banish_if_dies_turn: i64,
    pub death_bonus: Option<Value>,
    pub damaged_turn: i64,
    pub unmovable_by_enemies: bool,
    pub turn_abilities: Vec<(i64, Spec)>,
    pub win_xp_turn: i64,
    pub cant_move_turn: i64,
    pub equip_bonus_mult: i64,
    pub base_might_override: Option<i64>,
    pub moves_this_turn: i64,
    pub unchoosable: bool,
    pub cant_be_chosen_turn: i64,
    pub no_move_to_base: bool,
    pub cant_ready: bool,
    pub spell_immune: bool,
    pub double_damage_turn: i64,
    pub damage_shield: i64,
    pub conquered_turn: i64,
    pub borrowed: Option<(Side, i64)>,
    pub extra_tags: Vec<String>,
    pub copied_from: Option<CardId>,
    pub gear_unit: bool,
}

impl Unit {
    pub fn new(card: CardId) -> Unit {
        Unit {
            card,
            damage: 0,
            ready: false,
            bonus_might: 0,
            temporary_might: 0,
            gear: Vec::new(),
            stunned: false,
            might_counters: 0,
            aura_might: 0,
            passive_might: 0,
            passive_keywords: Vec::new(),
            hidden: false,
            empowered: false,
            empower_times: 0,
            is_token: false,
            no_combat_damage: false,
            turn_keywords: Vec::new(),
            granted_keywords: Vec::new(),
            combat_keywords: Vec::new(),
            combat_might: 0,
            doomed_turn: -1,
            ward_turn: -1,
            prevent_next_turn: -1,
            was_mighty: false,
            ward_free: false,
            banish_if_dies_turn: -1,
            death_bonus: None,
            damaged_turn: -1,
            unmovable_by_enemies: false,
            turn_abilities: Vec::new(),
            win_xp_turn: -1,
            cant_move_turn: -1,
            equip_bonus_mult: 1,
            base_might_override: None,
            moves_this_turn: 0,
            unchoosable: false,
            cant_be_chosen_turn: -1,
            no_move_to_base: false,
            cant_ready: false,
            spell_immune: false,
            double_damage_turn: -1,
            damage_shield: 0,
            conquered_turn: -1,
            borrowed: None,
            extra_tags: Vec::new(),
            copied_from: None,
            gear_unit: false,
        }
    }
    /// py: UnitInPlay.reset_damage
    pub fn reset_damage(&mut self) {
        self.damage = 0;
        self.bonus_might = 0;
    }
    /// py: UnitInPlay.clear_combat_bonuses
    pub fn clear_combat_bonuses(&mut self) {
        self.combat_keywords.clear();
        self.combat_might = 0;
    }
    /// py: UnitInPlay.clear_turn_end_bonuses
    pub fn clear_turn_end_bonuses(&mut self) {
        self.temporary_might = 0;
        self.turn_keywords.clear();
        self.clear_combat_bonuses();
        self.base_might_override = None;
        self.moves_this_turn = 0;
        self.damage_shield = 0;
    }
}

/// py: battlefield.DeployedGear.
#[derive(Clone, Debug)]
pub struct DGear {
    pub card: CardId,
    pub is_token: bool,
}

/// py: battlefield.FacedownCard.
#[derive(Clone, Debug, PartialEq)]
pub struct Facedown {
    pub card: CardId,
    pub owner: Side,
    pub turn_hidden: i64,
}

// ---------------------------------------------------------- battlefield ---

/// py: battlefield.Battlefield (identity: its index in gs.battlefields).
#[derive(Clone, Debug)]
pub struct Battlefield {
    pub units: [Vec<UnitId>; 2],
    pub contested_this_turn: bool,
    pub scored_this_turn: [bool; 2],
    pub first_unit_here: [bool; 2],
    pub plays_here: PyDict<Side, (i64, i64)>,
    pub last_controller: Option<Side>,
    pub held_by: Option<Side>,
    pub gained_control: Option<Side>,
    pub contested_by: Option<Side>,
    pub showdown_pending: bool,
    pub card: Option<CardId>,
    pub replaced: Option<CardId>,
    pub facedowns: Vec<Facedown>,
    pub conquered_turn: PyDict<Side, i64>,
    pub excess_damage: PyDict<Side, (i64, i64)>,
    /// A set of units: kept in insertion order, compared as a set.
    pub combat_designated: Vec<UnitId>,
    pub combat_started: bool,
    pub combat_attacker: Option<Side>,
    pub gear: [Vec<GearId>; 2],
    pub kills: [i64; 2],
    pub deaths: [i64; 2],
    /// Dynamic attribute: absent (None) or set (Some(controller or None)).
    pub prev_controller: Option<Option<Side>>,
}

impl Battlefield {
    pub fn new(card: Option<CardId>) -> Battlefield {
        Battlefield {
            units: [Vec::new(), Vec::new()],
            contested_this_turn: false,
            scored_this_turn: [false, false],
            first_unit_here: [false, false],
            plays_here: PyDict::new(),
            last_controller: None,
            held_by: None,
            gained_control: None,
            contested_by: None,
            showdown_pending: false,
            card,
            replaced: None,
            facedowns: Vec::new(),
            conquered_turn: PyDict::new(),
            excess_damage: PyDict::new(),
            combat_designated: Vec::new(),
            combat_started: false,
            combat_attacker: None,
            gear: [Vec::new(), Vec::new()],
            kills: [0, 0],
            deaths: [0, 0],
            prev_controller: None,
        }
    }
    pub fn units_for(&self, s: Side) -> &Vec<UnitId> {
        &self.units[s.idx()]
    }
    pub fn units_for_mut(&mut self, s: Side) -> &mut Vec<UnitId> {
        &mut self.units[s.idx()]
    }
    pub fn count(&self, s: Side) -> usize {
        self.units[s.idx()].len()
    }
    /// py: Battlefield.controller
    pub fn controller(&self) -> Option<Side> {
        let (a, b) = (!self.units[0].is_empty(), !self.units[1].is_empty());
        if a && !b {
            Some(Side::A)
        } else if b && !a {
            Some(Side::B)
        } else {
            None
        }
    }
    /// py: Battlefield._note_control
    pub fn note_control(&mut self) {
        if self.contested_by.is_some() {
            return;
        }
        let sole = self.controller();
        if sole.is_some() || !(!self.units[0].is_empty() || !self.units[1].is_empty()) {
            self.hold(sole, true);
        }
    }
    /// py: Battlefield._hold
    pub fn hold(&mut self, side: Option<Side>, gained: bool) {
        if side != self.held_by {
            self.held_by = side;
            self.gained_control = if gained { side } else { None };
        }
    }
    /// py: Battlefield.control
    pub fn control(&mut self) -> Option<Side> {
        self.note_control();
        self.held_by
    }
    /// py: Battlefield.contest
    pub fn contest(&mut self, who: Side, before: Option<Side>) -> bool {
        if self.contested_by.is_some() || self.units[who.idx()].is_empty() {
            return false;
        }
        let both_before = before.is_none() && !self.units[0].is_empty() && !self.units[1].is_empty();
        let held = if both_before { self.held_by } else { before };
        if Some(who) == held {
            return false;
        }
        self.contested_by = Some(who);
        self.hold(held, false);
        true
    }
    /// py: Battlefield.establish_control
    pub fn establish_control(&mut self) {
        if !self.units[0].is_empty() && !self.units[1].is_empty() {
            return;
        }
        self.contested_by = None;
        self.note_control();
    }
    /// py: Battlefield.begin_turn_reset
    pub fn begin_turn_reset(&mut self) {
        self.note_control();
        self.gained_control = None;
        self.contested_this_turn = false;
        self.scored_this_turn = [false, false];
        self.first_unit_here = [false, false];
        self.showdown_pending = false;
    }
    /// The tail shared by add/remove/pop/resolve: contested / showdown_pending.
    pub fn after_change(&mut self) {
        if !self.units[0].is_empty() && !self.units[1].is_empty() {
            self.contested_this_turn = true;
            if self.controller().is_none() {
                self.showdown_pending = true;
            }
        } else {
            self.showdown_pending = false;
        }
    }
    /// py: Battlefield.add_unit
    pub fn add_unit(&mut self, who: Side, u: UnitId) {
        self.note_control();
        self.units[who.idx()].push(u);
        self.note_control();
        self.after_change();
    }
    /// py: Battlefield.remove_unit
    pub fn remove_unit(&mut self, who: Side, u: UnitId) {
        let l = &mut self.units[who.idx()];
        if let Some(i) = l.iter().position(|&x| x == u) {
            l.remove(i);
        }
        self.note_control();
        self.after_change();
    }
    /// py: Battlefield.can_score_hold
    pub fn can_score_hold(&self, active: Side) -> bool {
        if self.controller() != Some(active) {
            return false;
        }
        !self.scored_this_turn[active.idx()]
    }
    /// py: Battlefield.mark_scored
    pub fn mark_scored(&mut self, who: Side) {
        self.scored_this_turn[who.idx()] = true;
    }
    /// py: Battlefield.can_score_conquer
    pub fn can_score_conquer(&self, active: Side) -> bool {
        if self.controller() != Some(active) {
            return false;
        }
        if self.gained_control != Some(active) {
            return false;
        }
        if !self.contested_this_turn {
            return false;
        }
        !self.scored_this_turn[active.idx()]
    }
}

// --------------------------------------------------------------- player ---

/// py: player.Rune (value equality).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Rune {
    pub domain: Domain,
    pub ready: bool,
}

/// py: player.RuneDeck.
#[derive(Clone, Debug)]
pub struct RuneDeck {
    pub runes: Vec<Rune>,
    pub unseen: Option<i64>,
}

impl RuneDeck {
    pub fn top_seen(&mut self) {
        if let Some(u) = self.unseen {
            if u != 0 {
                self.unseen = Some(u - 1);
            }
        }
    }
    pub fn draw(&mut self) -> Option<Rune> {
        if self.runes.is_empty() {
            return None;
        }
        self.top_seen();
        Some(self.runes.remove(0))
    }
    pub fn recycle(&mut self, mut r: Rune) {
        r.ready = true;
        self.runes.push(r);
    }
}

/// py: player.Deck. Top = end of the list.
#[derive(Clone, Debug, Default)]
pub struct Deck {
    pub cards: Vec<CardId>,
    pub known_top: Vec<CardId>,
}

impl Deck {
    /// py: Deck.known_on_top
    pub fn known_on_top(&self) -> Vec<CardId> {
        let mut out = Vec::new();
        for &card in &self.known_top {
            if !self.cards.contains(&card) {
                continue;
            }
            if out.len() < self.cards.len() && self.cards[self.cards.len() - 1 - out.len()] == card {
                out.push(card);
            } else {
                break;
            }
        }
        out
    }
    pub fn draw(&mut self) -> Option<CardId> {
        self.cards.pop()
    }
    pub fn shuffle(&mut self, rng: &mut PyRandom) {
        rng.shuffle(&mut self.cards);
        self.known_top.clear();
    }
}

/// py: player.Player.
#[derive(Clone, Debug)]
pub struct Player {
    pub name: Side,
    pub hp: i64,
    pub hand: Vec<CardId>,
    pub hand_public: Vec<CardId>,
    pub deck: Deck,
    pub trash: Vec<CardId>,
    pub banished: Vec<CardId>,
    pub base_gear: Vec<CardId>,
    pub rune_energy: i64,
    pub pool_energy: i64,
    pub earmarked_energy_showdown: i64,
    pub earmarked_power_gear: i64,
    pub earmarked_power_spell: i64,
    pub earmarked_power_permanent: i64,
    pub earmarked_energy_spell: i64,
    pub earmarked_energy_unit: i64,
    pub rune_deck: RuneDeck,
    pub rune_pool: PyDict<Domain, Vec<Rune>>,
    pub power_pool: PyDict<Domain, i64>,
    pub floating_power: PyDict<Domain, i64>,
    pub power_spent_this_turn: i64,
    pub draws_this_turn: i64,
    pub base_units: Vec<UnitId>,
    /// Dynamic attribute (recycle_rune).
    pub runes_recycled: Option<i64>,
    /// Whether an agent sits here (py: player.agent is not None).
    pub has_agent: bool,
    /// The coach page's payment preference while one card cost is paid (py:
    /// CoachLoop._pay_card_cost's temporary `actor.pay_power_of`): the Power
    /// the cost needs is paid from this domain first. None outside that call.
    pub pay_first: Option<Domain>,
}

impl Player {
    pub fn new(name: Side, deck: Deck, rune_deck: RuneDeck) -> Player {
        Player {
            name,
            hp: 10,
            hand: Vec::new(),
            hand_public: Vec::new(),
            deck,
            trash: Vec::new(),
            banished: Vec::new(),
            base_gear: Vec::new(),
            rune_energy: 0,
            pool_energy: 0,
            earmarked_energy_showdown: 0,
            earmarked_power_gear: 0,
            earmarked_power_spell: 0,
            earmarked_power_permanent: 0,
            earmarked_energy_spell: 0,
            earmarked_energy_unit: 0,
            rune_deck,
            rune_pool: PyDict::new(),
            power_pool: PyDict::new(),
            floating_power: PyDict::new(),
            power_spent_this_turn: 0,
            draws_this_turn: 0,
            base_units: Vec::new(),
            runes_recycled: None,
            has_agent: false,
            pay_first: None,
        }
    }
    /// py: Player.energy (property)
    pub fn energy(&self) -> i64 {
        self.rune_energy + self.pool_energy
    }
    /// py: Player.energy = value
    pub fn set_energy(&mut self, value: i64) {
        let delta = value - self.energy();
        if delta < 0 {
            let from_pool = (-delta).min(self.pool_energy.max(0));
            self.pool_energy -= from_pool;
            self.rune_energy += delta + from_pool;
        } else {
            self.rune_energy += delta;
        }
    }
    pub fn add_energy(&mut self, amount: i64) {
        self.pool_energy += amount;
    }
    pub fn total_runes_in_play(&self) -> i64 {
        self.rune_pool.values().map(|v| v.len() as i64).sum()
    }
    /// py: Player.ready_runes
    pub fn ready_runes(&mut self, n: i64) {
        let exhausted = (self.total_runes_in_play() - self.rune_energy).max(0);
        let k = n.min(exhausted);
        self.rune_energy += k;
        self.pool_energy += n - k;
    }
    /// py: Player.runes_left_play
    pub fn runes_left_play(&mut self) {
        let over = self.rune_energy - self.total_runes_in_play();
        if over > 0 {
            self.rune_energy -= over;
            self.pool_energy += over;
        }
    }
    /// py: Player.empty_rune_pool
    pub fn empty_rune_pool(&mut self) {
        self.pool_energy = 0;
        let fl: Vec<(Domain, i64)> = self.floating_power.items().clone();
        for (domain, n) in fl {
            let left = self.power_pool.get_or(&domain, 0) - n;
            if left > 0 {
                self.power_pool.set(domain, left);
            } else {
                self.power_pool.pop(&domain);
            }
        }
        self.floating_power.clear();
        self.earmarked_energy_showdown = 0;
        self.earmarked_power_gear = 0;
        self.earmarked_power_spell = 0;
        self.earmarked_power_permanent = 0;
        self.earmarked_energy_spell = 0;
        self.earmarked_energy_unit = 0;
    }
    /// py: Player.add_rune
    pub fn add_rune(&mut self, domain: Domain, ready: bool) {
        self.rune_pool.setdefault(domain, Vec::new()).push(Rune { domain, ready });
    }
    /// py: Player.unlock_runes
    pub fn unlock_runes(&mut self, n: i64, exhausted: bool) {
        for _ in 0..n {
            if self.total_runes_in_play() >= 12 {
                break;
            }
            let Some(mut rune) = self.rune_deck.draw() else { break };
            rune.ready = false;
            self.rune_pool.setdefault(rune.domain, Vec::new()).push(rune);
            let v = self.power_pool.get_or(&rune.domain, 0) + 1;
            self.power_pool.set(rune.domain, v);
            if !exhausted {
                self.rune_energy += 1;
            }
        }
    }
    /// py: Player.recycle_rune
    pub fn recycle_rune(&mut self, domain: Domain) -> bool {
        let Some(runes) = self.rune_pool.get_mut(&domain) else { return false };
        if runes.is_empty() {
            return false;
        }
        let rune = runes.remove(0);
        if runes.is_empty() {
            self.rune_pool.pop(&domain);
        }
        self.rune_deck.recycle(rune);
        self.runes_left_play();
        self.runes_recycled = Some(self.runes_recycled.unwrap_or(0) + 1);
        true
    }
    /// py: Player.awaken_runes
    pub fn awaken_runes(&mut self) {
        for (_, runes) in self.rune_pool.iter_mut() {
            for r in runes.iter_mut() {
                r.ready = true;
            }
        }
    }
    /// py: Player.channel
    pub fn channel(&mut self) {
        let mut domains: Vec<Domain> = self.rune_pool.keys().copied().collect();
        domains.sort_by_key(|d| d.name());
        for d in domains {
            let n_ready = {
                let runes = self.rune_pool.get_mut(&d).unwrap();
                let mut n = 0;
                for r in runes.iter_mut() {
                    if r.ready {
                        r.ready = false;
                        n += 1;
                    }
                }
                n
            };
            for _ in 0..n_ready {
                self.rune_energy += 1;
                let v = self.power_pool.get_or(&d, 0) + 1;
                self.power_pool.set(d, v);
            }
        }
        let mut order: Vec<(Domain, i64)> = self.power_pool.items().clone();
        order.sort_by_key(|(d, _)| d.name());
        self.power_pool = PyDict::from_items(order);
    }
    /// py: Player.ready_base_units is on GameState (needs the unit arena).
    /// py: Player._power_left
    pub fn power_left(&self, domain: Domain) -> i64 {
        self.power_pool
            .get_or(&domain, 0)
            .min(self.rune_pool.get(&domain).map(|v| v.len() as i64).unwrap_or(0) + self.floating_power.get_or(&domain, 0))
    }
    pub fn can_pay_power_of(&self, n: i64, domains: &[Domain]) -> bool {
        domains.iter().map(|&d| self.power_left(d)).sum::<i64>() >= n
    }
    /// py: Player.pay_power_of (with CoachLoop's `first` over it while `pay_first` is set).
    pub fn pay_power_of(&mut self, n: i64, domains: &[Domain]) -> bool {
        if let Some(d) = self.pay_first {
            let k = if domains.contains(&d) { n.min(self.power_left(d)) } else { 0 };
            if k != 0 && !self.pay_cost(0, Some(k), Some(d)) {
                return false;
            }
            return if n > k { self.pay_power_of_base(n - k, domains) } else { true };
        }
        self.pay_power_of_base(n, domains)
    }
    /// py: Player.pay_power_of, the engine's own way.
    fn pay_power_of_base(&mut self, n: i64, domains: &[Domain]) -> bool {
        for _ in 0..n {
            // max(): the first domain with the most left
            let mut best = domains[0];
            let mut best_v = self.power_left(best);
            for &d in &domains[1..] {
                let v = self.power_left(d);
                if v > best_v {
                    best = d;
                    best_v = v;
                }
            }
            if best_v == 0 || !self.pay_cost(0, Some(1), Some(best)) {
                return false;
            }
        }
        true
    }
    /// py: Player.can_pay_cost
    pub fn can_pay_cost(&self, cost_energy: i64, cost_power: Option<i64>, domain: Option<Domain>) -> bool {
        if self.energy() < cost_energy {
            return false;
        }
        let cp = cost_power.unwrap_or(0);
        if cp == 0 {
            return true;
        }
        match domain {
            None => self.can_pay_power_of(cp, &Domain::ALL),
            Some(d) => self.power_left(d) >= cp,
        }
    }
    /// py: Player.pay_cost
    pub fn pay_cost(&mut self, cost_energy: i64, cost_power: Option<i64>, domain: Option<Domain>) -> bool {
        if !self.can_pay_cost(cost_energy, cost_power, domain) {
            return false;
        }
        let e = self.energy() - cost_energy;
        self.set_energy(e);
        let cp = cost_power.unwrap_or(0);
        if cp != 0 && domain.is_none() {
            return self.pay_power_of(cp, &Domain::ALL);
        }
        if cp != 0 {
            let d = domain.unwrap();
            self.power_spent_this_turn += cp;
            let current = self.power_pool.get_or(&d, 0) - cp;
            if current <= 0 {
                self.power_pool.pop(&d);
            } else {
                self.power_pool.set(d, current);
            }
            let floating = cp.min(self.floating_power.get_or(&d, 0));
            if floating != 0 {
                let v = self.floating_power.get_or(&d, 0) - floating;
                self.floating_power.set(d, v);
            }
            for _ in 0..(cp - floating) {
                if !self.recycle_rune(d) {
                    return false;
                }
            }
        }
        true
    }
    /// py: Player.add_power
    pub fn add_power(&mut self, d: Domain, amount: i64) {
        let v = self.power_pool.get_or(&d, 0) + amount;
        self.power_pool.set(d, v);
        let f = self.floating_power.get_or(&d, 0) + amount;
        self.floating_power.set(d, f);
    }
    /// py: Player.draw
    pub fn draw(&mut self) -> Option<CardId> {
        let c = self.deck.draw()?;
        self.to_hand(c, false);
        Some(c)
    }
    /// py: Player.to_hand
    pub fn to_hand(&mut self, c: CardId, public: bool) {
        self.hand.push(c);
        if public {
            self.mark_hand_public(&[c]);
        } else {
            self.hand_public.retain(|&x| x != c);
        }
    }
    /// py: Player.hand_known
    pub fn hand_known(&self) -> Vec<CardId> {
        self.hand_public.iter().copied().filter(|c| self.hand.contains(c)).collect()
    }
    /// py: Player.forget_hand_public (could_be: None = all)
    pub fn forget_hand_public_all(&mut self) {
        self.hand_public = Vec::new();
    }
    /// py: Player.mark_hand_public
    pub fn mark_hand_public(&mut self, cards: &[CardId]) {
        let mut known = self.hand_known();
        for &c in cards {
            if self.hand.contains(&c) && !known.contains(&c) {
                known.push(c);
            }
        }
        self.hand_public = known;
    }
    /// py: Player.mulligan
    pub fn mulligan(&mut self, indices: &[i64], rng: &mut PyRandom) -> Vec<CardId> {
        let mut chosen: Vec<usize> = Vec::new();
        for &i in indices {
            if i >= 0 && (i as usize) < self.hand.len() && !chosen.contains(&(i as usize)) {
                chosen.push(i as usize);
            }
        }
        // dict.fromkeys keeps the first occurrence; out-of-range are dropped before the [:2]
        let chosen: Vec<usize> = chosen.into_iter().take(2).collect();
        if chosen.is_empty() {
            return Vec::new();
        }
        let set_aside: Vec<CardId> = chosen.iter().map(|&i| self.hand[i]).collect();
        let mut sorted = chosen.clone();
        sorted.sort_unstable_by(|a, b| b.cmp(a));
        for i in sorted {
            self.hand.remove(i);
        }
        for _ in &set_aside {
            if let Some(c) = self.deck.draw() {
                self.to_hand(c, false);
            }
        }
        let mut recycled = set_aside.clone();
        if recycled.len() > 1 {
            rng.shuffle(&mut recycled);
        }
        let mut cards = recycled;
        cards.extend(self.deck.cards.drain(..));
        self.deck.cards = cards;
        set_aside
    }
}

// ---------------------------------------------------------------- chain ---

/// py: ChainItem.ability (a dict) for an activated / triggered ability.
#[derive(Clone, Debug)]
pub struct Ability {
    pub eff: Option<Spec>,
    pub kind: String,
    pub energy: i64,
    pub extra: Extra,
    pub target: Option<UnitId>,
    pub rest: Vec<(usize, Spec)>,
    pub bf: Option<usize>,
    pub flags: Option<Flags>,
    pub trigger: Option<String>,
    pub additional: bool,
    pub once: bool,
    pub cond_extra: Option<Extra>,
    pub cost: Option<Value>,
    /// Other keys of the dict (activated abilities): name -> value.
    pub other: PyDict<String, XVal>,
}

impl Ability {
    pub fn new(kind: &str) -> Ability {
        Ability {
            eff: None,
            kind: kind.to_string(),
            energy: 0,
            extra: Extra::default(),
            target: None,
            rest: Vec::new(),
            bf: None,
            flags: None,
            trigger: None,
            additional: false,
            once: false,
            cond_extra: None,
            cost: None,
            other: PyDict::new(),
        }
    }
}

/// A trigger's / effect's context dict (py: context_extra / ctx.extra).
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Extra {
    pub items: PyDict<String, XVal>,
}

/// A value in an `extra` dict.
#[derive(Clone, Debug, PartialEq)]
pub enum XVal {
    Bf(usize),
    Unit(UnitId),
    Card(CardId),
    Side(Side),
    Int(i64),
    Bool(bool),
    Str(String),
    None,
    Json(Value),
    List(Vec<XVal>),
}

impl Extra {
    pub fn get(&self, k: &str) -> Option<&XVal> {
        self.items.get(&k.to_string())
    }
    pub fn set(&mut self, k: &str, v: XVal) {
        self.items.set(k.to_string(), v);
    }
    pub fn bf(&self, k: &str) -> Option<usize> {
        match self.get(k) {
            Some(XVal::Bf(b)) => Some(*b),
            _ => None,
        }
    }
    pub fn unit(&self, k: &str) -> Option<UnitId> {
        match self.get(k) {
            Some(XVal::Unit(u)) => Some(*u),
            _ => None,
        }
    }
    pub fn card(&self, k: &str) -> Option<CardId> {
        match self.get(k) {
            Some(XVal::Card(c)) => Some(*c),
            _ => None,
        }
    }
    /// dict(a, **b)
    pub fn merged(&self, b: &Extra) -> Extra {
        let mut out = self.clone();
        for (k, v) in b.items.iter() {
            out.items.set(k.clone(), v.clone());
        }
        out
    }
}

/// A card's play flags (py: GameLoop._card_flags: kicker paid, SHOW OFF, ...).
pub type Flags = PyDict<String, XVal>;

/// The choices a chain item declared (py: {(run, instr, n): (kind, n options, chosen)}).
#[derive(Clone, Debug, Default)]
pub struct Declared {
    pub items: Vec<((i64, i64, i64), (String, usize, Chosen))>,
}

/// What a choice chose (an option, or a list for choose_many).
#[derive(Clone, Debug, PartialEq)]
pub enum Chosen {
    One(Opt),
    Many(Vec<Opt>),
}

/// An option of a choice (py: the heterogeneous `options` list of choose()).
#[derive(Clone, Debug, PartialEq)]
pub enum Opt {
    Unit(UnitId),
    Card(CardId),
    Bf(usize),
    Gear(GearId),
    Bool(bool),
    Int(i64),
    Domain(Domain),
    Side(Side),
    Chain(usize),
    Trigger(usize),
    NoMore,
    Str(String),
    /// A plain value (a dict of a cost_extras option: py `{"energy": 3, ...}`).
    Json(Value),
    /// A tuple (location, object) or another small tuple.
    Tuple(Vec<Opt>),
    None,
}

/// py: state.ChainItem.
#[derive(Clone, Debug)]
pub struct ChainItem {
    /// The item's identity (py: the ChainItem object): set as it goes on the chain.
    pub uid: usize,
    pub player: Side,
    pub card: CardId,
    pub bf_idx: usize,
    pub declared: Option<Declared>,
    pub choices_noted: bool,
    pub owner: Option<Side>,
    pub ability: Option<Ability>,
}

/// py: state.PendingTrigger.
#[derive(Clone, Debug)]
pub struct PendingTrigger {
    pub card: CardId,
    pub trigger: String,
    pub side: Side,
    pub bf: usize,
    pub specs: Vec<(usize, Spec)>,
    pub extra: Option<Extra>,
    pub additional: bool,
    pub flags: Option<Flags>,
    pub once: bool,
    pub replay: Option<Value>,
}

// ---------------------------------------------------------------- state ---

/// py: state.GameState, plus the object arenas.
#[derive(Clone)]
pub struct GameState {
    pub reg: Rc<Registry>,
    pub cards: Vec<Card>,
    pub units: Vec<Unit>,
    pub dgear: Vec<DGear>,

    pub rng: PyRandom,
    pub players: [Player; 2],
    pub turn: i64,
    pub max_turns: i64,
    pub active: Side,
    pub champion: [Option<CardId>; 2],
    pub legend: [Option<CardId>; 2],
    pub legend_unit: [Option<UnitId>; 2],
    pub extra_legends: [Vec<CardId>; 2],
    pub added_legends: [Vec<(UnitId, UnitId)>; 2],
    pub points: [i64; 2],
    pub victory_score: i64,
    pub winner: Option<Side>,
    pub battlefields: Vec<Battlefield>,
    pub champion_deployed: [bool; 2],
    pub chain: Vec<ChainItem>,
    pub pending_move: Option<(usize, Side)>,
    pub staged_showdowns: Vec<(usize, Side)>,
    pub showdown_active: bool,
    pub showdown_bf_idx: Option<usize>,
    pub showdown_attacker: Option<Side>,
    pub focus_player: Option<Side>,
    pub xp: [i64; 2],
    pub cards_played_this_turn: [i64; 2],
    pub spells_played_this_turn: [i64; 2],
    pub played_cards_this_turn: [Vec<CardId>; 2],
    pub enemy_choices_this_turn: [i64; 2],
    pub next_card_discounts: [Vec<Value>; 2],
    pub delayed_effects: Vec<Value>,
    pub delayed_main: Vec<Value>,
    /// key -> turn: (source card, effect index or tag), or (tag, side).
    pub once_per_turn_used: PyDict<OnceK, i64>,
    pub xp_gained_turn: PyDict<Side, i64>,
    pub no_spell_damage_turn: i64,
    pub decree_turn: i64,
    pub next_spell_bonus: PyDict<Side, i64>,
    pub modes_chosen: PyDict<(CardId, i64), Vec<i64>>,
    pub next_unit_any_bf: PyDict<Side, i64>,
    pub next_unit_accelerate: PyDict<Side, i64>,
    pub next_spell_repeat: PyDict<Side, i64>,
    pub held_hostage: Vec<(Side, CardId)>,
    pub move_group: Option<(i64, Side, usize, i64)>,
    pub jhin_pile: PyDict<Side, Vec<CardId>>,
    pub spell_spent: PyDict<Side, (i64, i64)>,
    pub turn_cost_changes: Vec<Value>,
    pub extra_turns: Vec<Side>,
    pub free_hide: PyDict<Side, i64>,
    pub buff_bonus_turn: PyDict<Side, i64>,
    pub rally_turn: PyDict<Side, i64>,
    pub conquer_return: Vec<(UnitId, i64)>,
    pub cant_play_spells_turn: PyDict<Side, i64>,
    /// The next chain item identity (ChainItem.uid).
    pub chain_uid: usize,
    /// Items that left the chain while it isn't empty: a counter's declared
    /// target still names one (py: the object, dumped by value).
    pub chain_gone: Vec<ChainItem>,
    pub next_unit_ready_buff: PyDict<Side, i64>,
    pub died_in_beginning: PyDict<Side, i64>,
    pub in_beginning_phase: bool,
    pub runes_at_beginning: (i64, PyDict<Side, i64>),
    pub in_ending_phase: bool,
    pub turns_taken: [i64; 2],
    pub cant_play_cards_turn: PyDict<Side, i64>,
    pub unit_play_draws: PyDict<Side, (i64, i64)>,
    pub units_enter_ready_turn: [i64; 2],
    pub next_units_enter_ready: [i64; 2],
    pub friendly_unit_died_this_turn: [bool; 2],
    pub friendly_gear_died_this_turn: [bool; 2],
    pub discarded_this_turn: [bool; 2],
    pub cards_burned_this_turn: [i64; 2],
    pub conquered_this_turn: [i64; 2],
    pub hold_points_this_turn: [i64; 2],
}

/// A once_per_turn_used key.
#[derive(Clone, Debug, PartialEq)]
pub enum OnceK {
    Card(CardId, OnceKey),
    Named(String, Side),
}

/// The second part of a (card, ...) once_per_turn_used key.
#[derive(Clone, Debug, PartialEq)]
pub enum OnceKey {
    Idx(i64),
    Str(String),
    Json(Value),
}

impl GameState {
    /// Where the chain item with identity `uid` is on the chain (Opt::Chain / Obj::Chain hold the uid).
    pub fn chain_pos(&self, uid: usize) -> Option<usize> {
        self.chain.iter().position(|c| c.uid == uid)
    }
    pub fn other(&self, s: Side) -> Side {
        s.other()
    }
    pub fn player(&self, s: Side) -> &Player {
        &self.players[s.idx()]
    }
    pub fn player_mut(&mut self, s: Side) -> &mut Player {
        &mut self.players[s.idx()]
    }
    pub fn card(&self, c: CardId) -> &Card {
        &self.cards[c.i()]
    }
    pub fn card_mut(&mut self, c: CardId) -> &mut Card {
        &mut self.cards[c.i()]
    }
    pub fn unit(&self, u: UnitId) -> &Unit {
        &self.units[u.i()]
    }
    pub fn unit_mut(&mut self, u: UnitId) -> &mut Unit {
        &mut self.units[u.i()]
    }
    pub fn new_card(&mut self, spec: u32) -> CardId {
        self.cards.push(Card::new(spec));
        CardId((self.cards.len() - 1) as u32)
    }
    pub fn new_unit(&mut self, u: Unit) -> UnitId {
        self.units.push(u);
        UnitId((self.units.len() - 1) as u32)
    }
    pub fn new_dgear(&mut self, g: DGear) -> GearId {
        self.dgear.push(g);
        GearId((self.dgear.len() - 1) as u32)
    }
    pub fn get_xp(&self, s: Side) -> i64 {
        self.xp[s.idx()]
    }
    /// py: GameState.add_xp
    pub fn add_xp(&mut self, s: Side, amount: i64) {
        self.xp[s.idx()] += amount;
        if amount > 0 {
            self.xp_gained_turn.set(s, self.turn);
        }
    }
}
