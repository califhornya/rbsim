//! py: loop.GameLoop — the loop's own fields and the choice machinery
//! (choose, choose_many, declared choices). The rest of GameLoop is split
//! across the lp_*.rs files as `impl Game` blocks.

use std::cell::RefCell;
use std::rc::Rc;

use crate::agent::{Agent, Chooser};
use crate::model::*;
use crate::types::*;

pub const DECLARED_CHOICES: [&str; 6] = ["target", "mode", "destination", "player", "battlefield", "tag"];
pub const PRIORITY_ROUNDS_CAP: i64 = 200;

pub fn is_declared_kind(kind: &str) -> bool {
    DECLARED_CHOICES.iter().any(|p| kind.starts_with(p))
}

/// py: {"card": card, "choices": {slot: (kind, n, chosen)}}
#[derive(Clone, Debug)]
pub struct Declaring {
    pub card: CardId,
    pub choices: Declared,
}

pub type Agents = [Option<Rc<RefCell<dyn Agent>>>; 2];

static LOOP_IDS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(1);

pub fn new_loop_id() -> u64 {
    LOOP_IDS.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
}

/// py: GameLoop (with its GameState).
#[derive(Clone)]
pub struct Game {
    pub gs: GameState,
    pub loop_id: u64,
    pub units_played: i64,
    pub spells_cast: i64,
    pub verbose: bool,
    pub chooser: Option<Rc<RefCell<dyn Chooser>>>,
    pub agents: Agents,
    pub journal: Option<Vec<JEntry>>,
    pub slot: Option<[i64; 3]>,
    pub declaring: Option<Declaring>,
    pub replay: Option<Declaring>,
    pub in_many: bool,
    pub declare_board: Option<Vec<(PresenceKey, Vec<Obj>)>>,
    pub ghost_ids: Option<Vec<Obj>>,
    pub chained_abilities: i64,
    pub pending_triggers: Vec<PendingTrigger>,
    pub task_depth: i64,
    pub flushing: bool,
    pub all_pass: bool,
    pub dry_run: bool,
    pub lookahead: bool,
    /// On a declaration's copy: the real game (for what the real players see).
    pub real: Option<*const GameState>,
    /// Arena sizes of the real game when this copy was made (objects created
    /// on the copy after that are foreign to the real game).
    pub copied_at: Option<(usize, usize, usize)>,
    pub spell_energy_paid: Option<i64>,
    pub spell_power_paid: Option<i64>,
    pub resolving_item: Option<CardId>,
    pub choices_noted: bool,
    pub discard_depth: i64,
    pub discard_sides: Vec<Side>,
    /// The pending triggers a trigger_order choice is about (for the trace).
    pub trigger_menu: Vec<PendingTrigger>,
}

/// A journal entry (py: ("decision", ...), ("choice", side, kind, n, idx)).
#[derive(Clone, Debug)]
pub enum JEntry {
    Decision(Side, String, crate::agent::Action),
    Choice(Side, String, usize, usize),
}

/// What sits in a presence list (py: _presence_lists: chain items, units, gear).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Obj {
    Unit(UnitId),
    Card(CardId),
    Gear(GearId),
    Chain(usize),
}

#[derive(Clone, Debug, PartialEq)]
pub enum PresenceKey {
    Chain,
    Units(usize, Side),
    Gear(usize, Side),
    Base(Side),
    BaseGear(Side),
    Worn(UnitId),
}

impl Game {
    pub fn new(gs: GameState) -> Game {
        Game {
            gs,
            loop_id: new_loop_id(),
            units_played: 0,
            spells_cast: 0,
            verbose: false,
            chooser: None,
            agents: [None, None],
            journal: None,
            slot: None,
            declaring: None,
            replay: None,
            in_many: false,
            declare_board: None,
            ghost_ids: None,
            chained_abilities: 0,
            pending_triggers: Vec::new(),
            task_depth: 0,
            flushing: false,
            all_pass: false,
            dry_run: false,
            lookahead: false,
            real: None,
            copied_at: None,
            spell_energy_paid: None,
            spell_power_paid: None,
            resolving_item: None,
            choices_noted: false,
            discard_depth: 0,
            discard_sides: Vec::new(),
            trigger_menu: Vec::new(),
        }
    }

    /// The game whose players are asked (the real one on a declaration's copy).
    pub fn real_gs(&self) -> &GameState {
        match self.real {
            // SAFETY: set only on a declaration's copy, while the real game is
            // borrowed (immutably in effect) by the frame running the copy.
            Some(p) => unsafe { &*p },
            None => &self.gs,
        }
    }

