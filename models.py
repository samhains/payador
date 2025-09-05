"""Load models to use them as a narrator and a common-sense oracle in the PAYADOR pipeline."""
import os
import json
from typing import Optional
from urllib import request, error
import google.generativeai as genai


def _load_dotenv(path: str = ".env") -> None:
    """Lightweight .env loader (no external deps).

    Parses KEY=VALUE lines (supports `export KEY=...` and quoted values) and
    sets them in os.environ if not already present. Ignores blank lines and comments.
    """
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.lower().startswith("export "):
                    line = line.split(" ", 1)[1].strip()
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        # Fail silently; env vars may already be configured elsewhere.
        pass

# Load .env early so env-based config works by default
_load_dotenv()


class GeminiModel():
    def __init__ (self, api_key: Optional[str] = None, model_name: Optional[str] | None = None) -> None:
        """"Initialize the Gemini model using an API key.

        Args:
            api_key: Optional direct API key (overrides env if provided).
            model_name: Optional model name. Defaults to env `GEMINI_MODEL` or 'gemini-2.5-pro'.
        """
        self.safety_settings = [
            {
                "category": "HARM_CATEGORY_DANGEROUS",
                "threshold": "BLOCK_NONE",
            },
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_NONE",
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_NONE",
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_NONE",
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_NONE",
            },
        ]
        api_key_value = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key_value:
            raise ValueError(
                "Gemini API key not found. Set GOOGLE_API_KEY (preferred) or GEMINI_API_KEY in your environment or .env."
            )
        api_key_value = _sanitize_key(api_key_value)
        genai.configure(api_key=api_key_value)
        # Prefer Gemini 2.5 Pro unless overridden
        preferred_model = model_name or os.getenv("GEMINI_MODEL") or "gemini-2.5-pro"
        try:
            self.model = genai.GenerativeModel(preferred_model)
            self.model_name = preferred_model
        except Exception:
            # Fallback for environments without 2.5 access
            for fallback in ("gemini-1.5-pro", "gemini-pro"):
                try:
                    self.model = genai.GenerativeModel(fallback)
                    self.model_name = fallback
                    print(f"Warning: Falling back to '{fallback}' model.")
                    break
                except Exception:
                    continue
            else:
                raise

    def prompt_model(self,prompt: str) -> str:
        """Prompt the Gemini model."""
        return self.model.generate_content(prompt, safety_settings=self.safety_settings).text

def get_api_key(path: str) -> str:
    """Load an API key from path and sanitize it.

    Accepts common formats like:
    - Plain key in the first non-empty line
    - KEY=VALUE or export KEY=VALUE forms
    Strips quotes and whitespace to avoid invalid gRPC header metadata.
    """
    candidate = ""
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            # Handle forms like: export GOOGLE_API_KEY=.... or GOOGLE_API_KEY=...
            if line.lower().startswith("export "):
                line = line.split(" ", 1)[1].strip()
            if "=" in line:
                line = line.split("=", 1)[1].strip()
            # Strip surrounding quotes
            line = line.strip().strip("\"").strip("'")
            candidate = line
            break

    if not candidate:
        raise ValueError(f"No API key found in {path}. Ensure it contains your Gemini API key.")

    # Defensive: remove any stray control characters
    candidate = "".join(ch for ch in candidate if ch >= " " and ch != "\x7f")

    return candidate

def _sanitize_key(key: str) -> str:
    return "".join(ch for ch in key.strip().strip('"').strip("'") if ch >= " " and ch != "\x7f")


class OpenRouterModel:
    """Minimal OpenRouter client with a Gemini-like prompt_model interface.

    Uses the OpenAI-compatible Chat Completions API via standard library.
    """

    def __init__(
        self,
        api_key_file: Optional[str] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: str = "https://openrouter.ai/api/v1",
        app_title: str = "PAYADOR",
    ) -> None:
        # Resolve API key: explicit > env > file
        key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not key and api_key_file:
            key = get_api_key(api_key_file)
        if not key:
            raise ValueError(
                "OpenRouter API key not provided. Set OPENROUTER_API_KEY or pass api_key/api_key_file."
            )

        # Sanitize to avoid illegal headers
        self.api_key = _sanitize_key(key)

        self.base_url = base_url.rstrip("/")
        self.model_name = model_name or os.getenv("OPENROUTER_MODEL") or "google/gemini-2.5-pro"
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # These are optional but recommended by OpenRouter
            "X-Title": app_title,
        }

    def prompt_model(self, prompt: str) -> str:
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }

        req = request.Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=60) as resp:
                body = resp.read()
                data = json.loads(body.decode("utf-8"))
        except error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
            raise RuntimeError(f"OpenRouter HTTP error {e.code}: {detail}") from e
        except error.URLError as e:
            raise RuntimeError(f"OpenRouter connection error: {e}") from e

        try:
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"Unexpected OpenRouter response schema: {data}") from e
