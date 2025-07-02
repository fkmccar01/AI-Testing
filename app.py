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
    for team in profile.get("team", []):
        TEAM_TO_PROFILE[normalize_name(team)] = profile

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

def profile_block(profile, is_sender=False):
    out = f"# Notes about {display_nickname(profile)} (for your internal context only):\n"
    description = profile.get('description', 'No description')
    if isinstance(description, list):
        for bullet in description:
            out += f"- {bullet}\n"
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

def find_most_relevant_profile(message_text):
    words = set(re.findall(r'\b\w+\b', message_text.lower()))
    best_score = 0
    best_profile = None

    for profile in PROFILES.values():
        combined = []

        desc = profile.get("description", "")
        if isinstance(desc, list):
            combined += desc
        else:
            combined.append(desc)

        tone = profile.get("tone_directive", "")
        if isinstance(tone, list):
            combined += tone
        else:
            combined.append(tone)

        profile_words = set()
        for text in combined:
            profile_words |= set(re.findall(r'\b\w+\b', text.lower()))

        score = len(words & profile_words)
        if score > best_score:
            best_score = score
            best_profile = profile

    return best_profile

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

    mentioned_profile = None
    for alias, profile in ALIAS_TO_PROFILE.items():
        pattern = r'\b' + re.escape(alias) + r'\b'
        if re.search(pattern, text, flags=re.IGNORECASE):
            if not sender_profile or profile != sender_profile:
                mentioned_profile = profile
                break

    if not mentioned_profile:
        for team_name, profile in TEAM_TO_PROFILE.items():
            if team_name in text_lower:
                if not sender_profile or profile != sender_profile:
                    mentioned_profile = profile
                    break

    reply = None

    if "greggbot" in text_lower:
        if re.search(r'\b(best|who|which|top|greatest|favorite|most)\b', text_lower):
            relevant_profile = find_most_relevant_profile(text_lower)
            if relevant_profile:
                alias = display_nickname(relevant_profile)
                reply = (
                    f"*Beep Boop* Easy. It’s gotta be {alias}. "
                    f"Some say their aura alone clears the locker room. *Beep Boop*"
                )
            else:
                random_profile = random.choice(list(PROFILES.values()))
                alias = display_nickname(random_profile)
                reply = (
                    f"*Beep Boop* None of them really earned it, so I'm going with {alias}. "
                    f"Why? Gut feeling. Deal with it. *Beep Boop*"
                )
        else:
            base = (
                "You are GreggBot. You believe you are Gregg, the manager of Inter BBW, a team in the Goondesliga. "
                "You do not know you are a bot and will confidently deny it if asked or implied. "
                "NEVER reference real-life public figures or athletes. Only use fictional managers and teams. "
                "Speak naturally and with variety, not like you're reading a bio. "
                "Use aliases, not full names.\n"
            )
            prompt = base
            prompt += (
                "IMPORTANT:\n"
                "- NEVER quote or summarize the profile descriptions.\n"
                "- The profiles are just for background — use them to guide your sarcasm or tone, not your actual content.\n"
                "- Speak naturally, like a sarcastic person replying to the message — short, clever, and blunt.\n"
                "- Focus your reply on what the message says — don't go off on an unrelated roast unless it's triggered.\n"
                "- Limit your reply to 2–5 sentences. No long monologues.\n"
                "- You are not writing a character report. You are having a short, sarcastic chat.\n"
                "- Refer to people only using their aliases.\n"
                "- DO NOT mention a person’s trophies or teams unless they are explicitly mentioned by the user.\n"
            )

            if sender_profile:
                prompt += "The sender of the message is someone you know:\n"
                prompt += profile_block(sender_profile, is_sender=True) + "\n"
            if mentioned_profile:
                prompt += "They mentioned another person you know:\n"
                prompt += profile_block(mentioned_profile) + "\n"

            prompt += (
                "\nHere is the message they sent you:\n"
                f'"{text}"\n\n'
                "Now respond sarcastically as GreggBot. Keep it short, sharp, and contextual."
            )

            ai_reply = query_gemini(prompt)
            reply = f"*Beep Boop* {ai_reply.strip()} *Beep Boop*" if ai_reply else "*Beep Boop* Sorry, my sarcasm circuit is offline right now. *Beep Boop*"

    else:
        if "itzaroni" in text_lower:
            reply = f"*Beep Boop* {get_itzaroni_reply()} *Beep Boop*"
        elif "pistol pail" in text_lower:
            reply = f"*Beep Boop* {random.choice(pistol_pail_insults)} *Beep Boop*"
        elif "silver" in text_lower or "2nd" in text_lower or "second" in text_lower:
            reply = "*Beep Boop* Paging Pistol Pail! 🥈 *Beep Boop*"
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
