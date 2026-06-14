# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset (data/listings.json) and returns a list of items that match the user's description, size, and maximum price. It scores each listing for relevance by checking how many of the description's keywords appear in the listing's title, description, and style_tags fields.

**Input parameters:**
- `description` (str): A natural-language description of the item the user wants (e.g., "vintage graphic tee"). Used to keyword-match against listing title, description, and style_tags.
- `size` (str | None): The clothing size to filter by (e.g., "M", "L", "XS"). If None or not provided, size filtering is skipped and all sizes are returned.
- `max_price` (float | None): The maximum price the user is willing to pay. Listings with a price strictly greater than this value are excluded. If None, no price cap is applied.

**What it returns:**
A list of dicts, where each dict is a listing with at least these fields: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list of str), `size` (str), `condition` (str), `price` (float), `colors` (list of str), `brand` (str), `platform` (str). The list is sorted by relevance score (most relevant first). Returns an empty list `[]` if no listings match — never raises an exception.

**What happens if it fails or returns nothing:**
If the returned list is empty, the agent stores `session["error"] = "No listings found for your search. Try a broader description, a higher price, or leave the size blank."` and returns immediately — it does NOT call suggest_outfit or create_fit_card with empty input.
---

### Tool 2: suggest_outfit

**What it does:**
Given a specific secondhand item and the user's current wardrobe, calls the Groq LLM (llama-3.3-70b-versatile) to suggest one or more complete outfit combinations using the new item plus existing wardrobe pieces. Returns a styled, conversational outfit suggestion as a string.

**Input parameters:**
- `new_item` (dict): A single listing dict (as returned by search_listings) representing the item the user is considering buying. Must have at least `title`, `description`, `style_tags`, `colors`, and `condition`.
- `wardrobe` (dict): The user's existing wardrobe in the format defined by data/wardrobe_schema.json. Contains a key `"items"` which is a list of wardrobe item dicts, each with fields like `type`, `color`, `style`, and `description`. May be empty (items list has length 0).

**What it returns:**
A non-empty string containing one or more outfit suggestions — specific pairings (e.g., "Pair this with your white straight-leg jeans and chunky white sneakers") plus brief styling notes (e.g., "tuck the front for shape, leave the sleeves cuffed"). The tone is friendly and direct, like advice from a knowledgeable friend.

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty, the tool does NOT crash — it prompts the LLM with a note that the wardrobe is empty and asks for general styling advice for the item based on its style_tags and colors. If the LLM call fails (network error or API exception), the tool catches the exception and returns the string: `"Outfit suggestion unavailable right now — try describing your wardrobe and I can suggest combinations manually."`

---

### Tool 3: create_fit_card

**What it does:**
Calls the Groq LLM (llama-3.3-70b-versatile) to generate a short, shareable outfit caption — the kind of thing someone would post as an Instagram or TikTok caption — based on the outfit suggestion and the new item. Each call should produce a meaningfully different result.

**Input parameters:**
- `outfit` (str): The full outfit suggestion string returned by suggest_outfit. If this is an empty string or None, the tool returns an error string without calling the LLM.
- `new_item` (dict): The listing dict for the item being styled. Used to pull in specific details like platform, price, brand, and title to make the caption feel personal and specific.

**What it returns:**
A string of 1–3 sentences in a casual, social-media-native voice (lowercase, maybe an emoji or two, no formal punctuation). The caption references the specific item (platform, price, vibe) and the outfit combination. Example: `"thrifted this faded band tee off depop for $22 and honestly it was made for my wide-legs 🖤 full look in my stories"`

**What happens if it fails or returns nothing:**
If `outfit` is empty or None, the tool immediately returns: `"Fit card could not be generated — outfit description was missing. Please try the full flow again."` without calling the LLM. If the LLM call raises an exception, catch it and return: `"Fit card generation failed. Try again in a moment."`

---

### Additional Tools (if any)

None for the base implementation. 

---

## Planning Loop

**How does your agent decide which tool to call next?**
The planning loop in `run_agent()` follows this explicit conditional logic:
 
1. **Always start with search_listings.** Call `search_listings(description, size, max_price)` using values parsed from the user's query (or passed directly as arguments).
2. **Check the result of search_listings:**
   - If `results == []` (empty list): set `session["error"] = "No listings found..."`, set `session["selected_item"] = None`, and **return the session immediately**. Do NOT proceed to step 3.
   - If `len(results) > 0`: set `session["selected_item"] = results[0]` (the top-ranked match) and proceed to step 3.
