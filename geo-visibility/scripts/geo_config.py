"""Project settings shared by the scripts (standard library only).

Put a `geo-visibility.json` in the folder you run from and the scripts stop asking for the same things:

    {
      "domain": "www.example.com",
      "paths": ["/pricing", "/blog/a-post"],
      "indexnow_key": "0123456789abcdef",
      "brand": "Example"
    }

Command-line arguments always win over the file. Unknown keys are an error (a typo should not be ignored silently).
"""
import json
import os

DEFAULT_NAME = "geo-visibility.json"
KNOWN_KEYS = ("domain", "paths", "indexnow_key", "brand")


class ConfigError(ValueError):
    """The settings file exists but cannot be used. The message says what to fix."""


def find(path=None, cwd=None):
    """The file to read: an explicit path, else ./geo-visibility.json when it exists, else None."""
    if path:
        return path
    candidate = os.path.join(cwd or os.getcwd(), DEFAULT_NAME)
    return candidate if os.path.isfile(candidate) else None


def load(path=None, cwd=None):
    """Return the settings as a dict ({} when there is no file). Raise ConfigError for an unusable file."""
    found = find(path, cwd)
    if found is None:
        return {}
    try:
        with open(found, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise ConfigError(f"settings file not found: {found}")
    except (OSError, ValueError) as e:
        raise ConfigError(f"{found} is not valid JSON ({e})")
    if not isinstance(data, dict):
        raise ConfigError(f"{found} must contain a JSON object, not {type(data).__name__}")
    unknown = sorted(set(data) - set(KNOWN_KEYS))
    if unknown:
        raise ConfigError(f"{found}: unknown key(s) {', '.join(unknown)}; allowed keys are {', '.join(KNOWN_KEYS)}")
    for key in ("domain", "indexnow_key", "brand"):
        if key in data and (not isinstance(data[key], str) or not data[key].strip()):
            raise ConfigError(f'{found}: "{key}" must be a non-empty string')
    if "paths" in data:
        paths = data["paths"]
        if not isinstance(paths, list) or not all(isinstance(p, str) and p.startswith("/") for p in paths):
            raise ConfigError(f'{found}: "paths" must be a list of URL paths that start with "/"')
    return {k: (v.strip() if isinstance(v, str) else v) for k, v in data.items()}
