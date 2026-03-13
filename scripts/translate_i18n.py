import os
import json
import asyncio
from google import genai
from config import GEMINI_API_KEY
from i18n import STRINGS

LANGUAGES = [
    ("ar", "Arabic"),
    ("fr", "French"),
    ("de", "German"),
    ("it", "Italian"),
    ("es", "Spanish"),
    ("ky", "Kyrgyz"),
    ("uz", "Uzbek"),
    ("be", "Belarusian"),
    ("tg", "Tajik"),
    ("tk", "Turkmen"),
]

async def get_key():
    import sqlite3
    import aiosqlite
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT value FROM settings WHERE key='GEMINI_API_KEY'") as cursor:
            row = await cursor.fetchone()
            if row: return row[0]
            return GEMINI_API_KEY

async def get_client():
    key = await get_key()
    return genai.Client(api_key=key)

async def translate_dict(en_dict, target_language):
    client = await get_client()
    prompt = f"Translate the following JSON dictionary values into {target_language}. Keep the exact same JSON keys. Maintain emojis and telegram HTML tags (<b>, <i>, etc). Here is the dictionary:\n{json.dumps(en_dict, indent=2)}\n\nOnly output valid JSON, nothing else."
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    
    result = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(result)

async def main():
    en_dict = STRINGS["en"]
    with open("i18n.py", "w", encoding="utf-8") as f:
        f.write('"""\nInternationalization (i18n) strings for NeuroNanoBanana.\n"""\n\nSTRINGS = {\n')
        
        # Write RU
        f.write('    "ru": ')
        f.write(json.dumps(STRINGS['ru'], indent=8, ensure_ascii=False))
        f.write(',\n')
        
        # Write EN
        f.write('    "en": ')
        f.write(json.dumps(STRINGS['en'], indent=8, ensure_ascii=False))
        f.write(',\n')
        
        for code, name in LANGUAGES:
            print(f"Translating {name}...")
            if code in STRINGS and False: # Skip if already there
                trans = STRINGS[code]
            else:
                try:
                    trans = await translate_dict(en_dict, name)
                except Exception as e:
                    print(f"Error for {name}: {e}")
                    trans = en_dict # fallback to en
            
            f.write(f'    "{code}": ')
            f.write(json.dumps(trans, indent=8, ensure_ascii=False))
            f.write(',\n')
            
        f.write('}\n\n')
        f.write('''def t(key, lang="ru", **kwargs):
    language_dict = STRINGS.get(lang)
    if not language_dict:
        language_dict = STRINGS["ru"]
    
    msg = language_dict.get(key, key)
    if kwargs:
        try:
            msg = msg.format(**kwargs)
        except Exception:
            pass
    return msg
''')

if __name__ == "__main__":
    asyncio.run(main())