    pub fn agent(&self, s: Side) -> Option<Rc<RefCell<dyn Agent>>> {
        self.agents[s.idx()].clone()
    }

    pub fn has_agent(&self, s: Side) -> bool {
        self.agents[s.idx()].is_some()
    }

    // ------------------------------------------------------------ choose ---

    /// py: GameLoop.choose. `pick` is the baseline's option (by identity).
    /// Err(Ignored) is py's `raise _Ignored` (a declared option no longer legal).
    pub fn choose(&mut self, kind: &str, side: Side, options: &[Opt], pick: Opt, source: Option<CardId>)
                  -> R<Opt> {
        let slot = self.choice_slot(kind, source);
        if let (Some(slot), Some(rp)) = (slot, self.replay.as_ref()) {
            if let Some((_, (_, _, chosen))) = rp.choices.items.iter().find(|(k, _)| *k == slot) {
                let chosen = match chosen {
                    Chosen::One(o) => o.clone(),
                    Chosen::Many(_) => return Err(EngineError::Invalid("replay: many for one".into())),
                };
                return match options.iter().find(|o| same_option(o, &chosen)) {
                    Some(o) => Ok(o.clone()),
                    None => Err(EngineError::Ignored(kind.to_string())),
                };
            }
        }
        let mut pick = pick;
        if self.ghost_ids.is_some() {
            pick = self.live_instead(options, pick, &[]);
        }
        let mut got = pick.clone();
        if self.chooser.is_some() && !options.is_empty() {
            let default = options.iter().position(|o| *o == pick).unwrap_or(0);
            let i = self.consult(kind, side, options, default, source)?;
            if let Some(i) = i {
                got = options[i].clone();
            }
        }
        self.chose(slot, kind, side, options.len(), Chosen::One(got.clone()), source);
        Ok(got)
    }

    /// py: GameLoop._consult (on this loop).
    pub fn consult(&mut self, kind: &str, side: Side, options: &[Opt], default: usize, source: Option<CardId>)
                   -> R<Option<usize>> {
        let ch = self.chooser.clone().expect("consult without chooser");
        let i = ch.borrow_mut().choose(self, kind, side, options, default, source)?;
        if let Some(j) = self.journal.as_mut() {
            j.push(JEntry::Choice(side, kind.to_string(), options.len(), i.unwrap_or(default)));
        }
        Ok(i)
    }

    /// py: GameLoop.choose_many.
    pub fn choose_many(&mut self, kind: &str, side: Side, options: &[Opt], picks: &[Opt], source: Option<CardId>,
                       up_to: Option<i64>, allowed: Option<&dyn Fn(&Game, &[Opt], &Opt) -> bool>)
                       -> R<Vec<Opt>> {
        let slot = self.choice_slot(kind, source);
        if let (Some(slot), Some(rp)) = (slot, self.replay.as_ref()) {
            if let Some((_, (_, _, chosen))) = rp.choices.items.iter().find(|(k, _)| *k == slot) {
                let chosen: Vec<Opt> = match chosen {
                    Chosen::Many(v) => v.clone(),
                    Chosen::One(o) => vec![o.clone()],
                };
                let hit: Vec<Opt> = options.iter().filter(|o| chosen.iter().any(|c| same_option(o, c))).cloned().collect();
                if !chosen.is_empty() && hit.is_empty() {
                    return Err(EngineError::Ignored(kind.to_string()));
                }
                return Ok(hit);
            }
        }
        let mut picks: Vec<Opt> = picks.to_vec();
        if self.ghost_ids.is_some() {
            let mut live: Vec<Opt> = Vec::new();
            for p in &picks {
                let l = self.live_instead(options, p.clone(), &live);
                live.push(l);
            }
            picks = live;
        }
        let mut out: Vec<Opt> = picks.clone();
        if self.chooser.is_some() {
            let mut order: Vec<Opt> = picks.clone();
            for o in options {
                if !picks.iter().any(|p| p == o) {
                    order.push(o.clone());
                }
            }
            out = Vec::new();
            let most = match up_to {
                None => picks.len(),
                Some(n) => (n.max(0) as usize).min(order.len()),
            };
            self.in_many = true;
            let res: R<()> = (|| {
                while out.len() < most {
                    let left: Vec<Opt> = order
                        .iter()
                        .filter(|o| !out.iter().any(|t| t == *o) && allowed.map_or(true, |f| f(self, &out, o)))
                        .cloned()
                        .collect();
                    if left.is_empty() {
                        break;
                    }
                    if up_to.is_none() {
                        let g = self.choose(kind, side, &left, left[0].clone(), source)?;
                        out.push(g);
                        continue;
                    }
                    let mut opts = left.clone();
                    opts.push(Opt::NoMore);
                    let base = if out.len() < picks.len() { left[0].clone() } else { Opt::NoMore };
                    match self.choose(kind, side, &opts, base, source)? {
                        Opt::NoMore => break,
                        g => out.push(g),
                    }
                }
                Ok(())
            })();
            self.in_many = false;
            res?;
        }
        self.chose(slot, kind, side, options.len(), Chosen::Many(out.clone()), source);
        Ok(out)
    }

