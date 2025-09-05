# Exploratory World-Building Mode

This document describes the changes introduced on branch `feat/world-building-tools` to support an exploratory, tool-like world-building flow where the model is encouraged to invent (hallucinate) new entities and have them persisted to the world state.

## Overview

- Adds a new prompt (`prompt_world_update_exploratory`) that:
  - Encourages creative invention of items, locations, and characters.
  - Optionally incorporates background text and a starting scenario.
  - Requires a strict, parseable update format.
- Extends the world engine to parse these new world-building updates before applying standard movement/unblocking/location changes.
- Adds optional runtime flags and file inputs to seed the session.

## How to Enable

```
export EXPLORATORY_MODE=1
# Optional background text used as a creative seed:
echo "A dusty spaceport on the desert planet Aridia..." > source_material.txt
# Optional starting scenario seed:
export STARTING_SCENARIO="You arrive at sunset, heat shimmering on the landing pads."
python main.py
```

Environment variables and files:
- `EXPLORATORY_MODE=1` enables this mode.
- `SOURCE_MATERIAL` (path): defaults to `source_material.txt` if present.
- `STARTING_SCENARIO` (string): short seed for the first turns.

## Output Format (Strict)

The model is asked to output updates using the following bullet structure. Multiple entities can be listed in a bullet, separated by commas. Angled brackets denote entity names; descriptions are in quotes.

- `New item: <Name> description: "Short description" location: <Inventory|Location|Character>`
- `New character: <Name> description: "Short description" location: <Location>`
- `New location: <Name> description: "Short description"`
- `Connect locations: <A> <-> <B>, <C> <-> <D>`
- `Moved object: <object> now is in <new_location>`
- `Blocked passages now available: <now_reachable_location>`
- `Your location changed: <new_location>`
- Final single-line narration as: `#<short sentence>#`

Notes:
- Use `None` if a category has no updates.
- Only use `<...>` for names (Items, Locations, Characters). Keep descriptions in quotes.
- If the player moves to a newly invented location, emit `New location` before `Your location changed`.

## Parser Behavior

World-building updates are applied first so subsequent bullets can reference new entities. Then the original updates run.

New helper methods:
- `World._ensure_location(name, description?)`: creates or returns an existing `Location`.
- `World._ensure_character(name, description?, location_name)`: creates or returns a `Character` at a location (created if needed).
- `World._ensure_item(name, description?)`: creates or returns an `Item`.

New parsing methods:
- `parse_new_locations`: parses `New location:` lines (comma-separated) and adds locations.
- `parse_new_characters`: parses `New character:` lines and adds characters in a location.
- `parse_new_items`: parses `New item:` lines and places the item in a `Location`, `Character`, or `Inventory`.
- `parse_connect_locations`: parses `Connect locations:` (pairs) and links them bidirectionally.

Then the original methods run:
- `parse_moved_objects`
- `parse_blocked_passages`
- `parse_location_change`

Error handling:
- Parsers are defensive; on malformed fragments they print the exception and proceed.
- Unknown destinations in `New item` create a new `Location` implicitly to keep the world consistent.

## Example Output

```
- New location: <Spaceport Office> description: "A cramped room with flickering lights"
- New character: <Dockmaster Rhea> description: "A gruff official with a cybernetic eye" location: <Spaceport Office>
- New item: <Ancient Coin> description: "Tarnished bronze disc with strange sigils" location: <Inventory>
- Connect locations: <Landing Pad> <-> <Spaceport Office>
- Moved object: <Flashlight> now is in <Inventory>
- Blocked passages now available: <Maintenance Tunnel>
- Your location changed: <Spaceport Office>
#The office smells of ozone as you pocket the coin.#
```

## Files Touched

- `prompts.py`:
  - Added `prompt_world_update_exploratory` with strict format and optional background/scenario input.
- `world.py`:
  - Added `_ensure_location`, `_ensure_character`, `_ensure_item`.
  - Added `parse_new_locations`, `parse_new_characters`, `parse_new_items`, `parse_connect_locations`.
  - Updated `parse_updates` to apply world-building first, then existing updates.
- `main.py`:
  - Added `EXPLORATORY_MODE` flow selecting the exploratory prompt.
  - Loads `SOURCE_MATERIAL` file (if present) and `STARTING_SCENARIO`.
- `README.md`:
  - Added a short “Exploratory world-building mode” section with usage.
- `.gitignore`:
  - Now ignores `.env`, `API_key`, `__pycache__/`, `*.pyc`, `source_material.txt`.

## Limitations and Next Steps

- Persistence: World exists in-memory only. Consider JSON save/load to persist across sessions.
- Blocked-passage creation: Currently supports unblocking; adding a `Block passage:` creation format (with obstacles) would complete the loop.
- Validation: Could add a minimal schema check and corrective hinting if the model’s output deviates from format.
- Safety: Keep `.env` and `API_key` out of version control (already ignored).

