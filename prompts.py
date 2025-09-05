def prompt_narrate_current_scene (world_state: str) -> str:
    prompt = f"""You are a storyteller. Take the following state of the world and narrate it in a few sentences. Be careful not to include details that contradict the current state of the world or that move the story forward. Also, try to use simple sentences, being concise and exhaustive.
    
    This is the state of the world at the moment:
    {world_state}
    """

    return prompt

def prompt_world_update (world_state: str, input: str) -> str:
    prompt = f"""You are a storyteller. You are managing a fictional world, and the player can interact with it. This is the state of the world at the moment:
    {world_state}\n\n
    Explain the changes in the world after the player actions in this input "{input}". 
    
    Here are some clarifications. If a passage is blocked, then the player must unblock it before being able to reach the place. Pay atenttion to the description of the components and their capabilities.
    Do not assume that the given input always make sense; maybe those actions try to do something that the world does not allow.
    Follow always the following format with the three categories, using "None" in each case if there are no changes and repeat the category for each case (there may be more than 3 items in the list):
    - Moved object: <object> now is in <new_location>
    - Blocked passages now available: <now_reachable_location>
    - Your location changed: <new_location>
    
    Here you have some examples. 
    Example 1
    - Moved object: <axe> now is in <Inventory>
    - Blocked passages now available: None
    - Your location changed: None

    Example 2
    - Moved object: None
    - Blocked passages now available: None
    - Your location changed: <Garden>

    Example 3
    - Moved object: <banana> now is in <Inventory>,  <bottle> now is in <Inventory>,  <axe> now is in <Main Hall>
    - Blocked passages now available: None
    - Your location changed: None

    Example 4
    - Moved object: <banana> now is in <Inventory>,  <bottle> now is in <Inventory>,  <axe> now is in <Main Hall>
    - Blocked passages now available: <Small room>
    - Your location changed: None

    Example 5
    - Moved object: <banana> now is in <Inventory>,  <bottle> now is in <Inventory>,  <axe> now is in <Main Hall>
    - Blocked passages now available: <Small room>
    - Your location changed:  <Small room>

    Example 6
    - Moved object: <book> now is in <John>,  <pencil> now is in <Inventory>
    - Blocked passages now available: None
    - Your location changed:  None

    Example 7
    - Moved object: <computer> now is in <Susan>
    - Blocked passages now available: None
    - Your location changed:  None
    

    Finally, you can add a final short sentence narrating the detected changes in the state of the world (without moving the story forward and creating details not included in the state of the world!) or answering a question of the player, using the format: #<your final sentence>#
    """

    return prompt


def prompt_world_update_exploratory(
    world_state: str,
    input: str,
    *,
    source_material: str | None = None,
    starting_scenario: str | None = None,
) -> str:
    """Exploratory world-building prompt.

    Encourages the model to invent (hallucinate) new components as needed and
    output strictly structured updates so we can parse and persist them.
    """

    context = ""
    if source_material:
        context += f"\nBACKGROUND MATERIAL (you may expand creatively):\n{source_material}\n"
    if starting_scenario:
        context += f"\nSTARTING SCENARIO (seed):\n{starting_scenario}\n"

    prompt = f"""You are a creative world-builder and storyteller managing a fictional world.
    You must keep internal consistency with the current state but are encouraged to invent new elements
    to make the world richer and to enable the player's actions.

    Current world state:
    {world_state}
    {context}

    Player input: "{input}"

    Produce updates in the STRICT format below. Use None when not applicable. Always include all bullets, including 'Observed paths'.
    Be concise and avoid moving the story forward beyond these state changes.

    - New item: <Name> description: "Short description" location: <Inventory|Location|Character>
    - New character: <Name> description: "Short description" location: <Location>
    - New location: <Name> description: "Short description"
    - Connect locations: <A> <-> <B>, <C> <-> <D>
    - Observed paths: <Diegetic lead name> description: "short diegetic hint", <Another lead> description: "..."
    - Moved object: <object> now is in <new_location>
    - Blocked passages now available: <now_reachable_location>
    - Your location changed: <new_location>

    Notes:
    - You may output multiple items/locations/characters in the same bullet, separated by commas.
    - Only use angle-bracket tokens <...> for component names; keep descriptions in quotes.
    - If you invented a new location and the player moves there, add it via "New location" first.
    - Observed paths are diegetic hooks (whispers, signage, tunnels) that the player could explore later; they DO NOT create locations yet. We will materialize them only if the player goes there.
    - Prefer 1–2 observed paths per turn that feel natural to the scene.

    Finally, add a single short narration sentence using the format: #<your sentence>#. Weave the observed paths into the prose naturally, without listing them mechanically.
    """

    return prompt