3. **Call suggest_outfit** with `session["selected_item"]` and the wardrobe passed into `run_agent()`. Store the result in `session["outfit_suggestion"]`.
4. **Check the result of suggest_outfit:**
   - If `session["outfit_suggestion"]` starts with `"Outfit suggestion unavailable"` (the error string): set `session["error"] = session["outfit_suggestion"]` and **return the session**. Do NOT call create_fit_card with a failure message.
   - Otherwise: proceed to step 5.
5. **Call create_fit_card** with `session["outfit_suggestion"]` and `session["selected_item"]`. Store the result in `session["fit_card"]`.
6. **Return the session.** The session now contains `selected_item`, `outfit_suggestion`, and `fit_card` (or `error` if something failed early).
The agent knows it's done when either: (a) it hits an error branch and returns early, or (b) it completes step 5 and all three session fields are populated.

---

## State Management

**How does information from one tool get passed to the next?**
A single `session` dict is created at the start of each `run_agent()` call and passed through the entire flow. It holds:
 
- `session["query"]` (str): The original user query, stored at the start.
- `session["selected_item"]` (dict | None): Set after search_listings runs. This exact dict object is passed into suggest_outfit — no re-fetching or re-parsing.
- `session["outfit_suggestion"]` (str | None): Set after suggest_outfit runs. This exact string is passed into create_fit_card.
- `session["fit_card"]` (str | None): Set after create_fit_card runs. This is the final output shown to the user.
- `session["error"]` (str | None): Set if any tool hits its failure mode. The UI checks for this key to display the error message in place of normal output.
All values start as `None`. Tools receive state values as direct function arguments (not by reading the session dict themselves) — only the planning loop reads and writes the session dict. This keeps tools testable in isolation.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.
 
| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No listings match the description, size, and price filters — returns `[]` | Agent sets `session["error"] = "No listings found for your search. Try a broader description, a higher price limit, or leave the size field blank."` and returns early. suggest_outfit and create_fit_card are never called. |
| suggest_outfit | `wardrobe["items"]` is empty (user has no wardrobe items on file) | Tool detects the empty items list and prompts the LLM for general styling advice based on the item's style_tags and colors alone. Returns a useful suggestion string — does not crash or return empty. |
| suggest_outfit | LLM API call raises an exception (network error, rate limit, etc.) | Tool catches the exception and returns the string `"Outfit suggestion unavailable right now — try describing your wardrobe and I can suggest combinations manually."` The planning loop detects this string prefix and sets session["error"] instead of proceeding to create_fit_card. |
| create_fit_card | `outfit` argument is an empty string or None | Tool immediately returns `"Fit card could not be generated — outfit description was missing. Please try the full flow again."` without calling the LLM. |
| create_fit_card | LLM API call raises an exception | Tool catches the exception and returns `"Fit card generation failed. Try again in a moment."` |

---

## Architecture

```
User query (description, size, max_price, wardrobe)
    │
    ▼
┌─────────────────────────────────────────────────────┐
│                   Planning Loop                     │
│                   (run_agent)                       │
└─────────────────────────────────────────────────────┘
    │
    ▼
search_listings(description, size, max_price)
    │
    ├── results == [] ──► session["error"] = "No listings found..."
    │                              │
    │                              ▼
    │                         RETURN SESSION (early exit)
    │
    └── results = [item, ...] ──► session["selected_item"] = results[0]
                                           │
                                           ▼
                            suggest_outfit(selected_item, wardrobe)
                                           │
                    ┌──────────────────────┴──────────────────────┐
                    │                                             │
              wardrobe empty                               wardrobe has items
                    │                                             │
                    ▼                                             ▼
          LLM prompt: general                          LLM prompt: outfit using
          styling advice for item                      wardrobe items + new item
                    │                                             │
                    └──────────────────┬──────────────────────────┘
                                       │
                                       ▼
                          session["outfit_suggestion"] = result
                                       │
                    ┌──────────────────┴────────────────────────┐
                    │                                           │
              LLM failed                                   LLM succeeded
              (error string)                               (useful string)
                    │                                           │
                    ▼                                           ▼
           session["error"] = result              create_fit_card(outfit_suggestion,
           RETURN SESSION (early exit)                          selected_item)
                                                               │
                                                ┌──────────────┴──────────────┐
                                                │                             │
                                          outfit empty                   outfit present
                                          or LLM failed                       │
                                                │                             ▼
                                                ▼                  session["fit_card"] = result
                                       return error string                    │
                                                                              ▼
                                                                     RETURN SESSION
                                                                  (all 3 fields populated)
```
---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**
 
