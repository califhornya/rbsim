//! py: loop.py — MAIN LOOP: start, setup, the turn loop, beginning a turn,
//! the main phase's actions, ending a turn.

use crate::agent::{AKind, Action};
use crate::game::*;
use crate::model::*;
use crate::types::*;

/// py: loop.Result (winner None = "DRAW").
#[derive(Clone, Debug, PartialEq)]
pub struct GameResult {
    pub winner: Option<Side>,
    pub turns: i64,
    pub units_played: i64,
    pub spells_cast: i64,
}

impl GameResult {
    pub fn winner_name(&self) -> &'static str {
        match self.winner {
            Some(s) => s.name(),
            None => "DRAW",
        }
    }
}

impl Game {
    fn result_now(&mut self) -> Option<GameResult> {
        self.victory().map(|w| GameResult { winner: Some(w), turns: self.gs.turn, units_played: self.units_played, spells_cast: self.spells_cast })
    }

    /// py: start()
    pub fn start(&mut self) -> R<GameResult> {
        self.setup()?;
        self.play_all_turns()
    }

    /// py: resume_to_completion()
    pub fn resume_to_completion(&mut self) -> R<GameResult> {
        if let Some(r) = self.run_main_actions()? {
            return Ok(r);
        }
        if let Some(r) = self.end_turn()? {
            return Ok(r);
        }
        self.play_all_turns()
    }

    /// py: _setup
    pub fn setup(&mut self) -> R<()> {
        for s in Side::BOTH {
            if let Some(l) = self.gs.legend[s.idx()] {
                if self.gs.legend_unit[s.idx()].is_none() {
                    let mut u = Unit::new(l);
                    u.ready = true;
                    let id = self.gs.new_unit(u);
                    self.gs.legend_unit[s.idx()] = Some(id);
                }
            }
        }
        for _ in 0..4 {
            self.gs.players[0].draw();
            self.gs.players[1].draw();
        }
        self.phase_mulligan()
    }

    /// py: _play_all_turns
    pub fn play_all_turns(&mut self) -> R<GameResult> {
        while self.gs.turn <= self.gs.max_turns {
            if let Some(r) = self.begin_turn()? {
                return Ok(r);
            }
            if let Some(r) = self.run_main_actions()? {
                return Ok(r);
            }
            if let Some(r) = self.end_turn()? {
                return Ok(r);
            }
        }
        Ok(GameResult { winner: None, turns: self.gs.turn - 1, units_played: self.units_played, spells_cast: self.spells_cast })
    }

    /// py: _begin_turn
    pub fn begin_turn(&mut self) -> R<Option<GameResult>> {
        let gs = &mut self.gs;
        let active = gs.active;
        gs.cards_played_this_turn = [0, 0];
        gs.spells_played_this_turn = [0, 0];
        gs.played_cards_this_turn = [Vec::new(), Vec::new()];
        gs.players[0].power_spent_this_turn = 0;
        gs.players[1].power_spent_this_turn = 0;
        gs.turns_taken[active.idx()] += 1;
        gs.players[0].draws_this_turn = 0;
        gs.players[1].draws_this_turn = 0;
        gs.enemy_choices_this_turn = [0, 0];
        gs.next_card_discounts = [Vec::new(), Vec::new()];
        gs.next_units_enter_ready = [0, 0];
        gs.friendly_unit_died_this_turn = [false, false];
        gs.friendly_gear_died_this_turn = [false, false];
        gs.discarded_this_turn = [false, false];
        gs.cards_burned_this_turn = [0, 0];
        gs.conquered_this_turn = [0, 0];
        gs.hold_points_this_turn = [0, 0];
        self.phase_beginning(active)?;
        if let Some(r) = self.result_now() {
            return Ok(Some(r));
        }
        self.recompute_passives()?;
        if !self.side_has_passive(active, "skip_draw_phase") {
            self.phase_draw(active)?;
        }
        if let Some(r) = self.result_now() {
            return Ok(Some(r));
        }
        self.start_of_main(active)?;
        self.recompute_passives()?;
        self.run_staged_showdowns()?;
        Ok(self.result_now())
    }

