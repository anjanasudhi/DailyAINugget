#!/usr/bin/env python3
"""
Daily AI Nugget Bot
--------------------
Generates one bite-sized AI/ML concept explanation + 1-2 recent, relevant
AI news items, then sends it to you both by email (Resend API) and by
Telegram (Telegram Bot API).

Designed to run on a schedule (cron / Windows Task Scheduler) alongside
your existing WhatsApp goal-notifier script.

SETUP
-----
1. pip install anthropic python-dotenv
2. Email (Resend): create a free account at https://resend.com and copy
   an API key from the dashboard (starts with "re_").
3. Telegram: message @BotFather on Telegram, send "/newbot", follow the
   prompts, and copy the bot token it gives you. Then send your new bot
   any message (e.g. "hi") so it can see your chat, and visit
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates in a browser to
   find your numeric chat id under "message" -> "chat" -> "id".
4. Create a .env file (same folder) with:
       ANTHROPIC_API_KEY=sk-ant-...
       RESEND_API_KEY=re_...
       EMAIL_TO=you@example.com
       EMAIL_FROM=onboarding@resend.dev              # optional; see note below
       TELEGRAM_BOT_TOKEN=123456789:AA...
       TELEGRAM_CHAT_ID=123456789
   Note: the shared "onboarding@resend.dev" sender only delivers to the
   email address you signed up to Resend with. To send to any address,
   verify your own domain in the Resend dashboard and set EMAIL_FROM to
   an address on it (e.g. bot@yourdomain.com).
5. Test: python daily_ai_nugget.py --dry-run   (prints message, doesn't send)
6. Schedule it:
       # crontab -e  (runs 8:00 AM daily)
       0 8 * * * /usr/bin/python3 /path/to/daily_ai_nugget.py >> /path/to/nugget.log 2>&1

CUSTOMIZING TOPICS
------------------
Edit TOPIC_CURRICULUM below to change the concepts covered or their order.
Unlike a random pool, this is a fixed, progressive curriculum: it starts
with basic ML foundations, moves through classic ML algorithms, then deep
learning fundamentals, then modern/LLM-era topics. The script sends ONE
topic per run, in order, and remembers where it left off in progress.json.
Once the whole curriculum is finished, it loops back to the start (handy
for spaced-repetition style review) — edit LOOP_WHEN_DONE to change that.
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import anthropic

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

SCRIPT_DIR = Path(__file__).parent
PROGRESS_FILE = SCRIPT_DIR / "progress.json"


# If True, restart from topic 1 after finishing the curriculum.
# If False, the script keeps re-sending the final topic once done.
LOOP_WHEN_DONE = True

# Ordered, progressive curriculum: basic ML -> classic ML -> DL fundamentals
# -> modern DL architectures -> LLM/GenAI-era topics -> applied/agentic AI.
# Add/remove/reorder freely — order IS the learning sequence.
TOPIC_CURRICULUM = [
    # --- Stage 1: Foundations / what is ML ---
    "what machine learning is and how it differs from traditional programming",
    "supervised vs unsupervised vs reinforcement learning",
    "features, labels, and training data",
    "the train/validation/test split and why it matters",
    "overfitting vs underfitting",
    "bias-variance tradeoff",
    # --- Stage 2: Core math intuition ---
    "vectors and matrices as ML building blocks",
    "what a dot product means geometrically",
    "gradient descent",
    "derivatives and the chain rule (why backpropagation needs them)",
    "loss functions and what they optimize for",
    # --- Stage 3: Classic ML algorithms ---
    "linear regression",
    "logistic regression and classification",
    "decision trees and random forests",
    "k-nearest neighbors",
    "support vector machines",
    "k-means clustering",
    "principal component analysis (PCA) and dimensionality reduction",
    "regularization (L1/L2) and why it prevents overfitting",
    # --- Stage 4: Deep learning fundamentals ---
    "what a neural network is (neurons, weights, layers)",
    "activation functions and why nonlinearity matters",
    "backpropagation",
    "convolutional neural networks (CNNs)",
    "recurrent neural networks (RNNs) and their limitations",
    "batch normalization and dropout",
    "vanishing/exploding gradients",
    # --- Stage 5: Modern architectures / LLM era ---
    "word embeddings (word2vec-style intuition)",
    "attention mechanisms",
    "transformers and self-attention",
    "how GPT-style models generate text, token by token",
    "tokenization and why LLMs struggle with things like counting letters",
    "pretraining vs fine-tuning",
    "reinforcement learning from human feedback (RLHF)",
    "embeddings and vector search",
    "retrieval-augmented generation (RAG)",
    "context windows and long-context models",
    "mixture of experts (MoE) architectures",
    "diffusion models",
    "multimodal models",
    # --- Stage 6: Applied / practical GenAI topics ---
    "prompt engineering vs fine-tuning: when to use which",
    "hallucination in LLMs and mitigation techniques",
    "chain-of-thought reasoning",
    "AI agents and tool use",
    "model context protocol (MCP)",
    "AI orchestration frameworks",
    "model quantization and distillation",
    "AI evaluation and benchmarking",
    "prompt injection and LLM security",
    "guardrails and content moderation for LLMs",
    "synthetic data for training",
]


def load_progress() -> int:
    """Returns the index of the next topic to send."""
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text()).get("next_index", 0)
    return 0


def save_progress(next_index: int) -> None:
    PROGRESS_FILE.write_text(json.dumps({"next_index": next_index}))


def pick_topic() -> str:
    idx = load_progress()
    if idx >= len(TOPIC_CURRICULUM):
        if LOOP_WHEN_DONE:
            idx = 0
        else:
            idx = len(TOPIC_CURRICULUM) - 1
            save_progress(idx)  # stay parked on the last topic
            return TOPIC_CURRICULUM[idx]

    topic = TOPIC_CURRICULUM[idx]
    save_progress(idx + 1)
    return topic


def generate_nugget(topic: str) -> str:
    """Call Claude (with web search) to produce the concept explainer + news."""
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    prompt = f"""Write a short daily "AI nugget" email. Three parts:

