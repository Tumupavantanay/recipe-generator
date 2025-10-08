from flask import Flask, request, jsonify
from flask_cors import CORS
import os, time, re
from dotenv import load_dotenv
from openai import OpenAI, APIError, RateLimitError

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise Exception("Please set OPENROUTER_API_KEY in backend/.env")

APP_URL = os.getenv("APP_URL", "http://localhost:8000")

# OpenRouter via OpenAI SDK
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    default_headers={"HTTP-Referer": APP_URL, "X-Title": "Recipe Generator (Local Dev)"},
)

app = Flask(__name__)
CORS(app)

# --------- Helpers ---------
FREE_MODELS = [
    # Chat-friendly free-tier models (OpenRouter rotates availability)
    "mistralai/mixtral-8x7b:free",
    "gryphe/mythomax-l2-13b:free",
    "nousresearch/hermes-2-pro-mistral:free",
    "google/gemma-2-9b-it:free",  # some days this behaves like single-prompt, but keep as fallback
]

TEMPLATE_MARKERS = [
    "Please provide me with a clear prompt",
    "For example, you could ask me to",
    "The more specific your request",
]

def looks_like_recipe(text: str) -> bool:
    if not text or len(text.strip()) < 80:
        return False
    if any(m in text for m in TEMPLATE_MARKERS):
        return False
    # Must contain a title-like first line and ingredients + steps hints
    has_ingredients = re.search(r"\bingredients\b", text, re.I) is not None
    has_steps = re.search(r"\b(step|instructions)\b", text, re.I) is not None
    has_numbers = re.search(r"\n\s*(1\.|1\))", text) is not None
    return has_ingredients and (has_steps or has_numbers)

SYSTEM_PROMPT = (
    "You are a skilled chef. Always respond with a complete recipe. "
    "Format strictly as:\n"
    "1) A short recipe title on the first line\n"
    "2) 'Ingredients:' with bullet list and quantities\n"
    "3) 'Pantry Items:' list for salt/oil/water, if needed\n"
    "4) 'Steps:' with numbered steps\n"
    "5) 'Tips:' optional short bullets\n"
    "Do NOT ask the user for a clearer prompt. Never output placeholders."
)

def make_user_prompt(ingredients: str) -> str:
    return (
        f"Create a full recipe using ONLY these ingredients: {ingredients}.\n"
        "Keep it realistic; if essential pantry items are needed, list them under 'Pantry Items'. "
        "Return only the recipe formatted as specified."
    )

# --------- Routes ---------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/generate_recipe", methods=["POST"])
def generate_recipe():
    data = request.get_json(force=True) or {}
    ingredients = (data.get("ingredients") or "").strip()
    if not ingredients:
        return jsonify({"error": "No ingredients provided"}), 400

    user_prompt = make_user_prompt(ingredients)
    last_err = None

    for model in FREE_MODELS:
        # small retry on transient 429/5xx
        attempts, backoff = 0, 1.0
        while attempts < 2:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=650,
                    temperature=0.7,
                )
                text = resp.choices[0].message.content or ""
                if looks_like_recipe(text):
                    return jsonify({"recipe": text}), 200
                # If it looks junky, break to next model
                app.logger.warning(f"Model {model} returned non-recipe content, trying next.")
                break
            except RateLimitError as e:
                attempts += 1
                if attempts >= 2:
                    last_err = ("rate_limited", str(e))
                    break
                time.sleep(backoff); backoff *= 2
            except APIError as e:
                # 404 / endpoint not found / 5xx → go to next model
                last_err = ("openrouter_api_error", str(e))
                app.logger.warning(f"Model {model} API error: {e}")
                break
            except Exception as e:
                last_err = ("server_error", str(e))
                app.logger.warning(f"Model {model} general error: {e}")
                break

    # If we reach here, nothing worked well enough
    if last_err:
        code = 429 if last_err[0] == "rate_limited" else 502 if last_err[0] == "openrouter_api_error" else 500
        return jsonify({"error": last_err[0], "message": last_err[1]}), code

    return jsonify({
        "error": "no_valid_output",
        "message": "All free models returned unusable output. Please retry in a few seconds."
    }), 503


# Running under Vercel Python runtime (serverless). No app.run() block needed.
