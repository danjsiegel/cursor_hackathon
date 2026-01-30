# System prompts

Prompt templates live here as `.txt` files. Use **`.format()`-style placeholders** like `{user_env}`, `{goal}`, `{thought}` so `app.py` can inject values when calling the API.

## Usage in code

```python
from prompts import load, format_prompt

template = load("main_agent_system")  # loads prompts/main_agent_system.txt
text = format_prompt(template, user_context_line="\n**User context:** macOS; Firefox\n", first_step_extra="", example_response="")
```

## Placeholders by file

| File | Placeholders |
|------|--------------|
| `main_agent_system.txt` | `{user_context_line}`, `{first_step_extra}`, `{example_response}` |
| `main_agent_first_step_extra.txt` | (none – loaded as block when first step) |
| `main_agent_user.txt` | `{goal}`, `{history_block}`, `{json_keys_suffix}` |
| `validate_goal_system.txt` | `{user_context_line}` |
| `validate_goal_user.txt` | `{goal}`, `{user_context_block}` |
| `verify_step_system.txt` | `{user_context_line}` |
| `verify_step_user.txt` | `{intended_thought}`, `{user_context_block}` |
| `translate_step_system.txt` | `{user_context_line}` |
| `translate_step_user.txt` | `{step_description}` |

Any placeholder not passed to `format_prompt()` is replaced with an empty string. Edit the `.txt` files to change copy; keep placeholder names the same or update `app.py` to pass the new names.
