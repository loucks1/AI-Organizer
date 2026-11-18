# Categorization contract — drawer inventory

Any categorizer (Muse in chat, Grok via the xAI API, Gemini, GPT, Claude)
returns this JSON for one photo. Same shape regardless of provider, so the
provider can be swapped without touching the database or the MCP server.

## Prompt to give the categorizer

> Look at this photo of a drawer / shelf / box. List every distinct item
> or group you can identify. For each, give: a short name, a category,
> a few search tags, a rough quantity estimate (never pretend precision —
> "~30", "a handful", "1" are fine; say "unknown" rather than guessing),
> a confidence 0–1, and a bounding box as fractions of the photo
> (x, y, width, height, each 0–1, origin top-left) marking where the item
> sits. If a bin is too jumbled to call, say so in `notes` instead of
> hallucinating an inventory. The user's hint, if any, is authoritative
> for sizes and counts: file the item under the user's label.

## JSON schema

```json
{
  "items": [
    {
      "name": "Torx bit set",
      "category": "hand tools",
      "tags": ["torx", "bits", "driver"],
      "quantity_estimate": "1 set",
      "confidence": 0.9,
      "bbox": [0.05, 0.10, 0.30, 0.25],
      "notes": "in the red case, top left"
    }
  ]
}
```

- `bbox` is `[x, y, w, h]`, fractions of photo width/height, origin top-left.
- `quantity_estimate` is a string — "~30", "a handful", "unknown" are all valid.
- Omit an item you can't identify rather than guessing; use `notes` for
  "too jumbled to call" bins.
- The capture hint (e.g. "left bin is M5 bolts, ~30") overrides visual
  guessing for sizes, thread pitch, resistor values, and counts.

## Filing it

```sh
python3 categorize.py --photo-id <id> --json categorization.json --categorizer muse
# --categorizer: muse | grok | gemini | gpt | claude | ...
```

`categorize.py` validates the JSON (bbox values in 0–1, confidence in
0–1), inserts one row per item, and marks the photo `categorized`.
Re-running categorization for a photo replaces its items — the original
photo file is never modified.
