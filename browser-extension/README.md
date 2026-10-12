# Chat Monitor browser extension

Monitors the chats you type into **gemini.google.com**, **chatgpt.com** and **claude.ai** in
your browser. Every finished answer is sent to your Agent Observability dashboard, checked
with the same rules as your API traffic (personal data, prompt injection, refusals, your
contract's rules, the LLM judge), and the result appears as a small line under the answer.

```
you type in Gemini ──► Gemini answers ──► extension reads the finished turn
                                              │
                                              ▼
                        your API  /api/llm/ingest/browser-turn  ──► checks, alerts, dashboard
                                              │
                        "● Critical: Personal data in response · View"  ◄── shown under the answer
```

## Install (Chrome or Edge)

1. Open `chrome://extensions` (Edge: `edge://extensions`).
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and choose this `browser-extension` folder.
4. The extension's settings open from its toolbar icon → **Settings** (or *Details → Extension options*):
   - **API URL**: `http://127.0.0.1:8000` (where the API runs)
   - **Workspace API key**: dashboard → Settings → API keys → Create key
   - **Contract** (optional): a contract slug, e.g. `demo-support`, to apply its rules
5. Click **Test connection**, then reload any open Gemini / ChatGPT / Claude tabs.

Chat as usual. Each answer gets a status line once it has finished, and the call appears in
the dashboard under **Live calls** (source "Chat sites").

## What it sends, and what it does not

- Only **finished** answers, with the message that prompted them, the conversation id and the
  model name shown on the page.
- By default, only messages written **after** you open a chat; existing history is skipped
  (switch off "Only send messages written after a chat is opened" to include it).
- Nothing is sent while monitoring is paused (toolbar popup) or for sites you switch off.
- Your workspace API key is stored in this browser only (`chrome.storage.local`, not synced).
- Requests go from the extension's background worker straight to your API URL.
- Your workspace's privacy settings still apply (store content, mask PII, retention).

## Limits

- **Monitoring, not blocking:** the answer is already on your screen when it is checked.
  Blocking and auto-repair are only possible for apps that call the APIs through the gateway.
- **Browser only:** chats in the Gemini, ChatGPT or Claude mobile and desktop apps are not seen.
- **Page structure:** the extension reads each site's page. When a site redesigns, its reader in
  `content.js` (the `SITES` table) may need updating. Gemini and ChatGPT were verified against the
  live sites in October 2026; Claude requires sign-in and has not been verified yet.
- **Token counts** are estimated; consumer chat plans are not billed per token, so cost shows $0.
