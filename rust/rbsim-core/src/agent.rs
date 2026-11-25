//! The engine's callbacks into the players (py: player.agent.decide_*) and
//! the loop's chooser (py: GameLoop.chooser).

use crate::game::Game;
use crate::model::Opt;
use crate::types::*;

/// py: decisions.GameAction / the engine's action tuple.
#[derive(Clone, Debug, PartialEq)]
pub struct Action {
    pub kind: AKind,
    pub index: AIdx,
    pub lane: Option<i64>,
    pub dst: Option<i64>,
    /// to_engine() gives a 4-tuple (MOVE, or UNIT/CHAMPION with a destination).
    pub len4: bool,
    pub label: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AKind {
    Pass,
    Unit,
    Spell,
    Gear,
    Champion,
    Move,
    Hide,
    HiddenPlay,
    Ability,
}

impl AKind {
    pub fn name(self) -> &'static str {
        match self {
            AKind::Pass => "PASS",
            AKind::Unit => "UNIT",
            AKind::Spell => "SPELL",
            AKind::Gear => "GEAR",
            AKind::Champion => "CHAMPION",
            AKind::Move => "MOVE",
            AKind::Hide => "HIDE",
            AKind::HiddenPlay => "HIDDEN_PLAY",
            AKind::Ability => "ABILITY",
        }
    }
    pub fn from_name(s: &str) -> Option<AKind> {
        Some(match s {
            "PASS" => AKind::Pass,
            "UNIT" => AKind::Unit,
            "SPELL" => AKind::Spell,
            "GEAR" => AKind::Gear,
            "CHAMPION" => AKind::Champion,
            "MOVE" => AKind::Move,
            "HIDE" => AKind::Hide,
            "HIDDEN_PLAY" => AKind::HiddenPlay,
            "ABILITY" => AKind::Ability,
            _ => return None,
        })
    }
}

/// The `index` field: an int, a string ("champion", "ACTIVATED") or None.
#[derive(Clone, Debug, PartialEq)]
pub enum AIdx {
    None,
    Int(i64),
    Str(String),
}

impl Action {
    /// py: GameAction(kind, index, lane, dst, label) with to_engine()'s tuple length.
    pub fn new(kind: AKind, index: AIdx, lane: Option<i64>, dst: Option<i64>, label: String) -> Action {
        let len4 = kind == AKind::Move || (matches!(kind, AKind::Unit | AKind::Champion) && dst.is_some());
        Action { kind, index, lane, dst, len4, label }
    }
    pub fn pass() -> Action {
        Action::new(AKind::Pass, AIdx::None, None, None, "Pass".into())
    }
    pub fn idx_int(&self) -> Option<i64> {
        match self.index {
            AIdx::Int(i) => Some(i),
            _ => None,
        }
    }
    /// Same engine tuple (labels aside).
    pub fn same(&self, o: &Action) -> bool {
        self.kind == o.kind && self.index == o.index && self.lane == o.lane && self.len4 == o.len4
            && (!self.len4 || self.dst == o.dst)
    }
}

/// py: DecisionPoint.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Point {
    Mulligan,
    TurnAction,
    Reaction,
    ShowdownAction,
}

impl Point {
    pub fn name(self) -> &'static str {
        match self {
            Point::Mulligan => "mulligan",
            Point::TurnAction => "turn_action",
            Point::Reaction => "reaction",
            Point::ShowdownAction => "showdown_action",
        }
    }
}

/// A player's agent (py: player.agent). `g` is the game asking (the real one).
pub trait Agent {
    fn decide_action(&mut self, g: &mut Game, side: Side, cards_played: i64) -> R<Action>;
    fn decide_reaction(&mut self, g: &mut Game, side: Side) -> R<Action>;
    fn decide_showdown_action(&mut self, g: &mut Game, side: Side, bf_idx: usize) -> R<Action>;
    fn decide_mulligan(&mut self, g: &mut Game, side: Side) -> R<Vec<i64>>;
    fn decide_optional(&mut self, g: &mut Game, side: Side, card: CardId, effect_name: &str) -> R<bool>;
    fn decide_mode(&mut self, g: &mut Game, side: Side, card: CardId, n_modes: i64) -> R<Option<i64>>;
    fn decide_predict_recycle(&mut self, g: &mut Game, side: Side, card: CardId) -> R<bool>;
    /// The chooser's question for this side (py: PPOAgent.inner via PPOChooser);
    /// None keeps the baseline. Agents that are not PPO agents return None.
    fn inner(&mut self, g: &mut Game, kind: &str, side: Side, options: &[Opt], default: usize,
             source: Option<CardId>) -> R<Option<usize>> {
        let _ = (g, kind, side, options, default, source);
        Ok(None)
    }
    /// A seat that is asked with the trace's event of its decision (a human):
    /// the TraceAgent hands it the event it built before the menu's
    /// legal_actions (which notes control) ran, see `trace::decision_event_for`.
    fn wants_event(&self) -> bool {
        false
    }
    /// py: hasattr(agent, method) — the engine skips (or defaults) a
    /// decision the agent has no method for.
    fn has(&self, method: &str) -> bool {
        let _ = method;
        true
    }
}

/// py: GameLoop.chooser(loop, kind, side, options, default, source).
pub trait Chooser {
    fn choose(&mut self, g: &mut Game, kind: &str, side: Side, options: &[Opt], default: usize,
              source: Option<CardId>) -> R<Option<usize>>;
}
