import json
from typing import Any, Dict

def parse_output(task: str, raw: str) -> Dict[str, Any]:
    """
    Convert CLI output → structured JSON.
    You can extend this for more tasks.
    """
    if task in ["app_list", "build_list", "summary_report"]:
        # If output is JSON already
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

    # Fallback: plain text mode
    return {"raw_output": raw}