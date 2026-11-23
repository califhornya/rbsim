//! py: loop.py — HIDDEN keyword (§737): hide, facedown capacity, cleanup,
//! playing a facedown card.

use crate::game::*;
use crate::lp_phases::bf_extra;
use crate::model::*;
use crate::not_ported;
use crate::types::*;

impl Game {
    /// py: _hide_lanes
    pub fn hide_lanes(&mut self, side: Side) -> Vec<usize> {
        let mut out = Vec::new();
        for i in 0..self.gs.battlefields.len() {
            let ctl = self.gs.battlefields[i].control();
            if ctl == Some(side) && self.gs.battlefields[i].facedowns.len() < self.facedown_capacity(i) {
                out.push(i);
            }
        }
        out
    }

    /// py: _facedown_capacity
    pub fn facedown_capacity(&mut self, bf: usize) -> usize {
        let mut cap = 1;
        if let Some(c) = self.gs.battlefields[bf].card {
            if self.has_effect(c, "extra_facedown_slot") {
                cap += 1;
            }
        }
        if let Some(side) = self.gs.battlefields[bf].control() {
            cap += self.gs.battlefields[bf].gear[side.idx()]
                .iter()
                .filter(|&&dg| self.has_effect(self.gs.dgear[dg.i()].card, "extra_facedown_slot"))
                .count();
        }
        cap
    }

    /// py: _trim_facedowns
    pub fn trim_facedowns(&mut self, bf: usize) -> R<()> {
        let cap = self.facedown_capacity(bf);
        while self.gs.battlefields[bf].facedowns.len() > cap {
            let side = self.gs.battlefields[bf].control().unwrap_or(self.gs.battlefields[bf].facedowns.last().unwrap().owner);
            let opts: Vec<Opt> = self.gs.battlefields[bf].facedowns.iter().map(|f| Opt::Card(f.card)).collect();
            let base = opts.last().unwrap().clone();
            let src = self.gs.battlefields[bf].card;
            let got = self.choose("facedown_trash", side, &opts, base, src)?;
            let Opt::Card(card) = got else { unreachable!() };
            let i = self.gs.battlefields[bf].facedowns.iter().position(|f| f.card == card).unwrap();
            let fd = self.gs.battlefields[bf].facedowns.remove(i);
            self.put_in_trash(fd.owner, fd.card, false)?;
        }
        Ok(())
    }

    /// py: _hide_card(side, idx, lane); idx None = "champion"
    pub fn hide_card(&mut self, side: Side, idx: Option<i64>, lane: i64) -> R<bool> {
        let card = match idx {
            None => match self.hideable_champion(side) {
                Some(c) => c,
                None => return Ok(false),
            },
            Some(i) => {
                if i < 0 || i as usize >= self.gs.player(side).hand.len() {
                    return Ok(false);
                }
                self.gs.player(side).hand[i as usize]
            }
        };
        if !self.gs.has_keyword(card, "HIDDEN") {
            return Ok(false);
        }
        if lane < 0 || !self.hide_lanes(side).contains(&(lane as usize)) {
            return Ok(false);
        }
        if !self.can_hide_pay(side) {
            return Ok(false);
        }
        if self.gs.free_hide.get(&side) == Some(&self.gs.turn) {
        } else if self.can_pay_generic_power(side, 1) {
            self.pay_generic_power(side, 1)?;
        } else {
            let e = self.gs.player(side).energy() - 1;
            self.gs.player_mut(side).set_energy(e);
        }
        match idx {
            None => self.gs.champion_deployed[side.idx()] = true,
            Some(i) => {
                self.gs.player_mut(side).hand.remove(i as usize);
                let known = self.gs.player(side).hand_known();
                let kept: Vec<CardId> = known.into_iter().filter(|&c| !self.gs.has_keyword(c, "HIDDEN")).collect();
                self.gs.player_mut(side).hand_public = kept;
            }
        }
        let lane = lane as usize;
        let turn = self.gs.turn;
        self.gs.battlefields[lane].facedowns.push(Facedown { card, owner: side, turn_hidden: turn });
        if let Some(bc) = self.gs.battlefields[lane].card {
            self.resolve_triggered_effects(bc, "on_hide_here", lane, side, Some(bf_extra(lane)))?;
        }
        self.fire_units_trigger("on_hide", side, None, None, None)?;
        Ok(true)
    }

