"""Implement the main loop for the PAYADOR approach, described in Fig.3 of the paper.

The main steps in the loop are:
- Describe the ficional world in simple sentences
- Get the player input
- Prompt a model to predict the outcomes in the world, after the actions described by the player.
"""

import re
import sys
import os
import json
import argparse

import example_worlds
from models import GeminiModel, OpenRouterModel
from prompts import (
    prompt_narrate_current_scene,
    prompt_world_update,
    prompt_world_update_exploratory,
    prompt_bootstrap_from_context,
)
from player_agent import PlayerAgent

parser = argparse.ArgumentParser(description="PAYADOR interactive storytelling")
parser.add_argument("world", nargs="?", default="1", help="World id (default: 1; try 'blank' for an empty world)")
parser.add_argument("--explore", action="store_true", help="Enable exploratory world-building mode (overrides config)")
parser.add_argument("--config", help="Path to JSON config with settings and seeds (default: config.json)")
parser.add_argument("--auto", action="store_true", help="Enable autonomous player-agent to propose actions")
args = parser.parse_args()

"""Load config first so we can use it to set runtime behavior."""
cfg_path = args.config if args.config else ("config.json" if os.path.exists("config.json") else None)
cfg = {}

def _load_json_with_comments(path: str) -> dict:
    """Load JSON allowing //, # and /* */ comments by stripping them first."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        # Remove block comments /* ... */
        raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
        # Remove line comments starting with // or #
        raw = re.sub(r"^\s*//.*$", "", raw, flags=re.M)
        raw = re.sub(r"^\s*#.*$", "", raw, flags=re.M)
        # Remove trailing commas before } or ] to tolerate JSON with trailing commas
        raw = re.sub(r",\s*(}\s*)", r"\1", raw)
        raw = re.sub(r",\s*(\]\s*)", r"\1", raw)
        return json.loads(raw) if raw.strip() else {}
    except Exception as e:
        raise e

if cfg_path and os.path.exists(cfg_path):
    try:
        cfg = _load_json_with_comments(cfg_path)
    except Exception as e:
        print(f"Warning: Could not load config '{cfg_path}': {e}")
        cfg = {}

def _prune_placeholder_location(
    world,
    *,
    placeholder_name: str = "Starting Point",
    fallback_locations: list[str] | None = None,
    force: bool = False,
) -> None:
    try:
        sp = world.locations.get(placeholder_name)
        if not sp:
            return
        # If the player is still at the placeholder, optionally relocate first
        if world.player.location is sp and force:
            target = None
            # Prefer provided fallbacks in order
            for name in (fallback_locations or []):
                if name in world.locations and world.locations[name] is not sp:
                    target = world.locations[name]
                    break
            # Otherwise pick any other known location
            if target is None:
                for loc in world.locations.values():
                    if loc is not sp:
                        target = loc
                        break
            if target is not None:
                world.player.location = target
            else:
                # No alternative: keep placeholder for now
                return
        if world.player.location is sp:
            return
        # Move any NPCs off the placeholder to the player's current location
        for ch in list(world.characters.values()):
            if ch.location is sp:
                ch.location = world.player.location
        # Remove connections and blocked references to the placeholder
        for loc in list(world.locations.values()):
            if sp in getattr(loc, 'connecting_locations', []):
                loc.connecting_locations = [l for l in loc.connecting_locations if l is not sp]
            if placeholder_name in getattr(loc, 'blocked_locations', {}):
                try:
                    del loc.blocked_locations[placeholder_name]
                except Exception:
                    pass
        # Finally remove the placeholder location from the world registry
        try:
            del world.locations[placeholder_name]
        except Exception:
            pass
    except Exception:
        # Non-fatal; pruning is best-effort
        pass

def _apply_player_config(
    world,
    player_cfg: dict | None,
    *,
    apply_location: bool = False,
    apply_inventory: bool = False,
) -> None:
    """Apply player configuration to the current world.

    - Always applies name/description if present.
    - Optionally applies location and inventory (controlled by flags).
    """
    if not player_cfg:
        return
    try:
        name = player_cfg.get("name")
        if isinstance(name, str) and name.strip():
            world.player.name = name.strip()

        descs = player_cfg.get("descriptions")
        if isinstance(descs, list) and all(isinstance(d, str) for d in descs):
            world.player.descriptions = descs

        if apply_location:
            loc_name = player_cfg.get("start_location")
            if isinstance(loc_name, str) and loc_name.strip():
                loc_desc = player_cfg.get("start_location_description")
                # Create location if missing (default True)
                create_missing = bool(player_cfg.get("create_location_if_missing", True))
                if loc_name in world.locations:
                    world.player.location = world.locations[loc_name]
                elif create_missing:
                    try:
                        # Use ensure helper if available
                        loc = world._ensure_location(loc_name, loc_desc)  # type: ignore[attr-defined]
                    except Exception:
                        from world import Location
                        loc = Location(loc_name, [loc_desc] if loc_desc else ["An unspecified location created from config."])
                        world.add_location(loc)
                    world.player.location = loc

        if apply_inventory:
            items = player_cfg.get("inventory")
            inv_desc_map = player_cfg.get("inventory_descriptions", {}) or {}
            if isinstance(items, list):
                for item_name in items:
                    if not isinstance(item_name, str) or not item_name.strip():
                        continue
                    iname = item_name.strip()
                    try:
                        item = world.items.get(iname)
                        if not item:
                            try:
                                item = world._ensure_item(iname, inv_desc_map.get(iname))  # type: ignore[attr-defined]
                            except Exception:
                                from world import Item
                                item = Item(iname, [inv_desc_map.get(iname) or "An object from config."])
                                world.add_item(item)
                        # Remove from any holder/location
                        for ch in list(world.characters.values()):
                            if item in ch.inventory:
                                ch.inventory = [i for i in ch.inventory if i is not item]
                        for loc in list(world.locations.values()):
                            if item in loc.items:
                                loc.items = [i for i in loc.items if i is not item]
                        if item not in world.player.inventory:
                            world.player.inventory.append(item)
                    except Exception:
                        continue
    except Exception:
        # Non-fatal
        pass

# Instantiate the world (config can override)
world_id = str(cfg.get("world", args.world)) if isinstance(cfg, dict) else args.world
world = example_worlds.get_world(world_id)

# Initialize the model using environment variables (.env supported)
provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
if provider == "openrouter":
    model = OpenRouterModel()
else:
    model = GeminiModel()

# Welcome the user
print ("""
PAYADOR is an approach to tackle the world-update problem in Interactive Storytelling.
This proof of concept is intended to ease research on the aforementioned problem and other related tasks. 