    /// py: _run_main_actions
    pub fn run_main_actions(&mut self) -> R<Option<GameResult>> {
        let ap = self.gs.active;
        let op = ap.other();
        let mut actions_this_turn = 0;
        loop {
            if let Some(r) = self.result_now() {
                return Ok(Some(r));
            }
            let cards_played = self.gs.cards_played_this_turn[ap.idx()];
            let act = match self.agent(ap) {
                None => Action::pass(),
                Some(a) => {
                    let act = a.borrow_mut().decide_action(self, ap, cards_played)?;
                    self.open_segment(ap, &act, cards_played);
                    act
                }
            };
            if act.kind == AKind::Pass {
                if self.gs.pending_move.is_some() {
                    self.flush_pending_move()?;
                    self.recompute_passives()?;
                    actions_this_turn += 1;
                    continue;
                }
                break;
            }
            let before = self.action_fingerprint(ap, op);
            let held = self.gs.pending_move;
            self.apply_action(ap, &act, cards_played)?;
            self.recompute_passives()?;
            actions_this_turn += 1;
            let ended_move = held.is_some() && self.gs.pending_move.is_none();
            if self.action_fingerprint(ap, op) == before && !ended_move {
                break;
            }
            if actions_this_turn > 200 {
                break;
            }
        }
        self.flush_pending_move()?;
        Ok(self.result_now())
    }

    /// py: _open_segment — a main-phase decision made: the journal starts again from it.
    pub fn open_segment(&mut self, side: Side, act: &Action, cards_played: i64) {
        if self.journal.is_some() {
            let mut gs = self.gs.clone();
            gs.rng.log = None;
            self.segment = Some(std::rc::Rc::new(Segment { gs, side, action: act.clone(), cards_played }));
            self.journal = Some(Vec::new());
        }
    }

    /// py: replay_segment — on a copy of `segment`'s game (its own loop, agents
    /// that answer from the journal): what the main loop does with that
    /// decision, up to the next one.
    pub fn replay_segment(&mut self) -> R<()> {
        let seg = self.segment.clone().expect("replay_segment without a segment");
        if seg.action.kind == AKind::Pass && self.gs.pending_move.is_none() {
            self.flush_pending_move()?;
            if self.victory().is_none() && self.end_turn()?.is_none() && self.gs.turn <= self.gs.max_turns {
                self.begin_turn()?;
            }
            return Ok(());
        }
        self.apply_action(seg.side, &seg.action, seg.cards_played)?;
        self.recompute_passives()
    }

    /// py: _end_turn
    pub fn end_turn(&mut self) -> R<Option<GameResult>> {
        self.flush_pending_move()?;
        self.run_staged_showdowns()?;
        let active = self.gs.active;
        self.phase_combat_and_conquer(active)?;
        if let Some(r) = self.result_now() {
            return Ok(Some(r));
        }
        self.gs.in_ending_phase = true;
        self.ending_step(active)?;
        if let Some(r) = self.result_now() {
            self.gs.in_ending_phase = false;
            return Ok(Some(r));
        }
        for u in self.all_units_in_play() {
            let unit = self.gs.unit_mut(u);
            unit.damage = 0;
            unit.clear_turn_end_bonuses();
            unit.stunned = false;
        }
        self.gs.players[0].empty_rune_pool();
        self.gs.players[1].empty_rune_pool();
        self.cleanup_hidden_cards()?;
        self.gs.in_ending_phase = false;
        if !self.gs.extra_turns.is_empty() {
            self.gs.active = self.gs.extra_turns.remove(0);
        } else {
            self.gs.active = active.other();
        }
        self.gs.turn += 1;
        Ok(None)
    }
}
