"""Implement the main loop for the PAYADOR approach, described in Fig.3 of the paper.

The main steps in the loop are:
- Describe the ficional world in simple sentences
- Get the player input
- Prompt a model to predict the outcomes in the world, after the actions described by the player.
"""

import re
import sys

import example_worlds
import os
from models import GeminiModel, OpenRouterModel
from prompts import (
    prompt_narrate_current_scene,
    prompt_world_update,
    prompt_world_update_exploratory,
)

# Instantiate the world
world_id = sys.argv[1] if len(sys.argv) > 1 else "1"
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

# Exploratory mode configuration (optional)
exploratory_mode = os.getenv("EXPLORATORY_MODE", "0").strip() in ("1", "true", "yes", "on")
source_material = None
starting_scenario = None
if exploratory_mode:
    source_path = os.getenv("SOURCE_MATERIAL", "source_material.txt").strip()
    try:
        if os.path.exists(source_path):
            with open(source_path, "r", encoding="utf-8") as f:
                source_material = f.read()
    except Exception:
        source_material = None
    starting_scenario = os.getenv("STARTING_SCENARIO")

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
        print(f"{re.sub(r'#([^#]*?)#','',response_update)}\n")
    except Exception as e:
        print (f"Error: {e}")

    # Show a narration for those changes
    print("\n📖 Narration of the predicted outcomes 📖")
    try:
        print(f"{re.findall(r'#([^#]*?)#',response_update)[0]}\n")
    except Exception as e:
        print (f"Error: {e}")

    # Parse the response and update the world
    world.parse_updates(response_update)
