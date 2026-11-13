# The optional AI

The AI is **optional**. Every tool works without it. It exists to explain output,
answer questions and help you learn, and it can *propose* a command.

## Configuring it

Open **Settings → AI provider**.

### Local, with Ollama

1. Install [Ollama](https://ollama.com/download).
2. Pull a model, e.g. `ollama pull llama3`.
3. In the app: provider **Ollama**, base URL `http://127.0.0.1:11434`,
   model `llama3`.

Nothing leaves your machine.

### The four providers

`server/ai.py` supports four providers. Pick one in the Provider list; each
has its own default base URL and model, which you can change:

| Provider | Where it runs | Default base URL | Default model | Key needed |
| --- | --- | --- | --- | --- |
| Ollama (local) | your machine | `http://127.0.0.1:11434` | `llama3.1` | no |
| OpenAI-compatible | OpenAI or any gateway that speaks its API | `https://api.openai.com/v1` | `gpt-4o-mini` | yes |
| Anthropic | Anthropic's API | `https://api.anthropic.com` | `claude-sonnet-4-5` | yes |
| Google Gemini | Google's Generative Language API | `https://generativelanguage.googleapis.com/v1beta` | `gemini-2.0-flash` | yes |

The OpenAI-compatible option works with a self-hosted vLLM, LiteLLM or Azure
endpoint, as long as it speaks the same API. Use the **Test connection** button
to check a provider before you save it. It lists the models the endpoint
reports.

### Cloud providers

1. Choose the provider, leave the base URL as the default or set your own
   (for OpenAI-compatible gateways).
2. Choose a model, e.g. `gpt-4o-mini`, `claude-sonnet-4-5` or `gemini-2.0-flash`.
3. Paste an API key and save.

Each provider has its own saved key. The app sends a stored key only to the
base URL it was saved for (or the provider's default), and only over **https**
unless the base URL is a loopback address.

**Keys are stored with the Windows Data Protection API**, encrypted to your
Windows user account, under
`%LOCALAPPDATA%\KaliWindowsSubstitute\secrets`. They are never written to the
repository, the database or a log. Clearing a key in Settings deletes it. Treat a
key like a password: do not paste it into a shared machine.

Be aware that when you use a cloud model, **the text you send (including tool
output) leaves your machine** and is handled under that provider's terms. Do not
send it data you are not allowed to share.

## What it can and cannot do

It can:

- explain a tool's output in plain English;
- suggest a command or a next step;
- answer "what does this flag mean?" questions;
- propose a tool run, as structured data.

It cannot:

- run anything by itself. A proposal is rendered as a confirm dialog; the run
  only happens if you click **Confirm and run**;
- bypass the scope guard, the allowlist, the timeout or the output cap. A
  confirmed run goes through exactly the same path as a run you started by hand;
- reach the filesystem or the network except through the app.

## How a proposal works

The model is asked to answer with JSON when, and only when, a run is appropriate:

```json
{ "action": "run", "tool": "nmap",
  "payload": { "target": "192.168.1.10", "profile": "service" } }
```

The backend validates the shape, the UI shows what would run, and on confirmation
the normal `/api/tool/<id>` path runs it. If the target is public, the scope
guard still refuses it unless you confirm.

## Cost and privacy notes

- A local model costs nothing and sends nothing anywhere.
- A cloud model bills per token; tool output can be large, so the app truncates
  what it sends.
- If you do not want any of this, leave the provider set to **None**. The rest of
  the app is unaffected.

## Verified live (2026-10-14)

The full cloud path — Settings save, DPAPI key store, chat round-trip over the
internet — was exercised against a real free OpenAI-compatible endpoint and a
real model replied. A second request shape was declined by that endpoint's free
tier (`402 Payment Required`); the app surfaced it as a readable chat error
instead of failing. With a paid provider key the same code path applies.
