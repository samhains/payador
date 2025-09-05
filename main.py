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
)

parser = argparse.ArgumentParser(description="PAYADOR interactive storytelling")
parser.add_argument("world", nargs="?", default="1", help="World id (default: 1; try 'blank' for an empty world)")
parser.add_argument("--explore", action="store_true", help="Enable exploratory world-building mode (overrides config)")
parser.add_argument("--config", help="Path to JSON config with settings and seeds (default: config.json)")
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
        return json.loads(raw) if raw.strip() else {}
    except Exception as e:
        raise e

if cfg_path and os.path.exists(cfg_path):
    try:
        cfg = _load_json_with_comments(cfg_path)
    except Exception as e:
        print(f"Warning: Could not load config '{cfg_path}': {e}")
        cfg = {}

# Instantiate the world
world_id = args.world
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

last_player_position = None

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

# Pass helpful toggles to the world engine
try:
    # Enable frictionless movement for invented locations when exploring
    world.auto_connect_on_move = bool(exploratory_mode)
except Exception:
    pass

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
            print(f"Loaded world state from {world_state_path}")
        except Exception as e:
            print(f"Warning: Could not load world state from {world_state_path}: {e}")

# Optional: bootstrap world from starting scenario when in exploratory mode and starting from blank
bootstrap_on_start = bool(cfg.get("bootstrap_on_start", True))
if exploratory_mode and starting_scenario and bootstrap_on_start and not state_loaded and world_id.lower() in ("blank", "0", "empty"):
    try:
        bootstrap_input = cfg.get("bootstrap_instruction") or (
            "Initialize the world based on the starting scenario. "
            "Invent plausible locations, items, and characters; connect the starting area; "
            "choose a starting location for the player and emit 'Your location changed' to it. "
            "Use the STRICT update format."
        )
        prompt_update = prompt_world_update_exploratory(
            world.render_world(),
            bootstrap_input,
            source_material=source_material,
            starting_scenario=starting_scenario,
        )
        response_update = model.prompt_model(prompt_update)
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
    except Exception as e:
        print(f"Warning: Bootstrap failed: {e}")

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
        except Exception as e:
            print (f"Error: {e}")

    # Take the input from the user
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
