import json
import logging
import anthropic
from app import config

log = logging.getLogger(__name__)
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


SYSTEM = """You parse SMS messages for a real estate lead capture tool. The user texts addresses of properties they spot while driving, or commands to manage existing leads.

Return ONLY valid JSON. No markdown, no explanation.

Two message types:

1. CAPTURE — contains a property street address, possibly with condition notes and flags.
Flags: -ns (no skip trace), -nc (no campaign), -hot (start immediately)
Return:
{"type":"capture","address":"<street number and name only>","city":"<default Seattle>","state":"<default WA>","zip":"<infer zip code from the address when possible, else empty>","notes":"<condition observations about the property>","flags":["-ns"]}
The user operates in Seattle, WA. Always default city to Seattle and state to WA unless specified otherwise. Infer the 5-digit zip code from the street address when you can.

2. COMMAND — starts with a keyword: done, skip, start, kill, status, note, help
Return:
{"type":"command","command":"<keyword>","address_fragment":"<partial address for matching>","action_name":"<for done, e.g. letter 1>","note_text":"<for note command>"}

For "done letter 1 1234 Main": command=done, action_name=letter 1, address_fragment=1234 Main
For "note 1234 Main called owner no answer": address_fragment=1234 Main, note_text=called owner no answer
For "help": command=help, no other fields needed.

3. If you truly cannot parse the message: {"type":"unknown"}"""


def parse_sms(body: str) -> dict:
    """Parse an SMS body into a structured dict using Claude Haiku."""
    response = _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=SYSTEM,
        messages=[{"role": "user", "content": body}],
    )
    text = response.content[0].text.strip()

    # Strip markdown fences if Haiku wraps them
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log.error("Failed to parse LLM response: %s", text)
        return {"type": "unknown"}