The system will print the current 🌎 World state 🌍 and a possible 📖 narration 📖 for it.
Then you will be asked to enter some action(s), and the system will try to predict the outcomes. 

Enter "q" to quit.
""")

# Startup summary to make modes clear
try:
    print(f"Mode: world={world_id}, explore={'ON' if bool(cfg.get('explore', False) or '--explore' in sys.argv) else 'OFF'}, auto={'ON' if ('--auto' in sys.argv or bool(cfg.get('auto', False))) else 'OFF'}")
except Exception:
    pass

last_player_position = None
last_scene_narration = None

# Exploratory mode setting: CLI flag overrides config's `explore` boolean
exploratory_mode = bool(args.explore) or bool(cfg.get("explore", False))
source_material = None
starting_scenario = None

# Resolve seeds from config
try:
    src_path = cfg.get("source_material_path")
    if src_path and os.path.exists(src_path):
        with open(src_path, "r", encoding="utf-8") as f:
            source_material = f.read()
    elif "source_material_text" in cfg and isinstance(cfg.get("source_material_text"), str):
        source_material = cfg.get("source_material_text")
    elif os.path.exists("source_material.txt"):
        # Convenience fallback when no config provided
        with open("source_material.txt", "r", encoding="utf-8") as f:
            source_material = f.read()
except Exception:
    source_material = None
starting_scenario = cfg.get("starting_scenario") if isinstance(cfg, dict) else None
player_cfg = cfg.get("player") if isinstance(cfg, dict) else None

# Pass helpful toggles to the world engine
try:
    # Enable frictionless movement for invented locations when exploring
    world.auto_connect_on_move = bool(exploratory_mode)
except Exception:
    pass

# Player-agent configuration
agent_cfg = cfg.get("player_agent", {}) if isinstance(cfg, dict) else {}
auto_mode = bool(args.auto) or bool(cfg.get("auto", False))
player_agent = None
if auto_mode:
    default_system = (
        "You are an adventurous, curious explorer. Make practical, in-character decisions that push the scene forward "
        "while staying consistent with the current world. Avoid meta commentary."
    )
    system_prompt = agent_cfg.get("system_prompt", default_system)
    history = agent_cfg.get("history", [])
    style_hint = agent_cfg.get("style_hint")
    player_agent = PlayerAgent(model, system_prompt=system_prompt, history=history, style_hint=style_hint)

# Optional: load saved world state
world_state_path = cfg.get("world_state_path") or cfg.get("state_path")
autosave = bool(cfg.get("autosave", bool(world_state_path)))
skip_load_on_blank = bool(cfg.get("skip_load_on_blank", True))
state_loaded = False
if world_state_path and os.path.exists(world_state_path):
    should_skip = skip_load_on_blank and world_id.lower() in ("blank", "0", "empty")
    if not should_skip:
        try:
            with open(world_state_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            world.load_dict(saved)
            state_loaded = True
            # Optional pruning of placeholder location on load
            if bool(cfg.get("prune_placeholder_on_load", True)):
                _prune_placeholder_location(world, placeholder_name=cfg.get("placeholder_name", "Starting Point"))
            # Apply player overrides (name/description only) when loading saved state
            _apply_player_config(world, player_cfg, apply_location=False, apply_inventory=False)
            print(f"Loaded world state from {world_state_path}")
        except Exception as e:
            print(f"Warning: Could not load world state from {world_state_path}: {e}")

# Optional: bootstrap world from context.txt (preferred) or starting_scenario when in exploratory mode and starting from blank
bootstrap_on_start = bool(cfg.get("bootstrap_on_start", True))
context_path = cfg.get("context_path") or "context.txt"
context_mode = exploratory_mode and os.path.exists(context_path) and world_id.lower() in ("blank", "0", "empty") and bootstrap_on_start and not state_loaded

if context_mode:
    try:
        with open(context_path, "r", encoding="utf-8") as f:
            context_text = f.read()
        # Ask model to derive system prompt, player persona, starting scenario, and world updates
        bootstrap_prompt = prompt_bootstrap_from_context(context_text)
        bootstrap_raw = model.prompt_model(bootstrap_prompt)
        # Extract JSON from fenced block or raw content
        json_str = bootstrap_raw
        m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", bootstrap_raw)
        if m:
            json_str = m.group(1)
        setup = json.loads(json_str)
        # Apply agent/system prompt and starting_scenario
        agent_system_prompt = setup.get("system_prompt")
        if isinstance(agent_system_prompt, str) and agent_system_prompt.strip():
            # If auto agent exists later we'll reinit with this; store for now
            cfg.setdefault("player_agent", {}) if isinstance(cfg, dict) else None
        starting_scenario = setup.get("starting_scenario") or starting_scenario
        # Apply player persona
        if isinstance(setup.get("player"), dict):
            p = setup["player"]
            try:
                world.player.name = p.get("name", world.player.name)
                if isinstance(p.get("descriptions"), list):
                    world.player.descriptions = [str(x) for x in p["descriptions"] if isinstance(x, str)] or world.player.descriptions
            except Exception:
                pass
        # Apply world updates (STRICT bullets)
        wu = setup.get("world_updates") or ""
        # Pre-extract created locations and whether a move was issued
        created_locations: list[str] = []
        try:
            new_loc_blocks = re.findall(r"-\s*New location:\s*(.+)", wu)
            for block in new_loc_blocks:
                names = re.findall(r"<([^<>]+)>\s*description:\s*\"", block)
                if not names:
                    names = re.findall(r"([^,<][^,]*?)\s*description:\s*\"", block)
                created_locations.extend([n.strip() for n in names if n])
        except Exception:
            pass
        had_location_change = bool(re.search(r"-\s*Your location changed:\s*<([^<>]+)>|Your location changed:\s*([^#\n]+)", wu))
        print("\n🛠️ Bootstrap from context 🛠️")
        print(wu)
        # Avoid auto-connecting placeholder and allow teleport during bootstrap
        _old_auto = getattr(world, 'auto_connect_on_move', False)
        _old_tp = getattr(world, 'allow_teleport_on_location_change', False)
        try:
            world.auto_connect_on_move = False
            world.allow_teleport_on_location_change = True
            world.parse_updates(wu)
        finally:
            world.auto_connect_on_move = _old_auto
            world.allow_teleport_on_location_change = _old_tp
        if bool(cfg.get("prune_placeholder_after_bootstrap", True)):
            _prune_placeholder_location(
                world,
                placeholder_name=cfg.get("placeholder_name", "Starting Point"),
                fallback_locations=created_locations,
                force=not had_location_change,
            )
        try:
            world.visited.add(world.player.location.name)
        except Exception:
            pass
    except Exception as e:
        print(f"Warning: Context bootstrap failed: {e}")
elif exploratory_mode and starting_scenario and bootstrap_on_start and not state_loaded and world_id.lower() in ("blank", "0", "empty"):
    try:
        bootstrap_input = cfg.get("bootstrap_instruction") or (
            "Initialize the world from the starting scenario. "
            "Generate 2–3 connected locations, 1–2 items, and 1–2 NPCs. "
            "Connect locations bidirectionally via 'Connect locations'. "
            "Choose a starting location and emit 'Your location changed' to it. "
            "Use the STRICT update format with angle brackets <...> around all names."
        )
        prompt_update = prompt_world_update_exploratory(
            world.render_world(),
            bootstrap_input,
            source_material=source_material,
            starting_scenario=starting_scenario,
        )
        response_update = model.prompt_model(prompt_update)
        # Pre-extract created locations and whether a move was issued
        created_locations: list[str] = []
        try:
            new_loc_blocks = re.findall(r"-\s*New location:\s*(.+)", response_update, flags=re.S)
            for block in new_loc_blocks:
                created_locations += [n.strip() for n in re.findall(r"<([^<>]+)>\s*description:\s*\"", block)]
        except Exception:
            pass
        had_location_change = bool(re.search(r"-\s*Your location changed:\s*<([^<>]+)>", response_update))
        # Show bootstrap results succinctly
        print("\n🛠️ Bootstrap from starting scenario 🛠️")
        def _strip_for_bootstrap(text: str) -> str:
            cleaned = re.sub(r"#([^#]*?)#", "", text, flags=re.S)
            if cleaned == text:
                cleaned = "\n".join([ln for ln in text.splitlines() if not ln.strip().startswith('#')])
            return cleaned.strip()
        print(_strip_for_bootstrap(response_update))
        def _extract_for_bootstrap(text: str):
            m = re.search(r"#([^#]*?)#", text, flags=re.S)
            if m:
                return m.group(1).strip()
            for line in reversed(text.splitlines()):
                s = line.strip()
                if s.startswith('#'):
                    return s.lstrip('#').strip(' #')
            return None
        nar = _extract_for_bootstrap(response_update)
        if nar:
            print("\n📖 Narration of the bootstrap 📖")
            print(nar)
        # During bootstrap: avoid auto-connecting to Starting Point and allow teleport
        _old_auto = getattr(world, 'auto_connect_on_move', False)
        _old_tp = getattr(world, 'allow_teleport_on_location_change', False)
        try:
            world.auto_connect_on_move = False
            world.allow_teleport_on_location_change = True
            world.parse_updates(response_update)
        finally:
            world.auto_connect_on_move = _old_auto
            world.allow_teleport_on_location_change = _old_tp
        # Fallback: if the model didn't issue a location change, jump to the first created location
        try:
            if not had_location_change and created_locations:
                target_name = created_locations[0]
                # Ensure the location exists and teleport
                try:
                    loc = world._ensure_location(target_name)
                except Exception:
                    loc = world.locations.get(target_name)
                if loc:
                    world.player.location = loc
                    try:
                        world.visited.add(loc.name)
                    except Exception:
                        pass
        except Exception:
            pass
        # Remove the placeholder location now that we have a real starting area
        if bool(cfg.get("prune_placeholder_after_bootstrap", True)):
            _prune_placeholder_location(
                world,
                placeholder_name=cfg.get("placeholder_name", "Starting Point"),
                fallback_locations=created_locations,
                force=not had_location_change,
            )
        # Apply full player config after bootstrap (location/inventory allowed)
        _apply_player_config(world, player_cfg, apply_location=True, apply_inventory=True)
    except Exception as e:
        print(f"Warning: Bootstrap failed: {e}")

# If not loading a saved state and not using the blank bootstrap path,
# apply full player overrides (location/inventory) so config can
# deterministically set the starting scene.
if not state_loaded and world_id.lower() not in ("blank", "0", "empty"):
    _apply_player_config(world, player_cfg, apply_location=True, apply_inventory=True)

while(True):
    # Show the state of the world
    print(f"🌎 World state 🌍\n{world.render_world()}\n")
    # If the player is in a different place, narrate the scene
    if last_player_position is not world.player.location:
        last_player_position = world.player.location
        prompt_scene = prompt_narrate_current_scene(world.render_world())
        response_scene = model.prompt_model(prompt_scene)
        print("\n📖 Narration of the scene 📖")
        try:
            print(f"{response_scene}\n")
            last_scene_narration = response_scene
        except Exception as e:
            print (f"Error: {e}")

    # Take the input from the user or agent
    if auto_mode and player_agent:
        # Compute exploration metadata for the agent
        leads = list(getattr(world, 'proposed_locations', {}).keys())
        current_loc = world.player.location
        visited = getattr(world, 'visited', set())
        unvisited_neighbors = [l.name for l in current_loc.connecting_locations if l.name not in visited]
        npcs_here = [c.name for c in world.characters.values() if c.location is current_loc]
        user_input = player_agent.propose_action(
            world.render_world(),
            last_scene_narration,
            leads=leads,
            unvisited_neighbors=unvisited_neighbors,
            npcs_here=npcs_here,
        )
        print(f"🤖 Agent: {user_input}")
    else:
        user_input = input("\nWhat do you want to do?\n\t\t\t👉 ")
    if user_input == "q":
        break

    # Helper utilities for narration handling
    def _extract_narration(text: str) -> str | None:
        # Prefer strict #...#; fallback to any line starting with '#'
        m = re.search(r"#([^#]*?)#", text, flags=re.S)
        if m:
            return m.group(1).strip()
        for line in reversed(text.splitlines()):
            s = line.strip()
            if s.startswith('#'):
                return s.lstrip('#').strip(' #')
        return None

    def _strip_narration(text: str) -> str:
        # Remove strict #...# if present; else drop lines starting with '#'
        cleaned = re.sub(r"#([^#]*?)#", "", text, flags=re.S)
        if cleaned == text:
            cleaned = "\n".join([ln for ln in text.splitlines() if not ln.strip().startswith('#')])
        return cleaned.strip()

    # Create the prompt and run the model
    if exploratory_mode:
        prompt_update = prompt_world_update_exploratory(
            world.render_world(),
            user_input,
            source_material=source_material,
            starting_scenario=starting_scenario,
        )
    else:
        prompt_update = prompt_world_update(world.render_world(), user_input)
    response_update = model.prompt_model(prompt_update)

    # Show the detected changes in the fictional world
    print("\n🛠️ Predicted outcomes of the player input 🛠️")
    try:
        print(f"{_strip_narration(response_update)}\n")
    except Exception as e:
        print (f"Error: {e}")

    # Show a narration for those changes
    print("\n📖 Narration of the predicted outcomes 📖")
    try:
        nar = _extract_narration(response_update)
        print(f"{nar if nar else 'No narration provided.'}\n")
    except Exception as e:
        print (f"Error: {e}")

    # Parse the response and update the world
    world.parse_updates(response_update)

    # Autosave world state if configured
    if world_state_path and autosave:
        try:
            # Create directory if needed
            d = os.path.dirname(world_state_path)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(world_state_path, "w", encoding="utf-8") as f:
                json.dump(world.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Warning: Could not save world state to {world_state_path}: {e}")