def prompt_bootstrap_from_context(context_text: str) -> str:
    """Derive system prompt, player persona, starting scenario, and initial world from a context file.

    Output a single JSON object with keys:
      - system_prompt: string
      - starting_scenario: string (one or two sentences)
      - player: { name: string, descriptions: [string, ...] }
      - world_updates: string containing STRICT bullets to create 2–3 locations,
        1–2 items, 1–2 NPCs, bidirectional connections, and a starting move.

    The world_updates MUST follow the same strict format used elsewhere:
      - New item: <Name> description: "Short description" location: <Inventory|Location|Character>
      - New character: <Name> description: "Short description" location: <Location>
      - New location: <Name> description: "Short description"
      - Connect locations: <A> <-> <B>, <C> <-> <D>
      - Moved object: <object> now is in <new_location>
      - Blocked passages now available: <now_reachable_location>
      - Your location changed: <new_location>
      - Observed paths: <Lead> description: "short hint", <Lead2> description: "short hint"

    Wrap the JSON in a fenced block like: ```json ... ```.
    """
    prompt = f"""You are setting up an interactive story world from a single context.

Context:
{context_text}

Produce a JSON object with:
- system_prompt: Guidance for a curious, in-character explorer in this world.
- starting_scenario: One or two-sentence seed for the opening scene.
- player: name and 1–3 short descriptions.
- world_updates: STRICT bullet list to create 2–3 connected locations, 1–2 items, 1–2 NPCs,
  and bidirectional connections. Include a 'Your location changed: <...>' for the initial scene and
  an 'Observed paths' bullet with 1–2 diegetic leads (no creation yet).

Return only the JSON wrapped in ```json fences.
"""
    return prompt


def prompt_player_action(
    world_state: str,
    *,
    system_prompt: str,
    history=None,
    scene_narration: str | None = None,
    style_hint: str | None = None,
    leads: list[str] | None = None,
    unvisited_neighbors: list[str] | None = None,
    npcs_here: list[str] | None = None,
) -> str:
    """Prompt template for a player-agent that proposes the next action.

    The agent outputs a single, concise action line with no extra commentary.
    """
    history = history or []
    hist_block = "\n".join([f"- {h}" for h in history])
    scene_block = f"\nLatest scene narration:\n{scene_narration}\n" if scene_narration else "\n"
    leads = leads or []
    unvisited_neighbors = unvisited_neighbors or []
    npcs_here = npcs_here or []
    leads_block = "\nObserved paths (leads):\n" + "\n".join([f"- {l}" for l in leads]) if leads else "\nObserved paths (leads):\n- None"
    neighbors_block = "\nUnvisited adjacent places:\n" + "\n".join([f"- {n}" for n in unvisited_neighbors]) if unvisited_neighbors else "\nUnvisited adjacent places:\n- None"
    npcs_block = "\nNPCs here:\n" + "\n".join([f"- {n}" for n in npcs_here]) if npcs_here else "\nNPCs here:\n- None"
    style = style_hint or "Stay in character and be curious, concrete, and practical."

    prompt = f"""{system_prompt}

You are role-playing as the player. Given the current world, propose ONE next in-character action.
Return only the action text on a single line. Do not include quotes, narration, explanations, or bullets.

Conversation primer (persona/history):
{hist_block}

Current world state:
{world_state}
{scene_block}
{leads_block}
{neighbors_block}
{npcs_block}

Guidelines:
- Output a single imperative or first-person action (3–12 words).
- Prefer feasible, concrete actions (move, examine, take/give, talk/use, unblock).
- If any observed paths are available, pick one and go there (e.g., "Go to <lead>").
- Otherwise, move to an unvisited adjacent place. If none, engage with an NPC or examine a salient object.
- {style}

Examples (format only):
- Go to the Umbilical Atrium
- Examine the chitin pillars
- Ask the Custodian about exits
- Pick up the chitin shard

Your action:
"""
    return prompt
