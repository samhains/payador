"""This module implements the classes needed to represent the fictional world of the game.

The world class includes references to the several components (Items, Locations, Character),
and methods to update according to the detected changes by a language model.
"""

import re


class Component:
  """A class to represent a component of the world.

  The components considered in the PAYADOR approach are Items, Locations and Characters.
  """
  def __init__ (self, name:str, descriptions: 'list[str]'):

    self.name = name
    """the name of the component"""

    self.descriptions = descriptions
    """a set of natural language descriptions for the component"""

class Item (Component):
  """A class to represent an Item."""
  def __init__ (self, name:str, descriptions: 'list[str]', gettable: bool = True):

    super().__init__(name, descriptions)
    """inherited from Component"""

    self.gettable = gettable
    """indicates if the Item can be taken by the player"""

class Location (Component):
  """A class to represent a Location in the world."""
  def __init__ (self, name:str, descriptions: 'list[str]', items: 'list[Item]' = None, connecting_locations: 'list[Location]' = None):

    super().__init__(name, descriptions)
    """inherited from Component"""

    self.items = items or []
    """a list of the items available in that location"""

    self.connecting_locations = connecting_locations or []
    """a list of the reachable locations from itself."""

    self.blocked_locations = {}
    """a dictionary with the name of a location as key and <location,obstacle,symmetric> as value.
    A blocked passage between self and a location means that it
    will be reachable from [self] after overcoming the [obstacle].
    The symmetric variable is a boolean that indicates if, when unblocked,
    [self] will also be reachable from [location].
    """

  def block_passage(self, location: 'Location', obstacle, symmetric: bool = True):
    """Block a passage between self and location using an obstacle."""
    if location in self.connecting_locations:
      if location.name not in self.blocked_locations:
        self.blocked_locations[location.name] = (location, obstacle, symmetric)
        self.connecting_locations = [x for x in self.connecting_locations if x is not location]
      else:
        raise Exception(f"Error: A blocked passage to {location.name} already exists")
    else:
        raise Exception(f"Error: Two non-conected locations cannot be blocked")

  def unblock_passage(self, location: 'Location'):
    """Unblock a passage between self and location by adding it to the connecting locations of self.

    In case that the block was symmetric, self will be added to the connecting locations of location.
    """
    if self.blocked_locations[location.name]:
      self.connecting_locations += [location]
      if self.blocked_locations[location.name][2]:
        location.connecting_locations += [self]
      del self.blocked_locations[location.name]
    else:
      raise Exception("Error: That is not a blocked passage")

class Character (Component):
  """A class to represent a character."""
  def __init__ (self, name:str, descriptions: 'list[str]', location:Location, inventory: 'list[Item]' = None):

    super().__init__(name, descriptions)
    """inherited from Component"""

    self.inventory = inventory or []
    """a set of Items the carachter has"""

    self.location = location
    """the location of the character"""

  def move(self, new_location: Location):
    """Move the character to a new location."""
    if new_location in self.location.connecting_locations:
      self.location = new_location
    else:
      raise Exception(f"Error: {new_location.name} is not reachable")

  def save_item(self,item: Item, item_location_or_owner):
    """Add an item to the character inventory."""
    if item.gettable:
      if item not in self.inventory:
        self.inventory += [item]
        if item_location_or_owner.__class__.__name__ == 'Character':
          item_location_or_owner.inventory = [i for i in item_location_or_owner.inventory if i is not item]
        elif item_location_or_owner.__class__.__name__ == 'Location':
          item_location_or_owner.items = [i for i in item_location_or_owner.items if i is not item]
      else:
        raise Exception(f"Error: {item.name} is already in your inventory")
    else:
      raise Exception(f"Error: {item.name} cannot be taken")

  def drop_item (self, item: Item):
    """Leave an item in the current location."""
    self.inventory = [i for i in self.inventory if i is not item]
    self.location.items += [item]

  def give_item (self, character: 'Character', item: Item):
    """Give an item to another character."""
    try:
      character.save_item(item, self)
    except Exception as e:
      print(e)