- **search_listings:** I'll paste the Tool 1 spec block (inputs, return value, failure mode) into Claude and ask it to implement `search_listings()` in tools.py using `load_listings()` from `utils/data_loader.py`. I'll tell it not to re-implement file loading. Before running it, I'll check: (1) does it filter by all three parameters? (2) does it return `[]` on no match rather than raising? (3) does it sort by relevance? I'll test with 3 queries: a broad match, a size-filtered match, and an impossible query that should return `[]`.
- **suggest_outfit:** I'll paste the Tool 2 spec block into Claude and ask it to implement `suggest_outfit()` using the Groq Python SDK with model `llama-3.3-70b-versatile` and the `GROQ_API_KEY` from `.env` (loaded via python-dotenv). I'll explicitly tell it to handle the `wardrobe["items"] == []` case and wrap the API call in try/except. I'll verify by running it once with `get_example_wardrobe()` and once with `get_empty_wardrobe()`.
- **create_fit_card:** I'll paste the Tool 3 spec block into Claude and ask it to implement `create_fit_card()` with temperature set to 1.0 or higher to ensure variety. I'll run it 3 times on the same input and check that the outputs differ. I'll also test with `outfit=""` to verify it returns the error string rather than calling the API.
**Milestone 4 — Planning loop and state management:**
 
I'll paste the full Architecture diagram plus the Planning Loop and State Management sections from this file into Claude and ask it to implement `run_agent()` in agent.py. I'll tell it the function signature is already in place and it should follow the numbered logic in the Planning Loop section exactly. Before running it, I'll check: (1) does it branch on `results == []`? (2) does it store values in the `session` dict between calls? (3) does it ever call suggest_outfit when results is empty? I'll test the happy path and the no-results path explicitly.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The agent parses the query and calls `search_listings(description="vintage graphic tee", size=None, max_price=30.0)`. The tool loads all listings from data/listings.json, scores each one by checking how many words from "vintage graphic tee" appear in the listing's title, description, and style_tags, and filters out any item with price > 30.0. It returns a ranked list of matching items. The top result is: `{"id": "L004", "title": "Faded Band Tee", "price": 22.0, "platform": "Depop", "condition": "Good", "size": "M", "style_tags": ["vintage", "graphic", "band tee", "grunge"], "colors": ["black", "grey"]}`. The planning loop sets `session["selected_item"] = results[0]` and proceeds.
 
**Step 2:**
The agent calls `suggest_outfit(new_item=session["selected_item"], wardrobe=get_example_wardrobe())`. The wardrobe contains items like wide-leg jeans (black), chunky white sneakers, and an oversized denim jacket. The tool builds a prompt that includes the new item's details and the wardrobe contents, then calls the Groq LLM. The LLM returns: `"Pair this faded band tee with your wide-leg black jeans and chunky sneakers for a classic 90s grunge look. Tuck just the front corner of the tee for a little shape, and layer the oversized denim jacket on top for cooler days."` The planning loop sets `session["outfit_suggestion"]` to this string.
 
**Step 3:**
The agent calls `create_fit_card(outfit=session["outfit_suggestion"], new_item=session["selected_item"])`. The tool builds a prompt asking the LLM to write an Instagram-style caption referencing the item's platform (Depop), price ($22), and the outfit combination. The LLM returns: `"thrifted this faded band tee off depop for $22 and it literally completes my whole wardrobe 🖤 wide-legs + chunky sneakers = forever look"`. The planning loop sets `session["fit_card"]` to this string.
 
**Final output to user:**
The Gradio UI displays three panels:
- **Found item:** "Faded Band Tee — $22 on Depop, Good condition, Size M"
- **Outfit suggestion:** "Pair this faded band tee with your wide-leg black jeans and chunky sneakers for a classic 90s grunge look. Tuck just the front corner of the tee for a little shape, and layer the oversized denim jacket on top for cooler days."
- **Fit card:** "thrifted this faded band tee off depop for $22 and it literally completes my whole wardrobe 🖤 wide-legs + chunky sneakers = forever look"
**Error path example:**
If the user searches for "designer ballgown" with size "XXS" and max_price 5.0, search_listings returns `[]`. The agent sets `session["error"] = "No listings found for your search. Try a broader description, a higher price limit, or leave the size field blank."` and returns immediately. The UI displays the error message. suggest_outfit and create_fit_card are never called.