1. CONCEPT OF THE DAY: Explain "{topic}" in plain, simple language — 3-4 sentences,
   as if explaining to a smart colleague who isn't an ML specialist. Include one
   concrete example or analogy.

2. LEARN MORE: Search the web for ONE real, currently-live video/tutorial link that
   teaches this exact topic well. STRONGLY prefer a 3Blue1Brown (YouTube channel by
   Grant Sanderson) video if one exists on this topic or a close parent topic (e.g.
   his "Neural Networks" series, "Essence of Linear Algebra", "But what is a
   transformer?", "Attention in transformers", gradient descent/backpropagation
   videos, etc.) — his channel is a strong personal favorite. If no 3Blue1Brown
   video covers it, search for the next best high-quality, well-known tutorial
   (e.g. StatQuest, Andrej Karpathy, official docs) instead. Only include a URL you
   actually found via search — never invent or guess one. Give the exact title and
   the URL on one line.

3. IN THE NEWS: Search for genuinely recent (last 2-3 days) AI news that would be
   interesting to someone who is a Senior Manager working in Data Science / GenAI
   product management. Pick the single most relevant/interesting story. Give a
   2-3 sentence summary and mention the source name (no need for a URL).

4. INTERVIEW QUESTIONS ON THIS TOPIC: Write 2 interview questions (with concise,
   complete answers) about "{topic}" for EACH of these three roles, since the same
   topic gets probed at different depths depending on who's asking:
   a) AI Developer/ML Engineer — hands-on implementation/technical depth
      (e.g. how it works internally, tradeoffs, when it breaks or underperforms)
   b) Senior Manager — strategic/decision-level understanding (e.g. when to use
      it, cost/risk/ROI tradeoffs, how to evaluate a team's use of it)
   c) Software Engineer (non-ML specialist) — conceptual fluency a generalist
      dev would be expected to have (e.g. how it fits into a system, what to
      know before integrating it)
   Label each sub-group clearly and keep answers a few sentences each.

5. CASE STUDY / OPTIMIZATION INTERVIEW QUESTION: Write one realistic case-study
   or optimization-style interview question of the kind asked in technical
   interviews for AI/data/software roles (e.g. "how would you reduce latency/cost
   of X system", "how would you scale Y", "optimize this pipeline given
   constraints Z"). Follow it with a structured model answer: the approach/
   framework to reason through it, then a concrete example solution.

6. ENGINEERING LEADERSHIP CONCEPT: Cover one engineering concept that a
   cross-functional/tech lead should know — pick a different angle each time
   from areas like: when to refactor vs. leave code alone, code review best
   practices, managing technical debt, build vs. buy decisions, balancing
   speed vs. quality, mentoring/code ownership. Give a short explanation of the
   concept, then one sample interview Q&A that tests it (e.g. "how do you decide
   when code needs refactoring?").

Format as a plain-text email: short, scannable, use emoji sparingly for section
headers only (e.g. 🧠 for concept, 🎥 for learn more, 📰 for news, 💼 for interview
questions, 🧩 for case study, 🛠️ for engineering leadership). No markdown headers
(# or *), just plain text with line breaks. Do not add any preamble like "Here's
your nugget" - start directly with the content. Do not narrate your search
process, list what you found/considered, or explain your choices anywhere in
the output — only the final six formatted sections should appear, nothing
before section 1 and nothing after section 6."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=6000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )

    text_parts = [block.text for block in response.content if block.type == "text"]
    return "\n".join(text_parts).strip()


def send_email(subject: str, message: str) -> None:
    import urllib.request
    import urllib.error

    api_key = os.environ["RESEND_API_KEY"]
    from_address = os.environ.get("EMAIL_FROM", "onboarding@resend.dev")
    to_address = os.environ["EMAIL_TO"]

    payload = json.dumps({
        "from": from_address,
        "to": [to_address],
        "subject": subject,
        "text": message,
    }).encode("utf-8")

    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; daily-ai-nugget/1.0)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Resend API error {e.code}: {e.read().decode()}") from e

    print(f"Sent email to {to_address}. Resend id: {result.get('id')}")


def send_telegram(message: str) -> None:
    import urllib.request
    import urllib.error

    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
    }).encode("utf-8")

    request = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; daily-ai-nugget/1.0)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Telegram API error {e.code}: {e.read().decode()}") from e

    print(f"Sent Telegram message. Message id: {result['result']['message_id']}")


def main():
    parser = argparse.ArgumentParser(description="Daily AI nugget + news sender")
    parser.add_argument("--dry-run", action="store_true", help="Print message, don't send")
    parser.add_argument("--topic", type=str, help="Override topic selection")
    parser.add_argument("--reset-progress", action="store_true",
                         help="Restart the curriculum from topic 1")
    args = parser.parse_args()

    if args.reset_progress:
        save_progress(0)
        print("Progress reset to topic 1.")

    topic = args.topic or pick_topic()
    print(f"[{datetime.now().isoformat(timespec='seconds')}] Topic: {topic}")

    message = generate_nugget(topic)
    print("---- MESSAGE ----")
    print(message)
    print("-----------------")

    if args.dry_run:
        print("(dry run — not sent)")
        return

    send_email(f"AI Nugget: {topic}", message)
    send_telegram(message)


if __name__ == "__main__":
    sys.exit(main())