    /// py: _hideable_champion
    pub fn hideable_champion(&self, side: Side) -> Option<CardId> {
        let c = self.gs.champion[side.idx()]?;
        if !self.gs.champion_deployed[side.idx()] && self.gs.has_keyword(c, "HIDDEN") {
            Some(c)
        } else {
            None
        }
    }

    /// py: _can_hide_pay
    pub fn can_hide_pay(&self, side: Side) -> bool {
        let teemo = self.legend_with(side, "hide_for_energy", false).is_some();
        self.gs.free_hide.get(&side) == Some(&self.gs.turn)
            || self.can_pay_generic_power(side, 1)
            || (teemo && self.gs.player(side).energy() >= 1)
    }

    /// py: _cleanup_hidden_cards
    pub fn cleanup_hidden_cards(&mut self) -> R<()> {
        for i in 0..self.gs.battlefields.len() {
            // py: bf.control() inside the comprehension: noted only if there
            // are facedown cards here.
            if self.gs.battlefields[i].facedowns.is_empty() {
                continue;
            }
            let ctl = self.gs.battlefields[i].control();
            let gone: Vec<Facedown> =
                self.gs.battlefields[i].facedowns.iter().filter(|fd| ctl != Some(fd.owner)).cloned().collect();
            for fd in gone {
                self.put_in_trash(fd.owner, fd.card, false)?;
                let l = &mut self.gs.battlefields[i].facedowns;
                if let Some(p) = l.iter().position(|x| *x == fd) {
                    l.remove(p);
                }
            }
        }
        Ok(())
    }

    /// py: _hidden_playable -> [(battlefield, slot)]
    pub fn hidden_playable(&mut self, side: Side) -> R<Vec<(usize, usize)>> {
        let mut out = Vec::new();
        for i in 0..self.gs.battlefields.len() {
            if self.gs.battlefields[i]
                .units_for(side.other())
                .iter()
                .any(|&u| self.has_effect(self.gs.ucard(u), "no_enemy_reveals_here"))
            {
                continue;
            }
            for slot in 0..self.gs.battlefields[i].facedowns.len() {
                let fd = self.gs.battlefields[i].facedowns[slot].clone();
                if fd.owner != side || self.gs.turn <= fd.turn_hidden {
                    continue;
                }
                if self.gs.is_spell(fd.card) {
                    self.gs.card_mut(fd.card).hidden_bf = Some(i);
                    let ok = self.spell_has_targets(fd.card, side, i);
                    self.gs.card_mut(fd.card).hidden_bf = None;
                    if !ok? {
                        continue;
                    }
                }
                out.push((i, slot));
            }
        }
        Ok(out)
    }

    /// py: _play_from_hidden
    pub fn play_from_hidden(&mut self, side: Side, lane: usize, slot: usize) -> R<bool> {
        if !self.hidden_playable(side)?.contains(&(lane, slot)) {
            return Ok(false);
        }
        let fd = self.gs.battlefields[lane].facedowns.remove(slot);
        let card = fd.card;
        self.gs.card_mut(card).hidden_bf = Some(lane);
        let r: R<()> = (|| {
            if self.gs.is_spell(card) {
                self.spell_played(card, side, "facedown")?;
                self.put_on_chain(ChainItem {
                    player: side,
                    card,
                    bf_idx: lane,
                    declared: None,
                    choices_noted: false,
                    owner: None,
                    ability: None,
                })?;
                self.run_chain(side)?;
            } else if self.gs.is_gear_card(card) {
                self.play_gear(card, side, lane as i64, "facedown")?;
            } else {
                self.play_unit(card, side, Some(lane), "facedown")?;
            }
            Ok(())
        })();
        self.gs.card_mut(card).hidden_bf = None;
        r?;
        Ok(true)
    }

    /// py: _set_battlefield_card / _replace_battlefield (not in EK)
    pub fn replace_battlefield(&mut self, _bf: usize, token_name: &str) -> R<()> {
        not_ported!("_replace_battlefield", "battlefield token {token_name}")
    }
}
