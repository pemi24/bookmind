"""Intent routing for chat: small talk, questions about the assistant, book questions, off-topic.

Obvious messages ("hello", "thanks!", "what can you do?") are recognised by rules; anything
else gets one short classification call that small local models handle reliably (one word
back), and anything uncertain is treated as a book question, which keeps grounding strict.
The replies for non-book messages are written here, not by the model: instant, consistent,
and they never claim anything about the book's content.
"""
from __future__ import annotations

import random
import re
from collections.abc import Sequence

INTENTS = ("smalltalk", "meta", "book_question", "off_topic")

# ---------------------------------------------------------------- rules (whole message must match)

_END = r"[\s!.?,~:;)(\-]*(?:[\U0001F300-\U0001FAFF☀-➿]\s*)*$"  # trailing punctuation / emoji
_GREETING = re.compile(
    r"^(?:hi+|hey+|hello+|hiya|howdy|yo|greetings|good (?:morning|afternoon|evening|day)|hey there|hi there|"
    r"hello there|bonjour|salut|hola|ciao)(?: (?:there|again|bookmind|friend|everyone|buddy))?" + _END, re.I)
_HOW_ARE_YOU = re.compile(
    r"^(?:(?:hi|hey|hello)[\s,!]+)?(?:how are (?:you|u)(?: doing)?(?: today)?|how'?s it going|how are things|"
    r"what'?s up|sup|how do you do)" + _END, re.I)
_THANKS = re.compile(
    r"^(?:(?:ok(?:ay)?|great|perfect|awesome|cool|nice)[\s,!]+)?(?:thanks?(?: (?:a lot|so much|very much|again|"
    r"you(?: so much| very much)?))?|thank (?:you|u)(?: (?:so much|very much|a lot))?|thx|ty|cheers|merci|"
    r"much appreciated|appreciate it)" + _END, re.I)
_BYE = re.compile(
    r"^(?:bye+|goodbye|good night|see (?:you|ya)(?: later| soon)?|later|take care|that'?s all(?: for now)?|"
    r"i'?m done|ciao|au revoir)" + _END, re.I)
# Not "yes"/"no"/"sure": those usually answer the assistant's own question, so the router decides.
_ACK = re.compile(r"^(?:ok(?:ay)?|k|kk|alright|all right|got it|i see|cool|nice|great|awesome|perfect|"
                  r"good|fine|lol|haha+|wow|interesting|makes sense)" + _END, re.I)
_COMPLIMENT = re.compile(
    r"^(?:you(?:'re| are) (?:great|awesome|amazing|helpful|the best|smart|so helpful|very helpful)|"
    r"(?:great|good|nice|awesome|excellent|helpful) (?:job|work|answer|answers|bot)|well done|love it|"
    r"i love (?:this|you|it)|this is (?:great|awesome|amazing|helpful))" + _END, re.I)
_META = re.compile(
    r"^(?:what (?:can|could|do) you do|what are you|who are you|what is bookmind|what'?s bookmind|"
    r"how (?:do|can|should) i use (?:this|you|bookmind|the app|it)|how does (?:this|bookmind|it|the app) work|"
    r"what can i (?:ask|do)(?: here)?|help|help me|what features (?:do you have|are there)|"
    r"what are your (?:features|abilities|capabilities)|how can you help(?: me)?|"
    r"(?:can|could) you help(?: me)?|what should i ask(?: you)?)" + _END, re.I)

_SMALLTALK_KINDS = (("greeting", _GREETING), ("how_are_you", _HOW_ARE_YOU), ("thanks", _THANKS),
                    ("goodbye", _BYE), ("compliment", _COMPLIMENT), ("ack", _ACK))

# Follow-ups that only make sense about the conversation so far ("tell me more", "why did he do that?").
_FOLLOW_UP = re.compile(
    r"^(?:tell me more|more|go on|continue|and then\??|then what|what happened next|what next|why\??|how\??|"
    r"explain(?: that| more| further)?|elaborate|(?:can you )?(?:give|tell) me more|what else|anything else|"
    r"and (?:him|her|them|that|this)\??|what about (?:him|her|them|that|this|it)|"
    r"(?:why|how|when|where|who|what) (?:did|does|do|was|were|is|are|had|has|would|will) "
    r"(?:he|she|they|it|him|her|them|that|this|those|these)\b.*)" + _END, re.I)
# Words that point at a book's content: never off-topic, never small talk.
_BOOKISH = re.compile(r"\b(?:book|story|novel|chapter|character|plot|author|theme|quote|passage|page|ending|"
                      r"summar\w*|quiz|scene|narrator|protagonist|villain|hero|heroine|verse)\b", re.I)


def rule_intent(message: str) -> tuple[str, str] | None:
    """(intent, kind) for obvious messages; None when the model should decide."""
    text = " ".join(message.split())
    if not text or len(text) > 80:
        return None
    for kind, rx in _SMALLTALK_KINDS:
        if rx.match(text):
            return "smalltalk", kind
    if _META.match(text):
        return "meta", "features"
    return None


