"""Ask Claude to triage a sender list. Sends only domain, count, and up to
three subject lines per sender — the minimum needed to make a call."""
import json

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from .config import settings

SYSTEM = """You help people clean up an overflowing personal Gmail inbox.
You will receive a JSON list of senders with a count of recent messages and a few subject lines.
For each sender, decide one action:
- "keep": personal correspondence, financial/legal/medical records, receipts worth retaining, accounts they clearly still use
- "unsubscribe": marketing, newsletters, or notifications they likely no longer want — the sender is legitimate, they just get too much
- "trash": pure noise — expired promotions, spammy senders, dead services
Be conservative: when a sender could plausibly matter (banks, employers, government, schools, doctors), choose "keep".
Respond with ONLY a JSON array, no prose, no code fences. Each item: {"address": str, "action": "keep"|"unsubscribe"|"trash", "reason": str (max 12 words)}"""


class SenderIn(BaseModel):
    address: str
    domain: str
    count: int
    subjects: list[str]


class Suggestion(BaseModel):
    address: str
    action: str
    reason: str


async def suggest(senders: list[SenderIn]) -> list[Suggestion]:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    payload = [s.model_dump() for s in senders]
    msg = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=4000,
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(payload)}],
    )
    text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return [Suggestion(**item) for item in json.loads(text)]
