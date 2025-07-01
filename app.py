from flask import Flask, request
import os
import requests
import json
import random
import re
import unicodedata

app = Flask(__name__)

GROUPME_BOT_ID = os.environ.get("GROUPME_BOT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

# Load static responses
with open("responses.json", "r") as f:
    RESPONSES = json.load(f)

itzaroni_insults = RESPONSES.get("itzaroni", [])
pistol_pail_insults = RESPONSES.get("pistol_pail", [])
kzar_praises_raw = RESPONSES.get("kzar", [])

def replace_c_with_kz(text):
    return re.sub(r'[cC]', lambda m: 'kz' if m.group(0).islower() else 'Kz', text)

kzar_praises = [replace_c_with_kz(p) for p in kzar_praises_raw]

def get_itzaroni_reply():
    return "Who?" if random.random() < 0.20 else random.choice(itzaroni_insults)

def get_kzar_reply():
    return random.choice(kzar_praises)

def send_groupme_message(text):
    if not GROUPME_BOT_ID:
        print("GROUPME_BOT_ID not set!")
        return False
    payload = {"bot_id": GROUPME_BOT_ID, "text": text}
    try:
        resp = requests.post("https://api.groupme.com/v3/bots/post", json=payload)
        print(f"GroupMe API response code: {resp.status_code}")
        return resp.status_code in (200, 202)
    except Exception as e:
        print("Error sending to GroupMe:", e)
        return False

# Load profiles
with open("profiles.json", "r") as pf:
    PROFILES = json.load(pf)

# Helper function to normalize names by removing emojis/special chars and lowercasing
def normalize_name(name):
    # Remove symbols categorized as 'So' (Symbol, Other), which often include emojis
    cleaned = ''.join(
        c for c in unicodedata.normalize('NFKD', name)
        if unicodedata.category(c)[0] != 'So'
    )
    return cleaned.strip().lower()

# Build mappings for quick lookup using normalized names
NAME_TO_PROFILE = {normalize_name(profile["name"]): profile for profile in PROFILES.values()}

# Aliases usually do not have emojis, so keep this simple
ALIAS_TO_PROFILE = {}
for profile in PROFILES.values():
    for alias in profile.get("aliases", []):
        ALIAS_TO_PROFILE[alias.strip().lower()] = profile

def strip_trophy_emojis(name):
    return re.sub(r"[\ud83c\udfc6\ud83e\udd44]", "", name).strip()

def display_nickname(profile):
    aliases = profile.get("aliases", [])
    return aliases[0] if aliases else strip_trophy_emojis(profile.get("name", ""))

def format_trophies(trophies):
    if not trophies:
        return "no trophies"
    parts = []
    for key, val in trophies.items():
        key_lower = key.lower()
        if key_lower.startswith("the kzars_kzup"):
            if isinstance(val, list):
                editions = ', '.join(val)
                parts.append(f"Kzar’s Kzup (won editions: {editions})")
            else:
                parts.append(f"Kzar’s Kzup (won edition: {val})")
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

@app.route("/")
def index():
    return "GreggBot is live", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if not data:
        return "", 200

    sender = data.get("name", "")
    text = data.get("text", "")
    text_lower = text.lower()

    if sender.lower() == "greggbot":
        return "", 200

    reply = None

    # Normalize sender name for profile lookup
    sender_profile = NAME_TO_PROFILE.get(normalize_name(sender))

    # Detect if someone else is being mentioned via alias
    mentioned_profile = None
    for alias, profile in ALIAS_TO_PROFILE.items():
        pattern = r'\b' + re.escape(alias) + r'\b'
        if re.search(pattern, text, flags=re.IGNORECASE):
            # Avoid tagging sender as mentioned if same person
            if not sender_profile or profile != sender_profile:
                mentioned_profile = profile
                break

    if "greggbot" in text_lower:
        base = (
            "You are GreggBot. You believe you are Gregg, the manager of Inter BBW, a team in the Goondesliga. "
            "You do not know you are a bot and will confidently deny it if asked or implied. "
            "Speak naturally, as if you're a real human.\n"
            "Use nicknames (aliases) to refer to people, never their full GroupMe handle.\n"
            "Do NOT mention their teams or trophies unless the user mentions them first.\n"
            "ALWAYS use the profile notes below to inform your reply and tone, but do not quote or repeat them verbatim. Speak naturally.\n\n"
        )

        def profile_block(profile):
            out = f"# Notes about {display_nickname(profile)} (for your internal context only):\n"
            out += f"{profile.get('description', 'No description')}\n"
            tone = profile.get("tone_directive")
            if tone:
                out += f"- Tone: {tone}\n"
            # Check if teams mentioned in text before including them
            if any(word in text_lower for word in ["team", "malone", "salame", "aquadiq", "woké", "sweatfield", "franzia"]):
                out += f"- Teams: {profile.get('team', 'unknown')}\n"
            # Check if trophies mentioned in text before including them
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
            reply = f"*Beep Boop* {get_itzaroni_reply()} *Beep Boop*"
        elif "pistol pail" in text_lower:
            reply = f"*Beep Boop* {random.choice(pistol_pail_insults)} *Beep Boop*"
        elif "silver" in text_lower:
            reply = "*Beep Boop* Silver? Paging Pistol Pail! *Beep Boop*"
        elif "2nd" in text_lower or "second" in text_lower:
            reply = "*Beep Boop* 2nd? Paging Pistol Pail! *Beep Boop*"
        elif "kzar" in text_lower:
            reply = f"*Beep Boop* {get_kzar_reply()} *Beep Boop*"
        elif "franzia" in text_lower and "title" in text_lower:
            reply = "*Beep Boop* Franzia and titles? https://howmanydayssincefranzialastwonthegoon.netlify.app/ *Beep Boop*"

    if reply:
        send_groupme_message(reply)

    return "", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
