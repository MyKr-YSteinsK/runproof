"""Metadata-only SDK admission probe. No SDK imports or ambient credentials."""
import importlib.metadata
import json
import sys


def preflight():
    if not sys.flags.isolated:
        return {"status": "SDK_UNAVAILABLE", "reason": "ISOLATED_PYTHON_REQUIRED", "sdk_calls": 0}
    installed = {}
    for name in ("openai", "pydantic-ai-slim", "pydantic-ai"):
        try:
            installed[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    return {"status": "SDK_UNAVAILABLE",
            "reason": "SDK_IDENTITY_AND_TRANSPORT_NOT_ADMITTED" if installed else "NO_SDK_IN_ISOLATED_INTERPRETER",
            "observed_versions": installed, "sdk_calls": 0}


if __name__ == "__main__":
    print(json.dumps(preflight(), sort_keys=True))
