# PAYADOR
This repository contains the code for the PAYADOR approach, described in the ICCC24 paper “[PAYADOR: A Minimalist Approach to Grounding Language Models on Structured Data for Interactive Storytelling and Role-playing Games](https://github.com/pln-fing-udelar/payador/blob/main/PAYADOR_ICCC-2024-Proceedings.pdf)”.

TL;DR: The PAYADOR approach to the world-update problem in Interactive Storytelling (and Role-playing Games) consists of grounding Large Language Models to structured data and use them to predict the outcomes of the player input.

Authors: [Santiago Góngora](https://scholar.google.com/citations?user=p1lKpmYAAAAJ), [Luis Chiruzzo](https://scholar.google.com/citations?user=C7c4uCsAAAAJ), [Gonzalo Méndez](https://scholar.google.com/citations?user=lC8QyOwAAAAJ) and [Pablo Gervás](https://scholar.google.com/citations?user=AcY-Y2gAAAAJ).


## 🗂️ Project structure
The PAYADOR approach is intended to be easily adaptable for other research problems in Interactive Storytelling. Here we will briefly describe each module and add comments about how they should be modified for other cases.

- `main.py` implements the main loop of PAYADOR, as detailed in the picture below (same as Figure 3 of the paper). 
- `world.py` implements the three components of the world model (Items, Characters and Locations) as well as the world itself. This module also implements the world state rendering in natural language and the update of the world state, key steps for the PAYADOR approach.
    - ❗ If you are working for a different language than English, you will need to adapt the *render_world* and *parse_updates* methods.
    - ❗ If you are working for other changes in the fictional world (e.g. mood during a conversation, like in the [Emolift paper](https://computationalcreativity.net/iccc2019/papers/iccc19-paper-44.pdf)) you will need to add another updates in the *parse_updates* method.
- `example_worlds.py` includes some simple ready-to-play worlds. All their world components are in English.
- `models.py` loads and prompts the Gemini model.
    - ❗ If you want to use a different model, you can add another class for it.
- `prompts.py`
    - ❗ If you are working for a different language than English, you will need to adapt these prompts.
    - ❗ If you are working for other changes in the fictional world, you will need to ask for additional updates in the *prompt_world_update* function.

![A picture describing the PAYADOR approach, taken from the paper.](pipeline.jpg "Payador pipeline")
## ⚙️ Usage

Please, follow these steps to get this code running.

### Dependencies

To install the dependencies using [conda](https://conda.io/projects/conda/en/latest/user-guide/install/index.html), just run

```shell
conda env create -f environment.yml
```

and then activate the environment


```shell
conda activate payador
```

### Environment variables (.env)

Create a `.env` file in the project root (or export variables in your shell). The code auto-loads `.env` without extra dependencies.

Minimal examples:

```
# Choose provider: gemini (default) or openrouter
LLM_PROVIDER=gemini

# Gemini setup
GOOGLE_API_KEY=your_gemini_api_key
# Optional: pick a specific model
GEMINI_MODEL=gemini-2.5-pro

# OpenRouter setup (optional alternative)
# OPENROUTER_API_KEY=your_openrouter_api_key
# OPENROUTER_MODEL=google/gemini-2.5-pro
```

Notes:
- `GOOGLE_API_KEY` is preferred for Gemini; `GEMINI_API_KEY` is also supported.
- If you set `LLM_PROVIDER=openrouter`, the app will use OpenRouter instead.

### Run!

Finally, just run `main.py`.

```shell
python main.py
```

### Exploratory world-building mode (optional)

Enable a mode where the model can invent new locations, items, and characters and persist them to the world state via structured updates.

```
# Default config `config.json` enables exploratory mode
python main.py

# Optional: if you add a background text file, it will be picked up automatically
echo "A dusty spaceport on the desert planet Aridia..." > source_material.txt
python main.py --explore
```

Notes:
- A default `config.json` is included and auto-loaded; it enables exploratory mode, defines a starting scenario, and configures saving.
- If `source_material.txt` exists in the project root, it is used automatically as background text.
- You can still pass a custom config with `--config` or override via `--explore`.

Blank world preset
- Start from an empty canvas designed for exploratory building:
  - `python main.py blank`
  - If `starting_scenario` is set in `config.json`, the app bootstraps an initial set of locations/characters/items from it before the first turn. Saved state is skipped when starting with `blank`.

Saving and loading world state
- Configure a path in `config.json` to persist the evolving world across runs:
  - `"world_state_path": "world_state.json"`
  - `"autosave": true` (saves after each turn)
- On startup, if the file exists, the app loads it automatically.

In this mode, the model outputs extra world-building bullets (e.g., "New item", "New location", "New character", "Connect locations"). The engine parses these and extends the world so later turns can reference the newly created elements.

## 📄 Paper

ICCC'24 Proceedings: [Here!](https://computationalcreativity.net/iccc24/papers/ICCC24_paper_152.pdf)

### Citation

If you use some part of this work in your research, please cite:

```
@inproceedings{gongora2024payador,
  title={PAYADOR: A Minimalist Approach to Grounding Language Models on Structured Data for Interactive Storytelling and Role-playing Games},
  author={G{\'o}ngora, Santiago and Chiruzzo, Luis and M{\'e}ndez, Gonzalo and Gerv{\'a}s, Pablo},
  booktitle={Proceedings of The 15th International Conference on Computational Creativity},
  year={2024}
}
```