def is_follow_up(message: str) -> bool:
    return bool(_FOLLOW_UP.match(" ".join(message.split())))


def mentions_book(message: str, book_title: str) -> bool:
    if _BOOKISH.search(message):
        return True
    words = {w for w in re.findall(r"[a-z']{4,}", book_title.lower()) if w not in {"with", "from", "that", "this", "the"}}
    return bool(words & set(re.findall(r"[a-z']{4,}", message.lower())))


# ---------------------------------------------------------------- the model's tie-breaker

CLASSIFY_SYSTEM = """You sort messages sent to a reading assistant for one book. Reply with ONE word:
smalltalk - greeting, thanks, goodbye, chit-chat
meta - a question about the assistant or the app itself
book - anything about the book: its story, people, places, ideas, quotes, or a follow-up to the conversation
offtopic - general knowledge unrelated to the book
If unsure, reply: book"""


def build_classify_user(book_title: str, history: Sequence[tuple[str, str]], message: str) -> str:
    recent = "\n".join(f"{role}: {text[:200]}" for role, text in list(history)[-4:])
    convo = f"Recent conversation:\n{recent}\n\n" if recent else ""
    return f"Book: {book_title}\n{convo}Message: {message[:500]}\n\nOne word:"


def parse_intent(reply: str) -> str:
    """The model's one-word answer; anything unclear counts as a book question."""
    words = re.findall(r"[a-z_-]+", reply.lower())[:3]
    for w in words:
        if w in ("smalltalk", "small-talk", "small_talk", "chitchat"):
            return "smalltalk"
        if w == "meta":
            return "meta"
        if w in ("offtopic", "off-topic", "off_topic"):
            return "off_topic"
        if w in ("book", "book_question"):
            return "book_question"
    return "book_question"


# ---------------------------------------------------------------- replies (no model, no retrieval)

def _title(book_title: str, author: str | None) -> str:
    return f"*{book_title}*" + (f" by {author}" if author else "")


CAPABILITIES = ("answer questions with quotes and page references, summarize chapters, quiz you or make flashcards, "
                "find quotes on a theme, and explain characters and events")


def smalltalk_reply(kind: str, book_title: str, author: str | None = None) -> str:
    t = _title(book_title, author)
    replies = {
        "greeting": [f"Hello! How may I assist you with {t} today? I can {CAPABILITIES}."],
        "how_are_you": [f"I'm doing well, thanks for asking! I'm ready to dive into {t} with you. "
                        "What would you like to know?"],
        "thanks": [f"You're welcome! Is there anything else you'd like to know about {t}?",
                   f"Glad I could help! Ask me anything else about {t} whenever you like."],
        "goodbye": [f"Goodbye, and happy reading! Come back any time you have a question about {t}."],
        "compliment": [f"Thank you, that's kind of you! What else would you like to explore in {t}?"],
        "ack": [f"Great! What would you like to look at next in {t}? You could ask about a character, "
                "a chapter, or a theme."],
    }
    return random.choice(replies.get(kind, replies["greeting"]))


def meta_reply(book_title: str, author: str | None = None, compare_titles: Sequence[str] = ()) -> str:
    t = _title(book_title, author)
    scope = t if not compare_titles else t + " and " + ", ".join(f"*{x}*" for x in compare_titles)
    return (f"I'm BookMind, your reading companion for {scope}. Here's what I can do:\n\n"
            "- **Answer questions** about the book, with quotes and page references you can click to open the reader\n"
            "- **Summarize** a chapter or the whole book (Summaries tab)\n"
            "- **Quiz you** or make **flashcards** (Study tab)\n"
            "- **Find quotes** on a theme (Quotes tab), and map **characters** and the **timeline** (Explore, Timeline)\n"
            "- **Talk to a character**, compare books, and help plan an **essay**\n\n"
            "Set *Read up to* in the header and I won't spoil anything past where you are. "
            "What would you like to start with?")


def off_topic_reply(book_title: str, examples: Sequence[str], author: str | None = None) -> str:
    t = _title(book_title, author)
    lines = "\n".join(f"- {q}" for q in examples[:3])
    return (f"That's outside what I can help with here: I'm your reading companion for {t}, and I only answer "
            f"from the book itself. Here are some things you could ask instead:\n\n{lines}")


def not_found_reply(book_title: str, examples: Sequence[str]) -> str:
    """When the search finds nothing at all for a book question (the model isn't asked to guess)."""
    lines = "\n".join(f"- {q}" for q in examples[:3])
    return (f"I couldn't find anything about that in *{book_title}*, so I can't answer it from the book. "
            f"You could try rephrasing it with the names or words the book uses, or ask something like:\n\n{lines}")


DEFAULT_STARTERS = ("What is this book about?", "Who are the main characters?", "Summarize the first chapter.",
                    "What are the main themes?")


def starter_questions(suggested: Sequence[str]) -> list[str]:
    """The book's own suggested questions, topped up with general ones."""
    out = [q for q in suggested if q and q.strip()]
    for q in DEFAULT_STARTERS:
        if len(out) >= 5:
            break
        if q not in out:
            out.append(q)
    return out[:5]