class World:
  """A class to represent the fictional world, with references to every component."""
  def __init__ (self, player: Character) -> None:

    self.items = {}
    """a dictionary of all the Items in the world, with their names as values"""

    self.characters = {}
    """a dictionary of all the Characters in the world, with their names as values"""

    self.locations =  {}
    """a dictionary of all the Locations in the world, with their names as values"""

    self.player = player
    """a character for the player"""

    # When True, allow auto-connecting the current location to a target
    # location if a movement is requested but no path exists (useful in
    # exploratory world-building mode to reduce friction).
    self.auto_connect_on_move: bool = False
    # When True, allow location change to set the player's
    # location directly even if unreachable (used during bootstrap).
    self.allow_teleport_on_location_change: bool = False

  # ===== Persistence: export/import state =====
  def to_dict(self) -> dict:
    """Serialize the current world to a JSON-serializable dict."""
    def item_dict(i: Item) -> dict:
      return {
        "descriptions": i.descriptions,
        "gettable": bool(i.gettable),
      }

    def location_dict(loc: Location) -> dict:
      blocked_list = []
      for name, (target, obstacle, symmetric) in loc.blocked_locations.items():
        blocked_list.append({
          "location": target.name,
          "obstacle": obstacle.name if isinstance(obstacle, Item) else str(obstacle),
          "symmetric": bool(symmetric),
        })
      return {
        "descriptions": loc.descriptions,
        "items": [i.name for i in loc.items],
        "connecting_locations": [l.name for l in loc.connecting_locations],
        "blocked": blocked_list,
      }

    def character_dict(c: Character) -> dict:
      return {
        "descriptions": c.descriptions,
        "location": c.location.name,
        "inventory": [i.name for i in c.inventory],
      }

    data = {
      "items": {name: item_dict(i) for name, i in self.items.items()},
      "locations": {name: location_dict(l) for name, l in self.locations.items()},
      "characters": {name: character_dict(c) for name, c in self.characters.items()},
      "player": {
        "name": self.player.name,
        "descriptions": self.player.descriptions,
        "location": self.player.location.name,
        "inventory": [i.name for i in self.player.inventory],
      },
    }
    return data

  def load_dict(self, data: dict) -> None:
    """Replace current world state with the one provided in a dict.

    Expected schema matches to_dict().
    """
    # Reset containers
    self.items = {}
    self.locations = {}
    self.characters = {}

    # Items first
    items_data = data.get("items", {})
    for name, meta in items_data.items():
      descs = meta.get("descriptions", [])
      gettable = bool(meta.get("gettable", True))
      self.items[name] = Item(name, descs, gettable=gettable)

    # Locations next (without wiring)
    locs_data = data.get("locations", {})
    for name, meta in locs_data.items():
      descs = meta.get("descriptions", [])
      items_here = [self.items[i] for i in meta.get("items", []) if i in self.items]
      self.locations[name] = Location(name, descs, items=items_here)

    # Connect locations (open paths)
    for name, meta in locs_data.items():
      loc = self.locations[name]
      for target_name in meta.get("connecting_locations", []):
        if target_name in self.locations:
          target = self.locations[target_name]
          if target not in loc.connecting_locations:
            loc.connecting_locations.append(target)

    # Blocked passages
    for name, meta in locs_data.items():
      loc = self.locations[name]
      for blk in meta.get("blocked", []) or []:
        tname = blk.get("location")
        oname = blk.get("obstacle")
        symmetric = bool(blk.get("symmetric", True))
        if not tname or tname not in self.locations or not oname or oname not in self.items:
          continue
        target = self.locations[tname]
        obstacle = self.items[oname]
        if target not in loc.connecting_locations:
          loc.connecting_locations.append(target)
        try:
          loc.block_passage(target, obstacle, symmetric=symmetric)
        except Exception:
          # If already blocked or structure differs, set directly
          loc.blocked_locations[target.name] = (target, obstacle, symmetric)
          if target in loc.connecting_locations:
            loc.connecting_locations = [x for x in loc.connecting_locations if x is not target]

    # Characters (NPCs)
    chars_data = data.get("characters", {})
    for name, meta in chars_data.items():
      location_name = meta.get("location")
      if location_name not in self.locations:
        continue
      loc = self.locations[location_name]
      descs = meta.get("descriptions", [])
      inv = [self.items[i] for i in meta.get("inventory", []) if i in self.items]
      ch = Character(name, descs, location=loc, inventory=inv)
      self.add_character(ch)

    # Player
    p = data.get("player", {})
    pname = p.get("name", "Player")
    pdescs = p.get("descriptions", [])
    ploc_name = p.get("location")
    ploc = self.locations.get(ploc_name, next(iter(self.locations.values())) if self.locations else None)
    pinv = [self.items[i] for i in p.get("inventory", []) if i in self.items]
    if ploc is None:
      # Fallback minimal location
      ploc = Location("Nowhere", ["An undefined place"]) 
      self.add_location(ploc)
    self.player = Character(pname, pdescs, location=ploc, inventory=pinv)

  def add_location (self,location: Location) -> None:
    """Add a location to the world."""
    if location.name in self.locations:
      raise Exception(f"Error: Already exists a location called '{location.name}'")
    else:
       self.locations[location.name] = location

  def add_item (self, item: Item) -> None:
    """Add an item to the world."""  
    if item.name in self.items:
      raise Exception(f"Error: Already exists an item called '{item.name}'")
    else:
      self.items[item.name] = item

  def add_character (self, character: Character) -> None:
    """Add a character to the world."""
    if character.name in self.characters:
      raise Exception(f"Error: Already exists a character called '{character.name}'")
    else:
      self.characters[character.name] = character

  def add_locations (self,locations: 'list[Location]') -> None:
    """"Add a set of locations to the world."""
    for location in locations:
      self.add_location(location)

  def add_items (self, items: 'list[Item]') -> None:
    """Add a set of items to the world."""
    for item in items:
      self.add_item(item)

  def add_characters (self, characters: 'list[Character]') -> None:
    """Add a set of characters to the world."""
    for character in characters:
      self.add_character(character)

  def render_world(self, *,  detail_components:bool = True) -> str:
    """Return the fictional world as a natural language description, using simple sentences.

    The components described are only those the player can see in the current location.
    If detail_components is False, then the descriptions for each component are not included.
    """
    player_location = self.player.location
    reachable_locations = [f"<{p.name}>" for p in player_location.connecting_locations]
    blocked_passages = [f"<{p}> blocked by <{player_location.blocked_locations[p][1].name}>" for p in player_location.blocked_locations.keys()]
    characters_in_the_scene = [character for character in self.characters.values() if character.location is player_location]

    
    world_description = f'You are in <{player_location.name}>\n'
    
    if reachable_locations:
      world_description += f'From <{player_location.name}> you can access: {(", ").join(reachable_locations)}\n'
    else:
      world_description += f'From <{player_location.name}> you can access: None\n'

    if blocked_passages:
      world_description += f'From <{player_location.name}> there are blocked passages to: {(", ").join(blocked_passages)}\n'
    else:
      world_description += f'From <{player_location.name}> there are blocked passages to: None\n'

    if self.player.inventory:
      world_description += f'You have the following items in your inventory: {(", ").join([f"<{i.name}>" for i in self.player.inventory])}\n'
    else:
      world_description += f'You have the following items in your inventory: None\n'

    if player_location.items:
      world_description += f'If you look around, you can see the following items: {(", ").join([f"<{i.name}>" for i in player_location.items])}\n'
    else:
      world_description += f'If you look around, you can see the following items: None\n'
      
    if characters_in_the_scene:
      world_description += f'You can see some people: {(", ").join([f"<{c.name}>" for c in characters_in_the_scene])}'
    else:
      world_description += f'You can see some people: None'

    details = ""
    if detail_components:
      items_in_the_scene = player_location.items + self.player.inventory + [blocked_values[1] for blocked_values in player_location.blocked_locations.values() if isinstance(blocked_values[1], Item)]
      
      details += "\nHere is a description of each component.\n"
      details += f"<{player_location.name}>: This is the player's location. {('. ').join(player_location.descriptions)}.\n"
      details += "Characters:\n"
      details += f"- <Player>: The player is acting as {self.player.name}. {('. ').join(self.player.descriptions)}.\n"
      if len(characters_in_the_scene)>0:
        for character in characters_in_the_scene:
          details += f"- <{character.name}>: {('. ').join(character.descriptions)}."
          if len(character.inventory)>0:
            details += f" This character has the following items: {(', ').join([f'<{i.name}>' for i in character.inventory])}\n"
            items_in_the_scene+= character.inventory
          else:
            details += "\n"
      if len(items_in_the_scene)>0:
        details+="Objects:\n"
        for item in items_in_the_scene:
          details += f"- <{item.name}>: {('. ').join(item.descriptions)}\n"

    return world_description + '\n' + details

  def parse_updates (self, updates: str) -> None:
    """Does the changes in the world according to the output of the language model.

    The possible changes considered are:
      - an object was moved
      - a location is now reachable
      - the position of the player changed.
    """
    # First handle any world-building operations so subsequent moves can reference them
    try:
      self.parse_new_locations(updates)
      self.parse_new_characters(updates)
      self.parse_new_items(updates)
      self.parse_connect_locations(updates)
    except Exception as e:
      print(e)

    # Then apply movement/connectivity changes
    self.parse_moved_objects(updates)
    self.parse_blocked_passages(updates)
    self.parse_location_change(updates)

  # ===== World-building extensions =====
  def _ensure_location(self, name: str, description: str | None = None) -> 'Location':
    if name in self.locations:
      return self.locations[name]
    descs = [description] if description else ["An unspecified location created during play."]
    loc = Location(name, descs)
    self.add_location(loc)
    return loc

  def _ensure_character(self, name: str, description: str | None, location_name: str) -> 'Character':
    if name in self.characters:
      return self.characters[name]
    loc = self._ensure_location(location_name)
    descs = [description] if description else ["A character created during play."]
    ch = Character(name, descs, location=loc)
    self.add_character(ch)
    return ch

  def _ensure_item(self, name: str, description: str | None) -> 'Item':
    if name in self.items:
      return self.items[name]
    descs = [description] if description else ["An object created during play."]
    it = Item(name, descs)
    self.add_item(it)
    return it

  def parse_new_locations(self, updates: str) -> None:
    matches = re.findall(r"-\s*New location:\s*(.+)", updates)
    if not matches:
      return
    # Allow comma-separated entries on the same line
    entries = re.findall(r"<([^<>]+)>\s*description:\s*\"([^\"]*)\"", matches[0])
    for name, desc in entries:
      try:
        self._ensure_location(name.strip(), desc.strip())
      except Exception as e:
        print(e)

  def parse_new_characters(self, updates: str) -> None:
    matches = re.findall(r"-\s*New character:\s*(.+)", updates)
    if not matches:
      return
    entries = re.findall(r"<([^<>]+)>\s*description:\s*\"([^\"]*)\"\s*location:\s*<([^<>]+)>", matches[0])
    for name, desc, loc in entries:
      try:
        self._ensure_character(name.strip(), desc.strip(), loc.strip())
      except Exception as e:
        print(e)

  def parse_new_items(self, updates: str) -> None:
    matches = re.findall(r"-\s*New item:\s*(.+)", updates)
    if not matches:
      return
    entries = re.findall(r"<([^<>]+)>\s*description:\s*\"([^\"]*)\"\s*location:\s*<([^<>]+)>", matches[0])
    for name, desc, dst in entries:
      try:
        item = self._ensure_item(name.strip(), desc.strip())
        dst = dst.strip()
        # Place item
        if dst == 'Inventory':
          try:
            self.player.save_item(item, self.player.location)
          except Exception:
            # If already in inventory, ignore
            pass
        elif dst in self.locations:
          loc = self.locations[dst]
          if item not in loc.items:
            loc.items.append(item)
        elif dst in self.characters:
          ch = self.characters[dst]
          if item not in ch.inventory:
            ch.inventory.append(item)
        else:
          # Create location and place there
          loc = self._ensure_location(dst)
          if item not in loc.items:
            loc.items.append(item)
      except Exception as e:
        print(e)

  def parse_connect_locations(self, updates: str) -> None:
    matches = re.findall(r"-\s*Connect locations:\s*(.+)", updates)
    if not matches:
      return
    # Extract explicit pairs like <A> <-> <B>, <C> <-> <D>
    all_text = matches[0]
    pairs = re.findall(r"<([^<>]+)>\s*<->\s*<([^<>]+)>", all_text)
    if not pairs:
      return
    def connect(a: 'Location', b: 'Location'):
      if b not in a.connecting_locations:
        a.connecting_locations.append(b)
      if a not in b.connecting_locations:
        b.connecting_locations.append(a)
    for a_name, b_name in pairs:
      a = self._ensure_location(a_name.strip())
      b = self._ensure_location(b_name.strip())
      connect(a, b)

  def parse_moved_objects (self, updates: str) -> None:
    """Parse the output of the language model to update the position of objects.

    There are three cases:
      - the player has a new item
      - the player gave an item to other character
      - the player dropped an item.
    """
    parsed_objects = re.findall(r"-\s*Moved object:\s*(.+)", updates)
    if not parsed_objects:
      return
    line = parsed_objects[0].strip()
    if line.lower().startswith('none'):
      return
    parsed_objects_split = re.findall(r"<[^<>]*?>.*?<[^<>]*?>", line)
    for parsed_object in parsed_objects_split:
      pair = re.findall(r"<([^<>]*?)>.*?<([^<>]*?)>", parsed_object)
      try:
        world_item = self.items[pair[0][0]]
        
        if pair[0][1] == 'Inventory': #(save_item case)
          item_location = [character for character in list(self.characters.values()) if world_item in character.inventory]
          item_location += [location for location in list(self.locations.values()) if world_item in location.items]
          if item_location:
            self.player.save_item(world_item, item_location[0])
        elif pair[0][1] in self.characters: #(give_item case)
          self.player.give_item(self.characters[pair[0][1]], world_item)
        else: #(drop_item case)
          self.player.drop_item(world_item)
      except Exception as e:
        print(e)

  def parse_blocked_passages (self, updates: str) -> None:
    """Parse the output of the language model to update the reachable locations."""
    parsed_blocked_passages = re.findall(r"-\s*Blocked passages now available:\s*(.+)", updates)
    if not parsed_blocked_passages:
      return
    line = parsed_blocked_passages[0].strip()
    if line.lower().startswith('none'):
      return
    parsed_blocked_passages_split = re.findall(r"<([^<>]*?)>", line)
    for parsed_passage in parsed_blocked_passages_split:
      try:
        self.locations[self.player.location.name].unblock_passage(self.locations[parsed_passage])
      except Exception as e:
        print (e)

  def parse_location_change (self, updates: str) -> None:
    """Parse the output of the language model to update the position of the player."""
    parsed_location_change = re.findall(r"-\s*Your location changed:\s*(.+)", updates)
    if not parsed_location_change:
      return
    line = parsed_location_change[0].strip()
    if line.lower().startswith('none'):
      return
    parsed_location_change_split = re.findall(r"<([^<>]*?)>", line)
    if not parsed_location_change_split:
      return
    try:
      self.player.move(self.locations[parsed_location_change_split[0]])
    except Exception as e:
      # If movement fails due to unreachable, optionally teleport or auto-connect
      try:
        target = self.locations[parsed_location_change_split[0]]
        current = self.player.location
        if self.allow_teleport_on_location_change:
          self.player.location = target
        elif self.auto_connect_on_move and target not in current.connecting_locations:
          # Bidirectional connection
          current.connecting_locations.append(target)
          if current not in target.connecting_locations:
            target.connecting_locations.append(current)
          # Move after connecting
          self.player.location = target
        else:
          print(e)
      except Exception as e2:
        print(e2)
