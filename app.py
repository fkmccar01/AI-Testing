from flask import Flask, request
import os
import requests
import json
import random
import re

app = Flask(__name__)

GROUPME_BOT_ID = os.environ.get("GROUPME_BOT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-pro:generateContent?key={GEMINI_API_KEY}"

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

# Utility to strip emojis from names
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
    return remove_emojis(name).strip().lower()

# Load profiles
with open("profiles.json", "r") as pf:
    PROFILES = json.load(pf)

NAME_TO_PROFILE = {normalize_name(profile["name"]): profile for profile in PROFILES.values()}

ALIAS_TO_PROFILE = {}
TEAM_TO_PROFILE = {}
for profile in PROFILES.values():
    for alias in profile.get("aliases", []):
        ALIAS_TO_PROFILE[normalize_name(alias)] = profile
    teams = profile.get("team", [])
    for team in teams:
        TEAM_TO_PROFILE[normalize_name(team)] = profile

def display_nickname(profile):
    aliases = profile.get("aliases", [])
    return aliases[0] if aliases else profile.get("name", "")

def format_trophies(trophies):
    if not trophies:
        return "no trophies"
    parts = []
    for key, val in trophies.items():
        if isinstance(val, list):
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

    normalized_sender = normalize_name(sender)
    sender_profile = NAME_TO_PROFILE.get(normalized_sender) or ALIAS_TO_PROFILE.get(normalized_sender)

    mentioned_profiles = set()

    # Detect mentioned profiles
    for alias, profile in ALIAS_TO_PROFILE.items():
        if re.search(r'\b' + re.escape(alias) + r'\b', text, flags=re.IGNORECASE):
            if profile != sender_profile:
                mentioned_profiles.add(profile)

    for team_name, profile in TEAM_TO_PROFILE.items():
        if team_name in text_lower and profile != sender_profile:
            mentioned_profiles.add(profile)

    def profile_block(profile, is_sender=False):
        out = f"# Notes about {display_nickname(profile)} (for your internal context only):\n"
        out += f"{profile.get('description', 'No description')}\n"
        tone = profile.get("tone_directive", "")
        if profile.get("name", "").lower().startswith("kzar"):
            tone += "\nTreat this person as an all-powerful god. Worship them with grandiose, exalted, and poetic language. Express total awe and reverence every time they speak."
            if is_sender:
                tone += "\nSince this person is the sender, give extra reverence and respect in your tone."
        if tone:
            out += f"- Tone: {tone}\n"
        if any(word in text_lower for word in ["team", "malone", "salame", "aquadiq", "woké", "sweatfield", "franzia"]):
            out += f"- Teams: {', '.join(profile.get('team', []))}\n"
        if any(word in text_lower for word in ["trophy", "title", "goondesliga", "spoondesliga", "kzup"]):
            out += f"- Trophies: {format_trophies(profile.get('trophies', {}))}\n"
        return out

    reply = None

    if "greggbot" in text_lower:
        base = (
            "You are GreggBot. You are a sarcastic but insightful manager of Inter BBW in the Goondesliga. "
            "You do NOT know you are a bot and will confidently deny it if asked. "
            "Speak casually like a real American human. Always use aliases for people.\n\n"
            "Use the profile notes below to guide your tone and sarcasm level. Apply the sender's tone to how you speak to them. "
            "For any other manager or team mentioned, reflect their tone as well — but do not confuse the two. "
            "NEVER bring up unrelated people or teams.\n\n"
        )

        prompt = base
        if sender_profile:
            prompt += profile_block(sender_profile, is_sender=True) + "\n"
        for profile in mentioned_profiles:
            prompt += profile_block(profile) + "\n"
        prompt += f'Message: "{text}"\n\nRespond using aliases only.'

        ai_reply = query_gemini(prompt)
        if ai_reply:
            reply = f"*Beep Boop* {ai_reply.strip()} *Beep Boop*"
        else:
            reply = "*Beep Boop* Sorry, my sarcasm circuit is offline. *Beep Boop*"

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
