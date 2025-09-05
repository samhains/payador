from __future__ import annotations

from typing import List, Optional

from prompts import prompt_player_action


class PlayerAgent:
    """Autonomous player agent that proposes next actions.

    Uses the same model interface as the app (object with .prompt_model(prompt) -> str).
    """

    def __init__(
        self,
        model,
        *,
        system_prompt: str,
        history: Optional[List[str]] = None,
        style_hint: Optional[str] = None,
    ) -> None:
        self.model = model
        self.system_prompt = system_prompt
        self.history = list(history or [])
        self.style_hint = style_hint

    def remember(self, text: str) -> None:
        self.history.append(text)

    def propose_action(
        self,
        world_state: str,
        scene_narration: Optional[str],
        *,
        leads: list[str] | None = None,
        unvisited_neighbors: list[str] | None = None,
        npcs_here: list[str] | None = None,
    ) -> str:
        prompt = prompt_player_action(
            world_state,
            system_prompt=self.system_prompt,
            history=self.history,
            scene_narration=scene_narration,
            style_hint=self.style_hint,
            leads=leads,
            unvisited_neighbors=unvisited_neighbors,
            npcs_here=npcs_here,
        )
        raw = self.model.prompt_model(prompt)
        return _sanitize_action(raw)


def _sanitize_action(text: str) -> str:
    # Take the first non-empty line, strip quotes and trailing punctuation
    for line in text.splitlines():
        action = line.strip().strip('"').strip("'")
        if action:
            # Trim to a reasonable single line
            return action.split("  ")[0].strip()
    return "Look around"
