# FitFindr

A multi-tool AI agent that helps users find secondhand clothing and figure out how to wear it. Given a natural language query, FitFindr searches a mock thrift dataset, suggests outfit combinations using the user's wardrobe, and generates a shareable social-media caption — all in one flow.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Mac/Linux
# or: .venv\Scripts\activate     # Windows

pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_key_here
```

Get a free key at [console.groq.com](https://console.groq.com) — no credit card required.

Run the app:

```bash
python app.py
```

Open the URL shown in your terminal (usually `http://localhost:7860`).

---

## Tool Inventory

### `search_listings(description: str, size: str | None, max_price: float | None) → list[dict]`

Searches `data/listings.json` for secondhand items matching the user's request. Applies hard filters for price and size first, then scores surviving listings by keyword overlap between the description and each listing's title, description, style tags, colors, brand, and category. Items with zero keyword matches are dropped. Returns a list of matching listing dicts sorted by relevance score, best match first. Returns an empty list `[]` if nothing matches — never raises an exception.

Each returned dict contains: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str), `platform` (str).

### `suggest_outfit(new_item: dict, wardrobe: dict) → str`

Calls the Groq LLM (`llama-3.3-70b-versatile`) to suggest one or two complete outfit combinations using the new item and the user's existing wardrobe. If the wardrobe is empty (`wardrobe["items"] == []`), the tool detects this and asks the LLM for general styling advice based on the item's style tags and colors instead — it does not crash or return an empty string. Returns a non-empty string in a friendly, conversational tone. On API failure, returns a specific error string (beginning with `"Outfit suggestion unavailable"`) rather than raising an exception.

### `create_fit_card(outfit: str, new_item: dict) → str`

Calls the Groq LLM to generate a 2–3 sentence Instagram/TikTok-style caption for the thrifted outfit. Uses temperature `1.1` so outputs vary meaningfully across calls on the same input. References the item's title, price, and platform naturally within the caption. Guards against an empty `outfit` argument before making any API call — returns a descriptive error string immediately if `outfit` is empty or whitespace-only.

---

## How the Planning Loop Works

The planning loop lives in `run_agent()` in `agent.py`. It is not a fixed sequence — it branches based on what each tool returns.

**Step 1 — Parse the query.** A regex-based `_parse_query()` function extracts three things from the user's natural language input: a dollar amount (`"under $30"` → `30.0`), a clothing size (`"size M"` → `"M"`), and an item description (the query after stripping price and size phrases). This runs without calling the LLM, keeping it fast and free.

**Step 2 — Search.** `search_listings()` is called with the parsed parameters. If it returns an empty list, the agent sets `session["error"]` to a helpful message and returns immediately. `suggest_outfit` and `create_fit_card` are never called with empty input — this is the key branch that makes the loop conditional rather than fixed.

**Step 3 — Suggest outfit.** If results were found, the top result (`results[0]`) is stored in `session["selected_item"]` and passed to `suggest_outfit()`. If `suggest_outfit` returns its error string (detected by checking the string prefix), the agent sets `session["error"]` and returns early again.

**Step 4 — Generate fit card.** Only reached if both previous tools succeeded. `create_fit_card()` receives `session["outfit_suggestion"]` and `session["selected_item"]` and its output is stored in `session["fit_card"]`.

**Step 5 — Return.** The completed session dict is returned. The caller checks `session["error"]` first; if it's `None`, all three output fields are populated.

---

## State Management

A single `session` dict is created at the start of each `run_agent()` call and passed through the entire interaction. It holds:

- `session["query"]` — the original user query, stored immediately
- `session["parsed"]` — the structured output of `_parse_query()`: description, size, max_price
- `session["search_results"]` — the full list returned by `search_listings()`
- `session["selected_item"]` — `results[0]`, the exact dict object passed into `suggest_outfit()`
- `session["outfit_suggestion"]` — the string returned by `suggest_outfit()`, passed unchanged into `create_fit_card()`
- `session["fit_card"]` — the final caption string returned by `create_fit_card()`
- `session["error"]` — set to a message string if any tool hits its failure mode; `None` on success