    /// py: GameLoop._choice_slot
    pub fn choice_slot(&mut self, kind: &str, source: Option<CardId>) -> Option<(i64, i64, i64)> {
        if self.slot.is_none() || self.in_many || !is_declared_kind(kind) {
            return None;
        }
        let spell = self.replay.as_ref().or(self.declaring.as_ref()).map(|d| d.card);
        if spell.is_none() || source != spell {
            return None;
        }
        let s = self.slot.as_mut().unwrap();
        let key = (s[0], s[1], s[2]);
        s[2] += 1;
        Some(key)
    }

    /// py: GameLoop._replaying
    pub fn replaying(&self, kind: &str, source: Option<CardId>) -> bool {
        let Some(s) = self.slot else { return false };
        let Some(rp) = self.replay.as_ref() else { return false };
        !self.in_many && is_declared_kind(kind) && source == Some(rp.card)
            && rp.choices.items.iter().any(|(k, _)| *k == (s[0], s[1], s[2]))
    }

    /// py: GameLoop._chose (on_choice: the coach's log, not used here).
    pub fn chose(&mut self, slot: Option<(i64, i64, i64)>, kind: &str, _side: Side, n: usize, got: Chosen,
                 _source: Option<CardId>) {
        if self.in_many {
            return;
        }
        if let (Some(slot), Some(d)) = (slot, self.declaring.as_mut()) {
            if let Some(e) = d.choices.items.iter_mut().find(|(k, _)| *k == slot) {
                e.1 = (kind.to_string(), n, got);
            } else {
                d.choices.items.push((slot, (kind.to_string(), n, got)));
            }
        }
    }

    // ------------------------------------------------- ghosts (declaring) ---

    fn is_ghost(&self, x: &Opt) -> bool {
        match x {
            Opt::Tuple(v) => v.iter().any(|e| self.is_ghost(e)),
            _ => match (self.ghost_ids.as_ref(), opt_obj(x)) {
                (Some(g), Some(o)) => g.contains(&o),
                _ => false,
            },
        }
    }

    /// py: GameLoop._option_side
    pub fn option_side(&self, x: &Opt) -> Option<Side> {
        match x {
            Opt::Tuple(v) if !v.is_empty() => match &v[0] {
                Opt::Side(s) => Some(*s),
                _ => None,
            },
            Opt::Unit(u) => self.locate_unit(*u).map(|(s, _)| s),
            Opt::Chain(i) => self.gs.chain.get(*i).map(|c| c.player),
            _ => None,
        }
    }

    /// py: GameLoop._live_instead
    pub fn live_instead(&self, options: &[Opt], pick: Opt, taken: &[Opt]) -> Opt {
        if !self.is_ghost(&pick) {
            return pick;
        }
        let side = self.option_side(&pick);
        options
            .iter()
            .find(|o| !self.is_ghost(o) && side.is_some() && self.option_side(o) == side && !taken.iter().any(|t| t == *o))
            .cloned()
            .unwrap_or(pick)
    }
}

/// An option's object, for ghost / presence checks.
pub fn opt_obj(x: &Opt) -> Option<Obj> {
    match x {
        Opt::Unit(u) => Some(Obj::Unit(*u)),
        Opt::Card(c) => Some(Obj::Card(*c)),
        Opt::Gear(g) => Some(Obj::Gear(*g)),
        Opt::Chain(i) => Some(Obj::Chain(*i)),
        _ => None,
    }
}

/// py: _same_option. Objects by identity (ids), numbers/bools/strings by value and type.
pub fn same_option(option: &Opt, chosen: &Opt) -> bool {
    match chosen {
        Opt::Tuple(c) => match option {
            Opt::Tuple(o) => o.len() == c.len() && o.iter().zip(c).all(|(a, b)| same_option(a, b)),
            _ => false,
        },
        _ => option == chosen,
    }
}
