# PROGRESS_TOWARD_VISION.md  
**Alignment of Riftbound Simulator with Original AI-Simulator Vision**

---

## 1. Purpose & Context

This document tracks the evolution of the **Riftbound Simulator** from the original simulator concept (as described in `1.txt` and `answer-to-1.txt`) to the current, integrated version implementing **Real Riftbound Mechanics**.

The goal: assess how far the current system fulfills the original AI simulation vision—*automated matches, database logging, card abstraction, and modular AIs*—and identify the remaining work before final Codex ingestion.

---

## 2. Core Feature Parity

| Vision Feature (from `1.txt`) | Current Riftbound Implementation | Status |
|-------------------------------|----------------------------------|---------|
| **Automated match engine** capable of thousands of runs | `GameLoop`, `main.py` simulate N matches via CLI (`--games`, `--seed`) | ✅ |
| **Deck-specific AIs** (Burn vs Delver analogy) | Agents: `SimpleAggro`, `SimpleControl` selectable per side | ✅ |
| **SQLite database logging** with per-game analytics | Full ORM via SQLAlchemy (`schema.py`, `writer.py`, `session.py`) | ✅ |
| **Turn-level and card-level tracking** | Tables for Games, Turns, Decks, Draws, Hands, Boards, Plays | ✅ |
| **Randomized reproducibility** | Deterministic `Random(seed)` and per-game RNG splitting | ✅ |
| **Data serialization of cards** | `_card_to_dict` / `_unit_to_dict` JSON serializers | ✅ |
| **Dynamic effect handling** | `effects.py` registry + `EffectSpec` system | ✅ |
| **Multi-category card model** | Unified `Card` dataclass + typed subclasses (Unit, Spell, Gear, Rune, Legend, Battlefield) | ✅ |
| **Scoring and game resolution** | `Battlefield` + `GameLoop` implement Hold/Conquer VP rules | ✅ |
| **Runes / Energy channeling** | Implemented in `Player` with unlock + channel phases | ✅ |
| **Multi-phase turn sequence** | Awaken → Beginning → Channel → Draw → Action → Combat → End | ✅ |
| **Configurable simulation parameters** | CLI options for energy cap, runes, victory score, verbosity | ✅ |
| **Card registry & instantiation from JSON** | `cards_registry.py` dynamically loads JSON specs | ✅ |
| **Code modularization** | Full separation: `core/`, `data/`, `ai/` | ✅ |
| **Factory instead of per-card class explosion** | `CardSpec.instantiate()` replaces manual subclassing | ✅ |

---

## 3. Engineering Design Alignment (per `answer-to-1.txt`)

| Recommendation | Implementation | Status |
|----------------|----------------|---------|
| **“Separate code in modules”** | Clear package split: `riftbound.core`, `riftbound.data`, `riftbound.ai` | ✅ |
| **“Use ORM instead of raw SQL”** | SQLAlchemy ORM with declarative Base | ✅ |
| **“Encapsulate DB separately”** | `writer.py` and `session.py` isolate persistence logic | ✅ |
| **“Simulator shouldn’t do everything”** | Game orchestration isolated in `loop.py`; DB in data layer | ✅ |
| **“Avoid one-class-per-card”** | Replaced by `CardSpec` + factory pattern | ✅ |
| **“Don’t reinvent the wheel”** | Modern ORM, `typer` CLI, `rich` output, JSON schemas | ✅ |
| **Code readability / extensibility** | Dataclasses, typing, minimal inheritance | ✅ |

---

## 4. Outstanding Gaps

| Area | Description | Priority |
|------|--------------|----------|
| **Card pool population** | Only minimal test cards (`Bolt`, `Stalwart Recruit`); expand JSON registry with full Riftbound set. | HIGH |
| **Decklists from JSON** | Decks currently hardcoded; need proper deck definitions linked to Legends & Domains. | HIGH |
| **Advanced analytics layer** | Database ready, but no SQL / notebook utilities for queries (e.g. average win turn, card performance). | MEDIUM |
| **Extended AI logic** | Heuristics basic; add adaptive decision making per battlefield, hand evaluation, and rune efficiency. | MEDIUM |
| **Multi-match orchestration** | Add tournament runner (cross-deck matrix simulation) for meta-analysis. | MEDIUM |
| **Effect coverage expansion** | Registry supports `deal_damage`, `grant_might`; add all canonical Riftbound keywords (Stun, Heal, Buff, etc.). | MEDIUM |
| **Data validation / schema versioning** | Version tracking exists (`DB_VERSION=2`); migrate support still to implement. | LOW |
| **Codex integration hooks** | Export simplified JSON schemas for Codex ingestion (deck, match, turn snapshots). | LOW |

---

## 5. Next Steps

**Short-term (Codex integration readiness)**  
- Populate `data/cards/` with 1-unit, 1-spell, 1-gear example JSON files (canonical format).  
- Create `data/decks/` with legend/domain-compliant decklists.  
- Write lightweight analytics script to query SQLite results and export CSV summaries.  

**Mid-term**  
- Expand AI module with adaptive strategies and battlefield prioritization.  
- Integrate extended Effect handlers and keyword registry from rulebook (`Riftbound Core Rules v1.1`).  
- Implement in-game triggers for passive and triggered abilities (using `EffectContext`).  

**Long-term**  
- Add multi-deck tournament orchestration and balance evaluation.  
- Provide visualization and meta dashboards (e.g., victory curve, card efficiency).  
- Enable Codex auto-training from stored simulations.

---

**Summary:**  
The Riftbound Simulator now achieves **full architectural parity** and exceeds the original *Magic-AI simulator* vision.  
Remaining work lies in **content scale (cards/decks)** and **analytical tooling**, not in simulation fidelity.

