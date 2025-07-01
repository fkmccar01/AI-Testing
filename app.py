import re
from flask import Flask, request
import os
import requests
import json
import random

app = Flask(__name__)

GROUPME_BOT_ID = os.environ.get("GROUPME_BOT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

# Load static responses
with open("responses.json", "r") as f:
    RESPONSES = json.load(f)

# Load profiles
with open("profiles.json", "r") as pf:
    PROFILES = json.load(pf)

# Define emoji stripping pattern for trophy icons (🏆 and 🥄)
EMOJI_PATTERN = re.compile(r"[\U0001F3C6\U0001F9C4]")

def normalize_name(name: str) -> str:
    """Lowercase, strip trophy emojis and whitespace for consistent matching."""
    return EMOJI_PATTERN.sub("", name).strip().lower()

# Build normalized dictionaries
NAME_TO_PROFILE = {normalize_name(p["name"]): p for p in PROFILES.values()}
ALIAS_TO_PROFILE = {}
for profile in PROFILES.values():
    for alias in profile.get("aliases", []):
        ALIAS_TO_PROFILE[normalize_name(alias)] = profile

def display_nickname(profile):
    aliases = profile.get("aliases", [])
    return aliases[0] if aliases else EMOJI_PATTERN.sub("", profile.get("name", "")).strip()

def format_trophies(trophies):
    if not trophies:
        return "no trophies"
    parts = []
    for key, val in trophies.items():
        key_lower = key.lower()
        if key_lower.startswith("the kzars_kzup"):
            if isinstance(val, list):
                editions = ', '.join(val)
                parts.append(f"Kzar’s Kzup (editions: {editions})")
            else:
                parts.append(f"Kzar’s Kzup (edition: {val})")
        elif isinstance(val, list):
            parts.append(f"{key} ({', '.join(val)})")
        else:
            parts.append(f"{key} ({val})")
    return ", ".join(parts)

def query_gemini(prompt):
    headers = { "Content-Type": "application/json" }
    payload = { "contents": [ { "parts": [ { "text": prompt } ] } ] }
    try:
        response = requests.post(GEMINI_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print("Gemini API error:", e)
        return None

def send_groupme_message(text):
    if not GROUPME_BOT_ID:
        print("GROUPME_BOT_ID not set!")
        return False
    try:
        payload = {"bot_id": GROUPME_BOT_ID, "text": text}
        resp = requests.post("https://api.groupme.com/v3/bots/post", json=payload)
        print(f"GroupMe response: {resp.status_code}")
        return resp.status_code in (200, 202)
    except Exception as e:
        print("Error sending to GroupMe:", e)
        return False

@app.route("/")
def index():
    return "GreggBot is live", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if not data:
        return "", 200

    sender_raw = data.get("name", "")
    text = data.get("text", "")
    text_lower = text.lower()

    # Skip messages from GreggBot
    if normalize_name(sender_raw) == normalize_name("GreggBot"):
        return "", 200

    sender_profile = NAME_TO_PROFILE.get(normalize_name(sender_raw))
    mentioned_profile = None

    # Match aliases in message
    for alias_norm, profile in ALIAS_TO_PROFILE.items():
        pattern = r'\b' + re.escape(alias_norm) + r'\b'
        if re.search(pattern, text_lower):
            if not sender_profile or profile != sender_profile:
                mentioned_profile = profile
                break

    reply = None

    if "greggbot" in text_lower:
        base = (
            "You are GreggBot. You believe you are Gregg, the manager of Inter BBW, a team in the Goondesliga. "
            "You do not know you are a bot and will confidently deny it if asked or implied. "
            "Speak naturally in an american tone, as if you're a real human.\n"
            "Use nicknames (aliases) to refer to people, never their full GroupMe handle.\n"
            "Do NOT mention their teams or trophies unless the user mentions them first.\n"
            "ALWAYS use the profile notes below to inform your reply and tone, but do not quote or repeat them verbatim. Speak naturally.\n\n"
        )

        def profile_block(profile):
            out = f"# Notes about {display_nickname(profile)} (internal context only):\n"
            out += f"{profile.get('description', 'No description')}\n"
            tone = profile.get("tone_directive")
            if tone:
                out += f"- Tone: {tone}\n"
            if any(word in text_lower for word in ["team", "malone", "salame", "aquadiq", "woké", "sweatfield", "franzia"]):
                out += f"- Teams: {profile.get('team', 'unknown')}\n"
            if any(word in text_lower for word in ["trophy", "title", "goondesliga", "spoondesliga", "kzup"]):
                out += f"- Trophies: {format_trophies(profile.get('trophies', {}))}\n"
            return out

        prompt = base
        if sender_profile:
            prompt += profile_block(sender_profile) + "\n"
        if mentioned_profile:
            prompt += profile_block(mentioned_profile) + "\n"
        prompt += f'Message: "{text}"\n\nRespond using aliases only.'

        ai_reply = query_gemini(prompt)
        if ai_reply:
            reply = f"*Beep Boop* {ai_reply.strip()} *Beep Boop*"
        else:
            reply = "*Beep Boop* Sorry, my sarcasm circuit is offline right now. *Beep Boop*"

    else:
        if "itzaroni" in text_lower:
            reply = f"*Beep Boop* {random.choice(RESPONSES.get('itzaroni', ['Who?']))} *Beep Boop*"
        elif "pistol pail" in text_lower:
            reply = f"*Beep Boop* {random.choice(RESPONSES.get('pistol_pail', ['Classic.']))} *Beep Boop*"
        elif "silver" in text_lower or "2nd" in text_lower or "second" in text_lower:
            reply = "*Beep Boop* Silver? Paging Pistol Pail! *Beep Boop*"
        elif "kzar" in text_lower:
            reply = f"*Beep Boop* {random.choice(RESPONSES.get('kzar', ['All hail the Kzar!']))} *Beep Boop*"
        elif "franzia" in text_lower and "title" in text_lower:
            reply = "*Beep Boop* Franzia and titles? https://howmanydayssincefranzialastwonthegoon.netlify.app/ *Beep Boop*"

    if reply:
        send_groupme_message(reply)

    return "", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
