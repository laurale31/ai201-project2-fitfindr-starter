"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Parse a natural language query into structured search parameters using regex.

    Extracts:
        description (str):  The item the user wants, with price/size phrases stripped out.
        size (str | None):  A clothing size if mentioned (XS, S, M, L, XL, XXS, XXL, etc.)
        max_price (float | None): A dollar amount if mentioned (e.g. "under $30", "$30 or less")

    Examples:
        "vintage graphic tee under $30, size M"
            → {"description": "vintage graphic tee", "size": "M", "max_price": 30.0}
        "looking for a denim jacket"
            → {"description": "denim jacket", "size": None, "max_price": None}
    """
    # --- Extract max_price ---
    # Matches: "under $30", "less than $30", "$30 or less", "max $30", "up to $30", "for $30"
    price_patterns = [
        r"(?:under|below|less than|max|maximum|up to|for|around)\s*\$?([\d]+(?:\.\d+)?)",
        r"\$?([\d]+(?:\.\d+)?)\s*(?:or less|max|maximum|and under)",
    ]
    max_price = None
    for pattern in price_patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            max_price = float(match.group(1))
            break

    # --- Extract size ---
    # Matches: "size M", "size: L", "in XL", "XS" as a standalone word
    size_pattern = r"\b(?:size[:\s]+)?(?<!\w)(XXS|XS|S/M|M/L|XS/S|L/XL|XXL|XL|X+S|X+L|[SMLX]{1,3})\b"
    size_match = re.search(size_pattern, query, re.IGNORECASE)
    size = size_match.group(1).upper() if size_match else None

    # --- Extract description ---
    # Remove price phrases and size phrases to isolate the item description
    description = query

    # Strip price phrases
    description = re.sub(
        r"(?:under|below|less than|max|maximum|up to|for|around)\s*\$?[\d]+(?:\.\d+)?",
        "", description, flags=re.IGNORECASE
    )
    description = re.sub(
        r"\$?[\d]+(?:\.\d+)?\s*(?:or less|max|maximum|and under)",
        "", description, flags=re.IGNORECASE
    )

    # Strip size phrases
    description = re.sub(
        r"\b(?:size[:\s]+)?(?:XXS|XS|S/M|M/L|XS/S|L/XL|XXL|XL|X+S|X+L|[SMLX]{1,3})\b",
        "", description, flags=re.IGNORECASE
    )

    # Strip common filler phrases
    filler = [
        r"\blooking for\b", r"\bi(?:'m| am) looking for\b", r"\bfind me\b",
        r"\bi want\b", r"\bcan you find\b", r"\bsearch for\b",
        r"\bdesigner\b(?!\s+\w+\s+brand)",  # keep "designer" only if describing style
        r"\bsome\b", r"\ba\b", r"\ban\b", r"\bthe\b",
    ]
    for f in filler:
        description = re.sub(f, "", description, flags=re.IGNORECASE)

    # Clean up extra spaces, commas, punctuation
    description = re.sub(r"[,;]+", " ", description)
    description = re.sub(r"\s{2,}", " ", description).strip(" ,.")

    return {
        "description": description if description else query,
        "size": size,
        "max_price": max_price,
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query into structured parameters
    parsed = _parse_query(query)
    session["parsed"] = parsed

    description = parsed["description"]
    size = parsed["size"]
    max_price = parsed["max_price"]

    # Step 3: Search for listings
    results = search_listings(description, size, max_price)
    session["search_results"] = results

    # If no results → set error and return early. Do NOT call suggest_outfit.
    if not results:
        session["error"] = (
            "No listings found for your search. "
            "Try a broader description, a higher price limit, or leave the size blank."
        )
        return session

    # Step 4: Select the top result
    session["selected_item"] = results[0]

    # Step 5: Suggest an outfit
    outfit_suggestion = suggest_outfit(session["selected_item"], wardrobe)
    session["outfit_suggestion"] = outfit_suggestion

    # If suggest_outfit returned its error string → set error and return early
    if outfit_suggestion.startswith("Outfit suggestion unavailable"):
        session["error"] = outfit_suggestion
        return session

    # Step 6: Generate the fit card
    fit_card = create_fit_card(outfit_suggestion, session["selected_item"])
    session["fit_card"] = fit_card

    # Step 7: Return the completed session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")