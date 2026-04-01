# Morning Report: 2026-04-01

## Executive Summary

**Verdict**: Significant issues
- Features completed: 6/8
- Features deferred: 1 (questions need answers)
- Features failed: 1 (paused, need investigation)
- Rounds completed: 3
- Duration: 0h 36m

## Completed Features

### wild-light

#### node-reference-cleanup-erase-freed-players-from-autoload-dicts

**Key files changed:**
- CLAUDE.md

**Cost**: $4.02

**How to try:**
1. **Lint and format**: Run `gdlint autoloads/ scripts/core/` and `gdformat autoloads/ scripts/core/` — both pass with no errors.

2. **Unit tests**: Run the full test suite:
   ```
   godot --headless -s addons/gdUnit4/bin/GdUnitCmdTool.gd --ignoreHeadlessMode -a res://tests
   ```
   All existing snapshot manager tests must pass. The new `test_serialize_skips_freed_player_node` test must also pass.

3. **Launch probe**: Run `uv run scripts/tools/validate_project.py` — all gates pass.

4. **Game probe**: Run `uv run scripts/tools/run_game_probe.py --expect-game-state=PLAYING --expect-wave=1 --expect-enemies-gt=0 --expect-no-peer` — game starts and reaches wave 1 with enemies.

5. **Multiplayer probe** (conditional — `game_manager.gd` and `snapshot_manager.gd` are in the trigger list): Confirm no new `@rpc` violations introduced.

6. **Manual inspection checklist**:
   - `AudioManager._players` has a `player_disconnected` connection in `_connect_combat_signals()`.
   - `CameraShake._ready()` connects to both `player_disconnected` and `returned_to_menu`.
   - `SnapshotManager.serialize()` loop body contains `is_instance_valid()` guard before property access.
   - `CLAUDE.md` contains `### Node Reference Cleanup` subsection.

#### type-all-dictionary-declarations (backlog #097)

**Key files changed:**
- .pre-commit-config.yaml
- autoloads/audio_manager.gd
- autoloads/game_manager.gd
- autoloads/network_manager.gd
- autoloads/save_manager.gd

**Cost**: $4.09

**How to try:**
The feature is complete when all of the following pass:

1. **Grep AC1** — member var check:
   `grep -rP 'var\s+\w+\s*:\s*Dictionary\s*=' autoloads/` returns zero matches (all
   bare `Dictionary` member vars have been typed).

2. **Grep AC2** — function param check:
   `grep -rP '\(.*:\s*Dictionary\s*[,)]' autoloads/` returns zero matches except for
   intentionally-untyped RPC params, each of which must have a `# untyped: ...` inline
   comment explaining the Godot limitation.

3. **Grep AC3** — return type check:
   `grep -rP '->\s*Dictionary\s*:' autoloads/` returns zero matches.

4. **Launch probe** — `uv run scripts/tools/validate_project.py` exits 0 (no parse errors
   or GDScript warnings introduced by the typed declarations).

5. **Test suite** — full test suite passes with no regressions.

6. **Game probe** — `uv run scripts/tools/run_game_probe.py --expect-game-state=PLAYING
   --expect-wave=1 --expect-enemies-gt=0 --expect-no-peer` passes (typed declarations
   cause no runtime failures at external data boundaries).

### Expected boundary decisions (summary)

| Site | Declared type | Reason |
|------|--------------|--------|
| `_levels` in audio_manager | `Dictionary[String, Variant]` | JSON parse returns Variant; widest safe type |
| `load_game` return in save_manager | `Dictionary[String, Variant]` | JSON parse boundary |
| `init_result` in network_manager | `Dictionary` (untyped fallback) | `steam.call()` returns Variant |
| `_register_player(data)` param | `Dictionary` (untyped) | RPC deserialization |
| `_send_player_info(info)` param | `Dictionary` (untyped) | RPC deserialization |
| `restore(snapshot)` param | `Dictionary` (untyped) | RPC deserialization via `_receive_snapshot` |
| `_receive_snapshot(snapshot)` param | `Dictionary` (untyped) | RPC deserialization |
| `restore_for_migration(snapshot, ...)` snapshot param | `Dictionary` (untyped) | RPC origin |
| `restore_for_migration(..., peer_steam_id_map)` | `Dictionary[int, int]` | Passed internally |
| Inner dicts in `player_info`, `steam_id_to_entry` | `Dictionary` (untyped inner) | Godot doesn't support nested typed dicts |

#### cache-player-array-eliminate-per-frame-group-lookup (backlog #098)

**Key files changed:**
- autoloads/event_bus.gd
- autoloads/game_manager.gd
- scripts/entities/simple_enemy.gd

**Cost**: $1.49

