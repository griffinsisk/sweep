"""Cleanup presets. Each is a plain Gmail search query — the same thing
you'd type in the Gmail search bar, so users can verify a preset before
running it."""
from pydantic import BaseModel


class Preset(BaseModel):
    key: str
    label: str
    query: str
    hint: str


PRESETS: list[Preset] = [
    Preset(
        key="before-2020",
        label="Everything before 2020",
        query="before:2020/01/01 in:anywhere",
        hint="The single biggest win for an old inbox. Excludes nothing — check Starred first.",
    ),
    Preset(
        key="attachments-25m",
        label="Attachments over 25 MB",
        query="has:attachment larger:25M",
        hint="A few dozen of these can be gigabytes.",
    ),
    Preset(
        key="attachments-10m",
        label="Attachments over 10 MB",
        query="has:attachment larger:10M",
        hint="Videos, photo dumps, big PDFs.",
    ),
    Preset(
        key="promotions-1y",
        label="Promotions older than a year",
        query="category:promotions older_than:1y",
        hint="Sales you already missed.",
    ),
    Preset(
        key="social-1y",
        label="Social notifications older than a year",
        query="category:social older_than:1y",
        hint="Someone liked your post in 2019.",
    ),
    Preset(
        key="updates-1y",
        label="Updates and receipts older than a year",
        query="category:updates older_than:1y",
        hint="Shipping confirmations, password resets. Skip if you keep receipts for taxes.",
    ),
    Preset(
        key="noreply-1y",
        label="No-reply senders older than a year",
        query="(from:noreply OR from:no-reply OR from:donotreply) older_than:1y",
        hint="If they didn't want a reply, you probably don't need a record.",
    ),
]

PRESET_INDEX = {p.key: p for p in PRESETS}