Tools receive state as direct function arguments — they do not read the session dict themselves. Only the planning loop reads and writes the session. This keeps each tool independently testable: you can call `suggest_outfit()` directly in a terminal without needing a session object.

---

## Error Handling

| Tool | Failure mode | What the agent does |
|------|-------------|---------------------|
| `search_listings` | No listings match filters | Sets `session["error"] = "No listings found for your search. Try a broader description, a higher price limit, or leave the size blank."` Returns session immediately. `suggest_outfit` is never called. |
| `suggest_outfit` | `wardrobe["items"]` is empty | Sends a different LLM prompt asking for general styling advice. Returns a useful string — does not crash or return empty. |
| `suggest_outfit` | LLM API call raises an exception | Catches the exception, returns `"Outfit suggestion unavailable right now — try describing your wardrobe and I can suggest combinations manually."` The planning loop detects this prefix and exits early. |
| `create_fit_card` | `outfit` is empty or whitespace | Returns `"Fit card could not be generated — outfit description was missing. Please try the full flow again."` without calling the API. |
| `create_fit_card` | LLM API call raises an exception | Catches the exception, returns `"Fit card generation failed. Try again in a moment."` |

**Concrete example from testing** — triggering the no-results error path:

```bash
python3 -c "
from agent import run_agent
from utils.data_loader import get_example_wardrobe
session = run_agent('designer ballgown size XXS under \$5', get_example_wardrobe())
print(session['error'])
print(session['selected_item'])   # None — never set
print(session['fit_card'])        # None — never set
"
```

Output:
```
No listings found for your search. Try a broader description, a higher price limit, or leave the size blank.
None
None
```

**Concrete example from testing** — triggering the empty-outfit guard in `create_fit_card`:

```bash
python3 -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
```

Output:
```
Fit card could not be generated — outfit description was missing. Please try the full flow again.
```

---

## Spec Reflection

**One way the spec helped:** Writing the planning loop in plain conditional language in `planning.md` before touching `agent.py` made the implementation nearly mechanical. Each "if/else" in the spec translated directly to a branch in `run_agent()`. The error detection logic — checking for `results == []` and checking the suggest_outfit error string prefix — was decided during planning, not during debugging.

**One way implementation diverged:** The spec described query parsing as "parse description, size, and max_price from the user's query" without committing to a method. During implementation, the choice was between calling the LLM to parse or using regex. LLM parsing adds latency and costs an API call before any search happens; regex is instant and free. The implementation uses regex (`_parse_query()` in `agent.py`), which handles every example query correctly. The spec was updated after the fact to document this choice.

---

## AI Usage

**Instance 1 — Implementing `search_listings`**

I gave Claude the Tool 1 block from `planning.md` (input parameters, return value description, failure mode) and asked it to implement the function using `load_listings()` from `utils/data_loader.py`. The generated code had a bug: it used `item.get("brand", "")` to build the searchable text string, but several listings have `brand: null` in the JSON, which makes `get()` return `None` rather than the default `""`. Joining a list containing `None` raises a `TypeError`. I changed every field lookup in that block to use `item.get("field") or ""` instead, which handles both missing keys and explicit `null` values. I verified the fix by running `search_listings("vintage graphic tee", size="M", max_price=30)` and confirming results were returned without errors.

**Instance 2 — Implementing `run_agent`**

I gave Claude the full architecture diagram and the Planning Loop + State Management sections from `planning.md` and asked it to implement `run_agent()`. The generated code called all three tools unconditionally in sequence — it did not branch on the return value of `search_listings`. This violated the spec, which requires the agent to return early when no results are found. I rewrote the control flow to add the `if not results:` early return and the `if outfit_suggestion.startswith("Outfit suggestion unavailable"):` guard, then tested the no-results path explicitly with the ballgown query to confirm the agent exits before calling `suggest_outfit`.