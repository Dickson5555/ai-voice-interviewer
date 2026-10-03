# 🎙️ AI Voice Interviewer

### How I built a conversational AI that conducts real technical interviews — voice-first, observable, and shipped to production.

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Groq](https://img.shields.io/badge/Groq-gpt--oss--120b-F55036)](https://groq.com)
[![LangChain](https://img.shields.io/badge/LangChain-0.3-1C3C3C)](https://langchain.com)
[![LangSmith](https://img.shields.io/badge/LangSmith-Observable-FF6B35)](https://smith.langchain.com)
[![Deployed on Render](https://img.shields.io/badge/Deployed%20on-Render-46E3B7)](https://render.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## The Moment This Started

I was preparing for a data science interview and realized something uncomfortable: I had no way to *practice being interviewed*. Not the questions — I had plenty of those. The **experience**. The part where someone listens to your answer, reacts to it, pushes back a little, and moves the conversation forward. The part that actually determines whether you get the job.

The options available to me were bad:

- **Pay $100+/hour** for a human mock interviewer — unsustainable
- **Record myself** talking to a blank screen — no feedback, no adaptivity
- **Grind question banks** — static, impersonal, and they can't respond to what I actually said

So I built the thing I wished existed. **An AI interviewer that listens, evaluates, scores, and adapts — in real time, in the browser, with zero friction.**

No signup. No app install. Click one button and you're being interviewed by a conversational AI that reacts to your actual words.

But here's the honest part: **the project you're reading about is not the first version.** It's the version that survived contact with reality. What follows is the story of how a naive prototype became a system.

---

## What It Does

From the user's side, it's simple:

- 🎤 **You speak** — browser-native speech recognition captures your answer
- 🧠 **It evaluates** — an LLM trained to interview for Data Science, ML, SQL, Analytics, and AI roles
- 📊 **You get a score** — out of 10, with short constructive feedback
- 💬 **It speaks back** — reaction → feedback → score → next question, every turn
- 🌊 **You see it think** — an iridescent animated orb shifts state through idle / listening / thinking / speaking
- 🔍 **Every LLM call is traced** in LangSmith — latency, tokens, prompt, completion, failures

From the engineer's side, there's a lot more going on under that glassy orb. That's the rest of this document.

---

## Demo

**Live demo:** `https://vt.tiktok.com/ZSbmRQ3Hb/`

---

## Act 1: The Naive Prototype

The first version worked — technically. It had a FastAPI backend, a WebSocket connection, a Groq LLM behind a LangChain chain, and a talking avatar on the frontend. You clicked Start, it asked a question, you answered, it responded.

It also **failed 1 in 5 turns**.

The failure was silent. The LLM would respond, the backend would try to parse it as JSON, the parse would fail, and the user would see:

> *"I couldn't quite follow that. Try to structure your answer and explain the key idea clearly."*

For two days, I thought the mic was broken. It wasn't. The mic was fine. The **agent** was choking, and the fallback response was doing exactly what it was designed to do — hide the failure from the user.

That's when I learned the first real lesson of AI engineering: **graceful fallbacks are essential, but they will also hide every bug you have if you're not careful.** The fallback became my signal. Every time a user saw that message, somewhere in the logs, something had gone wrong.

I turned on `logging.exception`. I added the raw LLM content to every failure path. And then I started peeling back the layers.

---

## Act 2: The Four Bugs Nobody Warns You About

Each of these took real time to find. Each of them taught me something about building on top of LLMs.

### Bug #1 — The API Parameter That Lied

I was passing `response_format={"type": "json_object"}` inside `model_kwargs` on the `ChatGroq` client. This looked correct. It was not correct.

In `langchain-groq`, `response_format` is a **top-level parameter**, not a `model_kwargs` entry. Passing it inside `model_kwargs` sends it as a raw API parameter that Groq rejects with a **400 Bad Request** — which throws an exception inside the chain, gets caught by my broad `except Exception`, and silently returns the fallback.

**The fix:** Move `response_format` to the top level. One line. Two days of debugging.

**The lesson:** When an LLM library wraps an API, it sometimes renames or relocates parameters. Read the source. Don't trust the docs to be current.

### Bug #2 — The Model That Vanished

The first time I deployed, the app crashed immediately:



Groq had **deprecated the model mid-project**. My code was fine. The model was gone.

**The fix:** Swap to `openai/gpt-oss-120b` — Groq's current production model with JSON mode and a 131K context window.

**The lesson:** Never let a third-party dependency be a single point of failure. Wrap it. Have a fallback. Assume every model you build on will eventually be removed.

### Bug #3 — The Template That Ate My Candidate's Words

I was using `ChatPromptTemplate.from_template()` from LangChain. This treats `{anything}` as a template variable.

A candidate answered a question that included the phrase *"What happens if `{x}` is null?"*

The prompt engine saw `{x}`, tried to substitute a variable called `x`, found nothing, and raised `KeyError`. The turn died. The user saw the fallback.

**The fix:** Stop using `ChatPromptTemplate` for this use case. Build messages manually with `SystemMessage` and `HumanMessage`. Candidate input is now **data**, never **template**.

**The lesson:** Anything a user types is a potential injection vector. This is a security-adjacent decision, not a style preference. The difference between a chatbot and a system is whether it survives hostile input.

### Bug #4 — The Memory That Never Grew Up

My session memory was a plain Python dict. It stored every message from every session forever. On my local machine, this looked fine. On a server that runs for weeks, it's a memory leak wearing a feature's costume.

There was also a **second** problem: the memory service had a `get_history()` method — but **nothing ever called it**. The conversation history was being written but never read. Every LLM call was blind to the prior conversation.

**The fix:** Bounded `deque(maxlen=40)` per session, thread-safe with a lock, explicit `clear_session()` on every exit path including `finally`. And the WebSocket handler now actually passes `session_id` through to the agent so history can be retrieved.

**The lesson:** Memory is a resource. Resources need bounds. And methods that exist but are never called are worse than methods that don't exist — they give you false confidence.

---

## Act 3: Building for Reliability, Not Demos

Once the bugs were fixed, the interesting work began: making the system **robust**. Not "works in a demo" robust. "Works when a stranger uses it on a bad network with an unusual accent" robust.

### Structured Outputs, Not Vibes

Even with JSON mode enabled, Llama-family models on Groq sometimes:

- Wrap JSON in markdown fences (````json ... ````)
- Prefix the JSON with conversational prose
- Nest the response under a `"response"` or `"data"` key

Any one of these breaks a naive `json.loads()`. So I built a **three-layer defense:**

```python
# 1. Force JSON mode at the API level
# 2. Strip markdown fences
# 3. Extract the first balanced {...} object
# 4. Unwrap single-key nesting
# 5. Validate against a Pydantic schema with coercion

Layer five matters more than people realize. The InterviewResponse schema has a field_validator that coerces the score — so if the model returns "8/10" or "8.0" or 8.0 instead of 8, the schema fixes it silently. Forgiving validation beats strict rejection when the data source is an LLM.

---

## Observability From Day One
I wired LangSmith in before the first deployment. Not after. Not "when I have time." Before.

Every LLM call is now traced with:

The full prompt (system + history + candidate answer)

The raw completion

Token usage

Latency per turn

Fallback triggers — so I can see why a turn failed, not just that it did

This is the single highest-leverage decision I made on the project. When the fallback fires in production, I don't have to guess. I open LangSmith, click the trace, and the answer is right there.

You cannot improve what you cannot measure. Observability is not a "later" problem. It's a day-one problem.

The Design That Doesn't Look Like a Chatbot
The original UI had a talking avatar. It looked like every other LLM wrapper on the internet — a face, a chat box, a button.

The redesign started from a single reference image: an iridescent liquid orb, floating on pure black. I wanted the interface to feel alive rather than chatty.

The orb is built in pure CSS and SVG — no Three.js, no WebGL, no canvas library. Roughly 200 lines of CSS produce:

A rotating conic gradient core with layered radial glows

A soft outer rim that bleeds into the background

Four distinct states driven by a JavaScript state machine:

idle — slow breathing, calm colors

listening — pulse rings radiating outward

thinking — fast subtle vibration, desaturated

speaking — strong pulse, brightest hue

The Start button uses backdrop-filter: blur(20px) for a true glassmorphic effect — not a blurred PNG pretending to be glass. Every state transition is a data-state attribute change, so the CSS handles all animation. The JavaScript never touches animation directly.

The lesson: Design quality isn't decoration. It's the difference between a project that gets scrolled past and one that gets remembered.