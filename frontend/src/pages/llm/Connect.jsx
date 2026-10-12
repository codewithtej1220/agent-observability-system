import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../../api";
import { Async, Card } from "../../components/ui";

function Code({ text }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="code-wrap">
      <pre className="code">{text}</pre>
      <button className="copy" onClick={() => { navigator.clipboard?.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

const snippets = (u, project) => {
  const hdr = project ? project : "my-project";
  return {
    "OpenAI · Python": `from openai import OpenAI

client = OpenAI(
    base_url="${u.openai}",
    api_key="AOBS_API_KEY",  # your workspace key (aobs_...), not your OpenAI key
    default_headers={"X-AOBS-Project": "${hdr}"},  # optional: apply a prompt contract
)

resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "system", "content": "You are a support assistant."},
              {"role": "user", "content": "Where is my order?"}],
)
print(resp.choices[0].message.content)`,
    "OpenAI · JavaScript": `import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "${u.openai}",
  apiKey: process.env.AOBS_API_KEY,             // workspace key (aobs_...)
  defaultHeaders: { "X-AOBS-Project": "${hdr}" }, // optional
});

const resp = await client.chat.completions.create({
  model: "gpt-4o-mini",
  messages: [{ role: "user", content: "Where is my order?" }],
});`,
    "Claude · Python": `import anthropic

client = anthropic.Anthropic(
    base_url="${u.anthropic}",
    api_key="AOBS_API_KEY",  # workspace key (aobs_...)
    default_headers={"X-AOBS-Project": "${hdr}"},
)

msg = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=512,
    system="You are a support assistant.",
    messages=[{"role": "user", "content": "Where is my order?"}],
)
print(msg.content[0].text)`,
    "Claude · JavaScript": `import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic({
  baseURL: "${u.anthropic}",
  apiKey: process.env.AOBS_API_KEY,
  defaultHeaders: { "X-AOBS-Project": "${hdr}" },
});`,
    "Gemini · Python": `from google import genai
from google.genai import types

client = genai.Client(
    api_key="AOBS_API_KEY",  # workspace key (aobs_...)
    http_options=types.HttpOptions(
        base_url="${u.gemini}",
        headers={"X-AOBS-Project": "${hdr}"},
    ),
)

resp = client.models.generate_content(model="gemini-3.5-flash", contents="Where is my order?")
print(resp.text)`,
    "LangChain": `from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

gpt = ChatOpenAI(model="gpt-4o-mini", base_url="${u.openai}", api_key="AOBS_API_KEY",
                 default_headers={"X-AOBS-Project": "${hdr}"})
claude = ChatAnthropic(model="claude-sonnet-4-5", base_url="${u.anthropic}", api_key="AOBS_API_KEY",
                       default_headers={"X-AOBS-Project": "${hdr}"})`,
    curl: `curl ${u.openai}/chat/completions \\
  -H "Authorization: Bearer $AOBS_API_KEY" \\
  -H "Content-Type: application/json" \\
  -H "X-AOBS-Project: ${hdr}" \\
  -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hello"}]}'`,
  };
};

export default function Connect() {
  const info = useApi("/api/llm/connect");
  const keys = useApi("/api/workspace/api-keys");
  const [tab, setTab] = useState("OpenAI · Python");
  return (
    <Async state={info}>
      {(d) => {
        const sn = snippets(d.base_urls, d.contracts[0]);
        const hasKey = (keys.data || []).some((k) => !k.revoked);
        const anyCred = Object.values(d.credentials).some(Boolean);
        return (
          <>
            <div className="page-head">
              <div>
                <h1>Connect your LLMs</h1>
                <p>
                  Route your applications' calls to OpenAI, Claude and Gemini through the gateway. You change one setting (the base URL);
                  your code, prompts and SDKs stay the same. Every call is then logged, checked against your rules, and alerted on.
                </p>
              </div>
            </div>

            <div className="grid cols-3" style={{ marginBottom: 16 }}>
              <Card title={`1. Add provider keys ${anyCred ? "✓" : ""}`}>
                <div className="stack" style={{ gap: 6 }}>
                  {Object.entries(d.credentials).map(([p, ok]) => (
                    <div key={p} className="spread small"><span>{{ openai: "OpenAI", anthropic: "Anthropic (Claude)", gemini: "Google Gemini" }[p]}</span>
                      {ok ? <span className="badge healthy">✓ Stored</span> : <span className="badge neutral">Not added</span>}</div>
                  ))}
                  <Link className="small" to="/settings?tab=providers">Manage provider keys</Link>
                  <div className="small muted">Stored encrypted. Your apps never need to see them.</div>
                </div>
              </Card>
              <Card title={`2. Create a workspace API key ${hasKey ? "✓" : ""}`}>
                <div className="small text-2">Your apps authenticate to the gateway with a workspace key (<code>aobs_…</code>) in place of the provider key.</div>
                <Link className="small" to="/settings?tab=api-keys" style={{ display: "inline-block", marginTop: 8 }}>Create an API key</Link>
              </Card>
              <Card title="3. Point your SDK at the gateway">
                <dl className="kv small">
                  <dt>OpenAI</dt><dd className="mono">{d.base_urls.openai}</dd>
                  <dt>Claude</dt><dd className="mono">{d.base_urls.anthropic}</dd>
                  <dt>Gemini</dt><dd className="mono">{d.base_urls.gemini}</dd>
                </dl>
              </Card>
            </div>

            <Card title="Chatting on gemini.google.com, chatgpt.com or claude.ai?" style={{ marginBottom: 16 }}
                  sub="Chats typed into these websites do not go through the gateway. The Chat Monitor browser extension sends each finished answer here for checking.">
              <ol className="small text-2" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
                <li>Open <code>chrome://extensions</code> (Edge: <code>edge://extensions</code>) and turn on <strong>Developer mode</strong>.</li>
                <li>Click <strong>Load unpacked</strong> and select the project's <code>browser-extension</code> folder.</li>
                <li>Open the extension's settings: API URL <code>{d.api_url}</code>, a workspace API key, and optionally a contract slug.</li>
                <li>Click <strong>Test connection</strong>, then reload your chat tabs. Each answer gets a status line, and appears under
                  <Link to="/llm/calls?source=browser"> Live calls</Link>.</li>
              </ol>
              <div className="small muted" style={{ marginTop: 8 }}>
                Monitoring only (the answer is already on screen when it is checked). Mobile and desktop chat apps are not covered.
              </div>
            </Card>

            <Card title="Code" style={{ marginBottom: 16 }}>
              <div className="tabs">
                {Object.keys(sn).map((k) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{k}</button>)}
              </div>
              <Code text={sn[tab]} />
            </Card>

            <div className="grid cols-2">
              <Card title="Optional request headers" sub="Stripped before the request reaches the provider.">
                <table>
                  <tbody>
                    <tr><td className="mono small">X-AOBS-Project</td><td className="small">Contract slug: which rules apply and whether to monitor, block or repair. <Link to="/llm/contracts">Contracts</Link></td></tr>
                    <tr><td className="mono small">X-AOBS-Session</td><td className="small">Conversation id, to group the calls of one chat</td></tr>
                    <tr><td className="mono small">X-AOBS-User</td><td className="small">Your end-user's id</td></tr>
                    <tr><td className="mono small">X-AOBS-Tags</td><td className="small">Comma-separated labels (e.g. <code>web,beta</code>)</td></tr>
                    <tr><td className="mono small">X-AOBS-Credential</td><td className="small">Name of a stored provider key other than the default</td></tr>
                  </tbody>
                </table>
              </Card>
              <Card title="What your app sees">
                <ul className="small text-2" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>
                  <li><strong>Monitor mode</strong> (default): the provider's response, unchanged, with no added latency.</li>
                  <li><strong>Repair mode</strong>: a corrected response if the first one broke a critical rule; the header <code>x-aobs-enforcement: repaired</code> says so.</li>
                  <li><strong>Block mode</strong>, or repair that failed: HTTP 422 with <code>error.type = "aobs_policy_violation"</code>. SDKs raise it as an error (OpenAI: <code>UnprocessableEntityError</code>).</li>
                  <li>Every response carries <code>x-aobs-call-id</code>, which links to the call in the dashboard.</li>
                  <li>Consumer chat apps (chatgpt.com, claude.ai, gemini.google.com) have no API to route through; the gateway covers apps built on the APIs.</li>
                </ul>
              </Card>
            </div>
          </>
        );
      }}
    </Async>
  );
}