**How to try:**
1. Run `gdlint autoloads/event_bus.gd autoloads/game_manager.gd scripts/entities/simple_enemy.gd` — all files must pass with no new errors.
2. Confirm `get_nodes_in_group` does not appear in `scripts/entities/simple_enemy.gd` or `scripts/entities/simple_player.gd`.
3. Confirm `enemies` dict, `_on_enemy_spawned`, `_on_enemy_killed`, and `get_all_enemies()` are present in `autoloads/game_manager.gd`.
4. Confirm `EventBus.enemy_spawned.emit(self)` is present in `simple_enemy.gd` `_ready()`.
5. Run `uv run scripts/tools/validate_project.py` — must exit 0.
6. Run `uv run scripts/tools/run_game_probe.py --expect-game-state=PLAYING --expect-wave=1 --expect-enemies-gt=0 --expect-no-peer` — must pass all assertions, confirming enemies still spawn and move correctly.
7. Run the full GdUnit4 test suite (`godot --headless -s addons/gdUnit4/bin/GdUnitCmdTool.gd --ignoreHeadlessMode -a res://tests`) — all tests must pass, including `test_gameplay.gd` enemy movement and combat tests.

#### move-detection-ranges-to-constantsgd

**Key files changed:**
- scripts/core/constants.gd
- tests/unit/test_constants_detection_ranges.gd

**Cost**: $2.07

**How to try:**
1. After Task 1: Read `scripts/core/constants.gd` and confirm the three constants are present with correct values and placement (after Gameplay, before Physics layers).
2. After Task 2: Read `scripts/entities/simple_enemy.gd` and confirm `CONTACT_RANGE` local const is gone and the usage site references `Constants.ENEMY_CONTACT_RANGE`. Run `gdlint` on the file.
3. After Task 3: Run the new test file in isolation to confirm all 6 assertions pass.
4. Full suite: Run `uv run scripts/tools/validate_project.py` to confirm no parse or lint errors across the project.
5. Search for remaining raw literals: Grep `scripts/entities/` for `16\.0` and `32\.0` to confirm no detection-range literals remain in GDScript entity files (the only surviving `16.0` should be `TILE_SIZE`-adjacent or unrelated constants like `PIXEL_SCALE`).

#### switch-spawn-scene-loading-to-preload (backlog #100)

**Key files changed:**
- scripts/core/main.gd

**Cost**: $0.78

**How to try:**
1. Run `gdlint scripts/core/main.gd` — must exit 0 with no style warnings
2. Run `uv run scripts/tools/validate_project.py` — launch probe must exit 0
3. Run `uv run scripts/tools/run_game_probe.py --expect-game-state=PLAYING --expect-wave=1 --expect-enemies-gt=0 --expect-no-peer` — game probe must exit 0 confirming enemies and player spawn correctly
4. Run `godot --headless -s addons/gdUnit4/bin/GdUnitCmdTool.gd --ignoreHeadlessMode -a res://tests` — full test suite must exit 0

#### arena-bounds-tests-verify-player-enemy-containment

**Key files changed:**
- tests/integration/test_arena_containment.gd

**Cost**: $3.98

**How to try:**
1. **Source reading first** (Task 1): Exact node paths for walls and entity collision properties must be verified before writing tests. Incorrect node paths silently pass (node not found returns null).

2. **Bitwise collision checks** (Task 2): Use `& LAYER_WORLD != 0` — not equality — so future mask additions don't break tests.

3. **Direct velocity for enemy** (Task 3): Do not use `move_toward` or AI chase. Set velocity directly to ensure deterministic wall approach direction.

4. **Frame budget** (Task 3): 80 frames is conservative. If tests are slow, reduce to 60. If the entity doesn't reach the wall in 60–80 frames, the test will still pass (entity won't have exited), but won't cover the containment behavior. Pick a starting position close to the wall.

5. **Regression gate**: All 5 tests fail against pre-078 collision defaults. This is the key acceptance criterion.

## Deferred Questions (0)

No questions were deferred — all ambiguities were resolved by the pipeline.

## Failed Features (1)

### fix-game-over-screen-escape-doesnt-return-to-menu-re-enables-e-key-restart: completed with no new commits — check pipeline-events.log task_output and task_git_state events (branch: pipeline/fix-game-over-screen-escape-doesnt-return-to-menu-re-enables-e-key-restart)
- Retry attempts: 0
- Circuit breaker: not triggered
- Learnings: `lifecycle/fix-game-over-screen-escape-doesnt-return-to-menu-re-enables-e-key-restart/learnings/progress.txt`
- **Suggested next step**: Review learnings, retry or investigate

## New Backlog Items

- **#122** [feature] Retry deferred: backlog-status-reconciliation-fix-archived-complete-discrepancies — deferred
- **#123** [chore] Follow up: fix-game-over-screen-escape-doesnt-return-to-menu-re-enables-e-key-restart — failed

## What to Do Next

1. [ ] Try completed features: node-reference-cleanup-erase-freed-players-from-autoload-dicts, type-all-dictionary-declarations, cache-player-array-eliminate-per-frame-group-lookup, move-detection-ranges-to-constantsgd, switch-spawn-scene-loading-to-preload, arena-bounds-tests-verify-player-enemy-containment
2. [ ] Investigate 1 failed feature
3. [ ] Run integration tests

## Run Statistics

- Rounds completed: 3
- Per-round timing: Round 1: 11m, Round 2: 11m, Round 3: 8m
- Circuit breaker activations: 0
- Total features processed: 8
- Total session cost: $18.87
