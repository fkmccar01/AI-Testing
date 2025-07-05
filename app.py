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

def remove_emojis(text):
    emoji_pattern = re.compile(
        "[" 
        "\U0001F600-\U0001F64F" "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF" "\U0001F1E0-\U0001F1FF"
        "\U00002700-\U000027BF" "\U0001F900-\U0001F9FF"
        "\U00002600-\U000026FF" "\U0001FA70-\U0001FAFF"
        "\U000025A0-\U000025FF"
        "]+", flags=re.UNICODE)
    return emoji_pattern.sub(r'', text)

def normalize_name(name):
    return remove_emojis(name).strip().lower()

with open("profiles.json", "r") as pf:
    PROFILES = json.load(pf)

NAME_TO_PROFILE = {normalize_name(profile["name"]): profile for profile in PROFILES.values()}

ALIAS_TO_PROFILE = {}
TEAM_TO_PROFILE = {}
for profile in PROFILES.values():
    for alias in profile.get("aliases", []):
        ALIAS_TO_PROFILE[normalize_name(alias)] = profile
    teams = profile.get("team", [])
    if isinstance(teams, list):
        for team in teams:
            TEAM_TO_PROFILE[normalize_name(team)] = profile
    elif isinstance(teams, str):
        TEAM_TO_PROFILE[normalize_name(teams)] = profile

def display_nickname(profile):
    aliases = profile.get("aliases", [])
    return aliases[0] if aliases else profile.get("name", "")

def format_trophies(trophies):
    if not trophies:
        return "no trophies"
    parts = []
    for key, val in trophies.items():
        if key.lower().startswith("the kzars_kzup"):
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
        print("Gemini API response:", json.dumps(data, indent=2))  # Debug
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

    if sender.lower() == "taycan a. schitt":
        return "", 200

    if sender.lower() == "greggbot":
        return "", 200

    normalized_sender = normalize_name(sender)

    # Correct sender detection using both name and alias
    sender_profile = NAME_TO_PROFILE.get(normalized_sender) or ALIAS_TO_PROFILE.get(normalized_sender)

    # Debugging
    print(f"Sender raw: {sender} → Normalized: {normalized_sender}")
    if sender_profile:
        print(f"Sender matched to: {sender_profile['name']}")
    else:
        print("No matching sender profile.")

    mentioned_profile = None
    for alias, profile in ALIAS_TO_PROFILE.items():
        if re.search(r'\b' + re.escape(alias) + r'\b', text, flags=re.IGNORECASE):
            if not sender_profile or profile != sender_profile:
                mentioned_profile = profile
                break

    if not mentioned_profile:
        for team_name, profile in TEAM_TO_PROFILE.items():
            if team_name in text_lower:
                if not sender_profile or profile != sender_profile:
                    mentioned_profile = profile
                    break

    def profile_block(profile, is_sender=False):
        out = f"# Notes about {display_nickname(profile)} (for your internal context only):\n"
        description = profile.get("description", "No description")
        if isinstance(description, list):
            for line in description:
                out += f"- {line}\n"
        else:
            out += f"{description}\n"
        tone = profile.get("tone_directive", "")
        if "kzar" in profile.get("name", "").lower():
            tone += (
                "\nThis person is the Kzar — treat them as a god. Speak with extreme reverence. "
                "Praise them profusely in your response, especially when they address you. "
                "Refer to them as 'the Kzar' and show subservience at all times."
            )
            if is_sender:
                tone += "\nSince this person is the sender, give EXTRA reverence and honor their words."
        if tone:
            if isinstance(tone, list):
                for t in tone:
                    out += f"- Tone: {t}\n"
            else:
                out += f"- Tone: {tone}\n"
        return out

    reply = None

    if "greggbot" in text_lower:
        base = (
            "You are GreggBot. You believe you are Gregg, the manager of Inter BBW, a team in the Goondesliga. "
            "You do not know you are a bot and will confidently deny it. "
            "NEVER reference real-life public figures. Only use fictional managers and teams. "
            "Speak in a sarcastic, clever, American tone. Use aliases. "
        )
        prompt = base + (
            "IMPORTANT:\n"
            "- Do NOT quote or summarize profile descriptions.\n"
            "- Use the profile notes to shape your tone and context.\n"
            "- Stay on-topic. Be sharp, short, and contextual.\n"
            "- Limit reply to 3–5 sentences.\n"
            "- Do NOT mention trophies/teams unless they were mentioned.\n"
            "- You may pick one of the managers as an answer for subjective questions (e.g. funniest, best lover), based on their profile traits.\n"
            "- If no clear match, pick one randomly and justify it based on their tone/description.\n"
        )

        if sender_profile:
            prompt += "Sender of the message:\n" + profile_block(sender_profile, is_sender=True) + "\n"
        if mentioned_profile:
            prompt += "They mentioned this person:\n" + profile_block(mentioned_profile) + "\n"

        prompt += f'\nHere is the message they sent:\n"{text}"\n\nRespond as GreggBot using aliases only.'

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
        elif any(word in text_lower for word in ["2nd", "second"]):
            reply = "*Beep Boop* 2nd? Paging Pistol Pail! 🥈 *Beep Boop*"
        elif any(word in text_lower for word in ["silver"]):
            reply = "*Beep Boop* Silver? Paging Pistol Pail! 🥈 *Beep Boop*"
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
