import json
from typing import Dict, Any, List
import jinja2

def render_template(template_str: str, context: Dict[str, Any]) -> str:
    """
    Renders a standard jinja template string with the provided context dictionary.
    """
    # Create Jinja environment that ignores missing variables (renders them as empty)
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    try:
        template = env.from_string(template_str)
        return template.render(**context)
    except Exception as e:
        # If strict fails or template syntax is invalid, return original string
        # Robust implementations handle this more gracefully
        return template_str

def render_dict(data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively finds strings in a dictionary and renders them using Jinja.
    """
    if not isinstance(data, dict):
        return data

    result = {}
    for k, v in data.items():
        if isinstance(v, dict):
            result[k] = render_dict(v, context)
        elif isinstance(v, list):
            result[k] = [render_dict(i, context) if isinstance(i, dict) else (render_template(str(i), context) if isinstance(i, str) else i) for i in v]
        elif isinstance(v, str):
            result[k] = render_template(v, context)
        else:
            result[k] = v
    return result

def extract_variables(run_id: str, tenant_id: str, env: str, custom_inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Returns the base execution context."""
    from datetime import datetime, timezone
    
    context = {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "env": env,
        "now": datetime.now(timezone.utc).isoformat(),
        "steps": {}, # Stores outputs of successful steps
    }
    
    if custom_inputs:
        context.update(custom_inputs)
        
    return context
