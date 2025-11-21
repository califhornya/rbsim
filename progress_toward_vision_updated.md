# PROGRESS_TOWARD_VISION (Updated)

This document captures the current project status and all work required to reach the **next checkpoint**. It merges the previous assessment with new information: **the full Riftbound card pool now exists**, but *is not yet integrated into the simulator*.

---

## 1. Vision Alignment (from `1.txt` and `answer-to-1.txt`)
The simulator's purpose remains:

- An **AI playground** for large-scale headless match simulations.
- Deep **data logging** for analytics, meta exploration, and Codex training.
- Clean modular architecture separating **engine**, **AI**, and **DB** layers.
- No GUI, no human-play interface.

This alignment is unchanged.

---

## 2. What Is Fully Implemented
The following features from the vision are complete:

### **Simulation Engine**
- Automated multi-match engine (CLI-driven).
- Deterministic RNG with seeding.
- Multi-phase turn system.
- Hold/Conquer scoring system.
- Might-based combat (simplified but functional).

### **Data Logging & Storage**
- SQLite database with ORM models for:
  - Games, Turns, Boards, Plays
  - Decks, Draws, Hands
- JSON serialization of card and unit states.
- Analytics helpers.

### **Card Model Architecture**
- Unified dataclass hierarchy: Unit, Spell, Gear, Rune, Legend, Battlefield.
- CardSpec + factory instantiation.
- Effect registry system for dynamic effect execution.

### **AI System**
- Pluggable agent interface.
- SimpleAggro and SimpleControl implemented.

### **Code Structure**
- Clean modular package layout.
- DB isolated in data layer.
- GameLoop isolated in core.
- No one-class-per-card design.

---

## 3. New Status: Card Pool
**The complete Riftbound card pool has been added as `master_cards.json`.**

However:
- **The simulator does not use it yet.**
- No loading, parsing, or rule-text translation exists.
- Decks still use hardcoded test cards.

So the card pool is available, but **unintegrated**.

---

## 4. Outstanding Gaps (Updated)
Below are all features not yet implemented, grouped and prioritized.

### **4.1 Card Integration (High Priority)**
- Build importer to convert `master_cards.json` → CardSpec.
- Map JSON structure (type, cost, domain, rules_text) to simulator format.
- Handle Champion/Token types.
- Build deck JSON format + loader.
- Replace hardcoded decks with real deck files.

### **4.2 Keyword System (High Priority)**
The JSON contains many keywords not implemented:
- HIDDEN, REACTION, ACTION
- SHIELD, TANK, DEFLECT
- GANKING, TEMPORARY, VISION
- DEATHKNELL, LEGION, ASSAULT
- ACCELERATE (partial implementation exists)

Need keyword registry + mechanics.

### **4.3 Timing & Stack System (High Priority)**
Required for most keywords:
- Chain system
- Showdown windows
- Reaction timing
- Priority flow
- Card resolution order

### **4.4 Combat System Expansion (Medium Priority)**
- Stuns
- Shield/Tank ordering
- Mighty state checks
- Attack vs defense bonuses
- Cleanup timing (damage clearing, buffs expiring)

### **4.5 Zone System (Medium Priority)**
Full rules need:
- Base
- Battlefield
- Trash
- Banish
- Facedown
- Champion Zone

### **4.6 Deck & Card Metadata (Medium Priority)**
- Card sets, rarity, variant IDs (mostly not needed for AI, but may matter for meta simulation).

### **4.7 Advanced AI Improvements (Medium Priority)**
- Battlefield evaluation functions.
- Spell targeting logic.
- Rune efficiency heuristics.
- Multi-turn planning.

### **4.8 Analytics & Meta Tools (Medium Priority)**
- Winrate curves
- Card performance impact
- Deck matchup matrices
- CSV export utilities

### **4.9 DB Schema Versioning (Low Priority)**
- Migration tools for future schema changes.

---

## 5. Next Checkpoint Goals (Single Unified Plan)
This section outlines everything required from **now until the next milestone**.

### **Step 1 — Integrate the Card Pool**
- Write card importer.
- Build effect/keyword parsing foundation.
- Create deck JSON format and loader.
- Verify cards instantiate correctly.

### **Step 2 — Implement Keyword Framework**
Minimal set needed for real gameplay:
- ACCELERATE
- LEGION
- HIDDEN
- SHIELD
- ASSAULT
- TANK
- VISION
- REACTION
- GANKING

### **Step 3 — Add Timing/Stack System**
- Chain queue
- Reaction and action windows
- Showdown phase handling
- Priority passing

### **Step 4 — Expand Combat Model**
- Stun
- Defender bonuses
- Damage replacement effects

### **Step 5 — Build Real Decks**
- Populate `/data/decks/` with real decks used for simulations.
- Allow CLI to select decks.

### **Step 6 — Update AI**
- Make AI keyword-aware.
- Basic targeting logic (kill priority, stun value, etc.).
- Battlefield strength estimation.

### **Step 7 — Analytics Tools**
- Export reports (CSV)
- Simple meta visualization helpers
- Per-card winrate impact

---

## 6. Summary
- **Card pool exists but is not integrated.**
- Engine architecture is strong and aligned with the vision.
- The next checkpoint is all about **connecting real cards to real rules**.
- The work focuses on rule fidelity (keywords, stack, timing) and real deck usage.

This document defines the exact tasks required to reach that next project milestone.

