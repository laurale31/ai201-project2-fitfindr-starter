"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    # Step 1: Load all listings
    listings = load_listings()

    # Step 2: Filter by max_price and size
    filtered = []
    for item in listings:
        # Price filter
        if max_price is not None and item.get("price", 0) > max_price:
            continue
        # Size filter (case-insensitive substring match so "M" matches "S/M")
        if size is not None:
            item_size = item.get("size", "").lower()
            if size.lower() not in item_size:
                continue
        filtered.append(item)

    # Step 3: Score each remaining listing by keyword overlap with description
    # Split description into lowercase words, ignoring short filler words
    stopwords = {"a", "an", "the", "and", "or", "for", "of", "in", "with", "that", "is"}
    keywords = [
        word.strip(".,!?").lower()
        for word in description.split()
        if word.strip(".,!?").lower() not in stopwords and len(word) > 1
    ]

    scored = []
    for item in filtered:
        # Build a single searchable text blob from relevant fields
        searchable = " ".join([
            item.get("title") or "",
            item.get("description") or "",
            item.get("category") or "",
            item.get("brand") or "",
            " ".join(item.get("style_tags") or []),
            " ".join(item.get("colors") or []),
        ]).lower()

        score = sum(1 for kw in keywords if kw in searchable)
        if score > 0:
            scored.append((score, item))

    # Step 4 & 5: Drop zero-score listings, sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offers general styling advice for the item.
    """
    try:
        client = _get_groq_client()

        # Format the new item details for the prompt
        item_details = (
            f"Title: {new_item.get('title', 'Unknown item')}\n"
            f"Description: {new_item.get('description', '')}\n"
            f"Style tags: {', '.join(new_item.get('style_tags', []))}\n"
            f"Colors: {', '.join(new_item.get('colors', []))}\n"
            f"Condition: {new_item.get('condition', '')}\n"
            f"Brand: {new_item.get('brand', '')}\n"
            f"Category: {new_item.get('category', '')}"
        )

        # Step 1 & 2: Handle empty wardrobe
        wardrobe_items = wardrobe.get("items", [])

        if not wardrobe_items:
            prompt = f"""You are a knowledgeable and friendly secondhand fashion stylist.

A user is considering buying this thrifted item:
{item_details}

They haven't told you what else is in their wardrobe. Based on the item's style, colors, and vibe, suggest 1-2 general outfit ideas — describe the types of pieces that would pair well with it (e.g., "wide-leg jeans," "chunky sneakers," "a simple white tee"). Keep it specific, practical, and conversational — like advice from a stylish friend, not a fashion magazine. 2-4 sentences."""

        else:
            # Step 3: Format wardrobe items for the prompt
            wardrobe_lines = []
            for w_item in wardrobe_items:
                parts = []
                if w_item.get("type"):
                    parts.append(w_item["type"])
                if w_item.get("color"):
                    parts.append(f"({w_item['color']})")
                if w_item.get("style"):
                    parts.append(f"— {w_item['style']}")
                if w_item.get("description"):
                    parts.append(f": {w_item['description']}")
                wardrobe_lines.append(" ".join(parts))

            wardrobe_text = "\n".join(f"- {line}" for line in wardrobe_lines)

            prompt = f"""You are a knowledgeable and friendly secondhand fashion stylist.

A user is considering buying this thrifted item:
{item_details}

Their current wardrobe includes:
{wardrobe_text}

Suggest 1-2 specific outfit combinations using the new item and named pieces from their wardrobe. Be concrete (e.g., "Pair this with your wide-leg black jeans and chunky sneakers"). Add 1-2 styling tips (tucking, layering, cuffing, etc.). Keep the tone friendly and direct — like advice from a stylish friend. 3-5 sentences total."""

        # Step 4: Call the LLM and return the response
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        return (
            "Outfit suggestion unavailable right now — try describing your wardrobe "
            "and I can suggest combinations manually."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, returns a descriptive error message
        string — does NOT raise an exception.
    """
    # Step 1: Guard against empty or whitespace-only outfit string
    if not outfit or not outfit.strip():
        return (
            "Fit card could not be generated — outfit description was missing. "
            "Please try the full flow again."
        )

    try:
        client = _get_groq_client()

        # Pull item details for a specific, personal caption
        title = new_item.get("title", "this find")
        price = new_item.get("price", "")
        platform = new_item.get("platform", "")
        style_tags = ", ".join(new_item.get("style_tags", []))

        price_str = f"${price:.2f}" if isinstance(price, (int, float)) else str(price)

        # Step 2: Build the prompt
        prompt = f"""You are writing an Instagram or TikTok caption for a thrift outfit post.

The thrifted item: "{title}" bought for {price_str} on {platform}.
Style vibe: {style_tags}

The outfit: {outfit}

Write a caption that:
- Sounds like a real person posting their OOTD (casual, lowercase, authentic)
- Mentions the item name, price, and platform naturally — once each
- Captures the outfit vibe in specific terms, not generic praise
- Is 2-3 sentences long
- Can include 1-2 relevant emojis if they feel natural
- Does NOT sound like an advertisement or product description

Write only the caption. No quotes, no explanation."""

        # Step 3: Call the LLM with higher temperature for variety
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=1.1,
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        return "Fit card generation failed. Try again in a moment."