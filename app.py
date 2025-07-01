from flask import Flask, request
import os
import requests
import json
import random
import re

app = Flask(__name__)

GROUPME_BOT_ID = os.environ.get("GROUPME_BOT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

# Load static insults/praises
with open("responses.json", "r") as f:
    RESPONSES = json.load(f)

# Helper to replace c/C with kz/Kz for kzar praises
def replace_c_with_kz(text):
    return re.sub(r'[cC]', lambda m: 'kz' if m.group(0).islower() else 'Kz', text)

kzar_praises = [replace_c_with_kz(p) for p in RESPONSES.get("kzar", [])]
itzaroni_insults = RESPONSES.get("itzaroni", [])
pistol_pail_insults = RESPONSES.get("pistol_pail", [])

def get_itzaroni_reply():
    return "Who?" if random.random() < 0.20 else random.choice(itzaroni_insults)

def get_pistol_pail_reply():
    return random.choice(pistol_pail_insults)

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

# Strip emojis helper
def remove_emojis(text):
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002700-\U000027BF"
        "\U0001F900-\U0001F9FF"
        "\U00002600-\U000026FF"
        "\U0001FA70-\U0001FAFF"
        "\U000025A0-\U000025FF"
        "]+", flags=re.UNICODE)
    return emoji_pattern.sub(r'', text)

def normalize_name(name):
    if isinstance(name, list):
        # Defensive fallback if name is a list (fix for bad input)
        name = " ".join(name)
    return remove_emojis(name).strip().lower()

# Load profiles
with open("profiles.json", "r") as pf:
    PROFILES = json.load(pf)

NAME_TO_PROFILE = {normalize_name(p["name"]): p for p in PROFILES.values()}
ALIAS_TO_PROFILE = {}
TEAM_TO_PROFILE = {}

for profile in PROFILES.values():
    for alias in profile.get("aliases", []):
        ALIAS_TO_PROFILE[normalize_name(alias)] = profile
    team = profile.get("team", [])
    if isinstance(team, str):
        TEAM_TO_PROFILE[normalize_name(team)] = profile
    elif isinstance(team, list):
        for t in team:
            TEAM_TO_PROFILE[normalize_name(t)] = profile

def display_nickname(profile):
    aliases = profile.get("aliases", [])
    return aliases[0] if aliases else profile.get("name", "")

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
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(GEMINI_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print("Gemini API error:", e)
        return None

def profile_block(profile, is_sender=False):
    tone = profile.get("tone_directive", "")
    name = display_nickname(profile)
    desc = profile.get("description", "No description")
    trophies = format_trophies(profile.get("trophies", {}))

    block = f"# Context for {name}:\n"
    block += f"{desc}\n"
    if trophies:
        block += f"Trophies: {trophies}\n"
    if tone:
        block += f"- Tone: {tone}\n"
    if is_sender:
        block += "- This person is the sender. Address them using this tone with proper respect.\n"
    else:
        block += "- Refer to this person in your reply using their aliases and their tone.\n"
    return block

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

    # Ignore messages from GreggBot itself
    if sender.lower() == "greggbot":
        return "", 200

    normalized_sender = normalize_name(sender)

    # Identify sender profile
    sender_profile = NAME_TO_PROFILE.get(normalized_sender) or ALIAS_TO_PROFILE.get(normalized_sender)

    # Helper to check exact word-boundary mention
    def is_mentioned(alias_or_team, text):
        pattern = r'\b' + re.escape(alias_or_team.lower()) + r'\b'
        return re.search(pattern, text) is not None

    mentioned_profiles = []
    mentioned_profiles_set = set()

    # Check aliases first, excluding ambiguous "gg" unless full name present
    for alias, profile in ALIAS_TO_PROFILE.items():
        alias_lower = alias.lower()
        if alias_lower == "gg":
            full_name_lower = profile["name"].lower()
            if full_name_lower not in text_lower:
                continue
        if is_mentioned(alias_lower, text_lower):
            if sender_profile and profile["name"] == sender_profile["name"]:
                continue
            if profile["name"] not in mentioned_profiles_set:
                mentioned_profiles.append(profile)
                mentioned_profiles_set.add(profile["name"])

    # Then check teams
    for team_name, profile in TEAM_TO_PROFILE.items():
        if is_mentioned(team_name.lower(), text_lower):
            if sender_profile and profile["name"] == sender_profile["name"]:
                continue
            if profile["name"] not in mentioned_profiles_set:
                mentioned_profiles.append(profile)
                mentioned_profiles_set.add(profile["name"])

    print("Mentioned profiles detected:", [p["name"] for p in mentioned_profiles])  # Debug line

    reply = None

    # Hardcoded fun replies if no AI prompt needed
    if "itzaroni" in text_lower:
        reply = f"*Beep Boop* {get_itzaroni_reply()} *Beep Boop*"
    elif "pistol pail" in text_lower:
        reply = f"*Beep Boop* {get_pistol_pail_reply()} *Beep Boop*"
    elif "silver" in text_lower or "2nd" in text_lower or "second" in text_lower:
        reply = "*Beep Boop* 2nd? Paging Pistol Pail! *Beep Boop*"
    elif "kzar" in text_lower:
        reply = f"*Beep Boop* {get_kzar_reply()} *Beep Boop*"
    elif "franzia" in text_lower and "title" in text_lower:
        reply = "*Beep Boop* Franzia and titles? https://howmanydayssincefranzialastwonthegoon.netlify.app/ *Beep Boop*"
    else:
        # Compose prompt for Gemini
        prompt = (
            "You are GreggBot, a sarcastic, witty chatbot for the Goondesliga group chat. "
            "Always start and end your reply with '*Beep Boop*'. "
            "Use nicknames (aliases) to refer to people, never their full names. "
            "Do NOT mention teams or trophies unless explicitly mentioned by the user.\n\n"
        )

        if sender_profile:
            prompt += profile_block(sender_profile, is_sender=True) + "\n"

        for prof in mentioned_profiles:
            prompt += profile_block(prof, is_sender=False) + "\n"

        prompt += f'User message: "{text}"\n\n'
        prompt += "Generate a single natural, sarcastic and tone-appropriate reply addressing the sender with their tone, and commenting on any mentioned other profiles using their tones, blending the tones naturally. Use aliases only."

        ai_reply = query_gemini(prompt)
        if ai_reply:
            reply = f"*Beep Boop* {ai_reply.strip()} *Beep Boop*"
        else:
            reply = "*Beep Boop* Sorry, my sarcasm circuit is offline right now. *Beep Boop*"

    if reply:
        send_groupme_message(reply)

    return "", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
