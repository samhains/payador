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

    Produce updates in the STRICT format below. Use None when not applicable.
    Be concise and avoid moving the story forward beyond these state changes.

    - New item: <Name> description: "Short description" location: <Inventory|Location|Character>
    - New character: <Name> description: "Short description" location: <Location>
    - New location: <Name> description: "Short description"
    - Connect locations: <A> <-> <B>, <C> <-> <D>
    - Moved object: <object> now is in <new_location>
    - Blocked passages now available: <now_reachable_location>
    - Your location changed: <new_location>

    Notes:
    - You may output multiple items/locations/characters in the same bullet, separated by commas.
    - Only use angle-bracket tokens <...> for component names; keep descriptions in quotes.
    - If you invented a new location and the player moves there, be sure to add it via "New location" first.

    Finally, add a single short narration sentence using the format: #<your sentence>#
    """

    return prompt
