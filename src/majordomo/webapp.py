"""The web app: ONE window, everything inside it, plus a small JSON API.

FastAPI serves a single self-contained page at ``/`` — the window:
a slim header (head icon, wordmark, the gold fingerprint, an
"On watch" status), the living face with his thought bubble, the
chat window, and the Ideas · Feed · Goal · Artifact reads, all in
one panel. No separate pages: the reads open inside the window, and
the fingerprint opens Soul & Memory inside the window too. (``/self``
still serves the same self files as a standalone page, for links
made before the window.)

Endpoints:

- ``GET  /health``            — liveness, provider name
- ``POST /chat``              — {message, session_id?, approve} → reply + events
- ``GET  /sessions``          — session summaries (the Feed read)
- ``GET  /memory``            — long-term memory entries
- ``GET  /self``              — the self files page (standalone)
- ``GET  /self-data``         — the self files as JSON (the in-window read)
- ``GET  /goals``             — the owner's goals
- ``POST /goals``             — add a goal {text, next_move}
- ``POST /goals/{id}/next-move`` / ``/done`` / ``DELETE /goals/{id}``
- ``GET  /files``             — workspace files (name, size, modified)
- ``GET  /files/{name}``      — download one workspace file (sandboxed)
- ``GET  /brand/{name}``      — the brand images shipped in static/

Approvals ride on the request: ``approve: true`` approves acting tools
for that one message; without it, acting tools are declined and the
agent says so. A background tick fires due reminders into the
``inbox`` session every 30 seconds and runs the initiative engine
(mail watch + escalation) alongside.

Reach it from a phone with Tailscale Serve — see the README.
"""

from __future__ import annotations

import asyncio
import html
import json
import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

log = structlog.get_logger(__name__)

from . import __version__
from .config import Settings
from .goals import GoalStore
from .providers import Provider
from .runtime import Runtime, build_runtime
from .self_files import SELF_FILES, SelfStore
from .tools import approve_all, approve_none

_STATIC = Path(__file__).parent / "static"

# The brand files the window serves at /brand/<name>: the real assets,
# copied from the repository's assets/ (the head from Pocket Pip's
# asset, byte-identical). Anything not listed here is a 404.
_BRAND_FILES: dict[str, str] = {
    "roboto-head.png": "image/png",
    "icon.jpg": "image/jpeg",
    "banner.jpg": "image/jpeg",
    "window.gif": "image/gif",
    "fingerprint.svg": "image/svg+xml",
}

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Majordomo</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: system-ui, sans-serif; background: #03060D; color: #E8EAF0;
         min-height: 100vh; display: flex; align-items: flex-start; justify-content: center;
         padding: 18px 10px; }
  #window { width: 100%; max-width: 880px; background: #060A14; border: 1px solid #22304F;
            border-radius: 18px; overflow: hidden; box-shadow: 0 18px 60px rgba(0,0,0,.55); }
  header { padding: 12px 16px; border-bottom: 2px solid #E8B84B; display: flex;
           align-items: center; gap: 10px; }
  header img.mark { width: 30px; height: 30px; border-radius: 8px; }
  header h1 { font-size: 19px; margin: 0; color: #E8B84B; letter-spacing: .14em; font-weight: 700; }
  header .spacer { flex: 1; }
  header .watch { color: #2DD4BF; font-size: 12px; }
  #fingerprint { background: none; border: 0; padding: 2px; cursor: pointer; line-height: 0; }
  #stage { position: relative; min-height: 252px; padding: 14px 16px 8px;
           background: radial-gradient(120% 130% at 18% 100%, #0D1B36 0%, #060A14 62%); }
  #bubble { position: absolute; top: 14px; right: 16px; max-width: 46%; background: #111B36;
            border: 1px solid #22304F; border-radius: 14px; padding: 9px 13px;
            font-size: 13.5px; color: #C9D4EE; }
  #headwrap { position: absolute; left: 18px; bottom: 8px; width: 168px; text-align: center; }
  #head { width: 168px; height: auto; display: block; cursor: pointer;
          transition: transform .35s ease; transform-origin: 50% 88%; }
  #head.bounce { animation: bounce .5s ease; }
  #head.blink { transform: scaleY(.93); }
  @keyframes bounce { 30% { transform: translateY(-13px); } 60% { transform: translateY(2px); } }
  #headstatus { font-size: 12px; color: #8FA3C8; min-height: 15px; margin-top: 2px; }
  #chat { border-top: 1px solid #22304F; padding: 10px 16px 4px; }
  #log { max-height: 300px; overflow-y: auto; padding-right: 4px; }
  .msg { margin: 8px 0; padding: 9px 13px; border-radius: 12px; white-space: pre-wrap;
         line-height: 1.45; font-size: 14.5px; }
  .user { background: #111B36; margin-left: 14%; }
  .agent { background: #0D1526; border: 1px solid #22304F; margin-right: 14%; }
  .tool { color: #8FA3C8; font-size: 12px; margin: 2px 0 2px 8px; }
  form#composer { display: flex; gap: 8px; align-items: center; padding: 10px 0 12px; }
  input[type=text] { flex: 1; padding: 11px 12px; border-radius: 10px; border: 1px solid #22304F;
                     background: #111B36; color: #E8EAF0; font-size: 15px; min-width: 0; }
  button.send { padding: 11px 17px; border-radius: 10px; border: 0; background: #E8B84B;
                color: #060A14; font-weight: 700; font-size: 15px; cursor: pointer; }
  label.approve { display: flex; align-items: center; gap: 5px; font-size: 12.5px;
                  color: #8FA3C8; white-space: nowrap; }
  nav#reads { display: flex; gap: 8px; padding: 10px 16px 2px; flex-wrap: wrap; }
  nav#reads button { flex: 1; min-width: 90px; padding: 10px 0; border-radius: 10px;
                     border: 1px solid #22304F; background: #0D1526; color: #E8EAF0;
                     font-size: 14.5px; cursor: pointer; }
  nav#reads button.active { border-color: #E8B84B; color: #E8B84B; }
  #steps { display: flex; align-items: center; gap: 0; padding: 12px 22px 0; }
  #steps .step { display: flex; flex-direction: column; align-items: center; gap: 4px;
                 font-size: 11.5px; color: #8FA3C8; }
  #steps .dot { width: 10px; height: 10px; border-radius: 50%; background: #22304F; }
  #steps .step.on { color: #E8EAF0; }
  #steps .step.on .dot { background: #E8B84B; box-shadow: 0 0 8px #E8B84B; }
  #steps .bar { flex: 1; height: 2px; background: #22304F; margin: 0 6px 16px; }
  #agents { display: flex; gap: 16px; justify-content: center; padding: 7px 0 13px;
            font-size: 12px; color: #8FA3C8; }
  #agents .agent-dot::before { content: "● "; color: #22304F; }
  #agents .agent-dot.on { color: #2DD4BF; }
  #agents .agent-dot.on::before { color: #2DD4BF; }
  #read { display: none; border-top: 1px solid #22304F; padding: 14px 18px 18px;
          background: #081020; }
  #read.open { display: block; }
  #read h2 { margin: 0 0 4px; font-size: 16px; color: #E8B84B; }
  #read .sub { color: #8FA3C8; font-size: 12.5px; margin-bottom: 10px; }
  #read .close { float: right; background: none; border: 1px solid #22304F; color: #8FA3C8;
                 border-radius: 8px; padding: 4px 10px; cursor: pointer; }
  #read ul { margin: 6px 0; padding-left: 18px; line-height: 1.55; font-size: 14.5px; }
  #read .row { display: flex; align-items: center; gap: 9px; padding: 8px 0;
               border-bottom: 1px solid #14213F; font-size: 14px; }
  #read .row:last-child { border-bottom: 0; }
  #read .tag { font-size: 10.5px; font-weight: 700; letter-spacing: .06em; color: #060A14;
               background: #2DD4BF; border-radius: 5px; padding: 2px 6px; white-space: nowrap; }
  #read .tag.img { background: #E8B84B; }
  #read .size { color: #8FA3C8; font-size: 12px; margin-left: auto; white-space: nowrap; }
  #read a.dl { color: #E8B84B; text-decoration: none; font-weight: 600; white-space: nowrap; }
  #read .thumbs { display: flex; gap: 10px; flex-wrap: wrap; margin: 8px 0 4px; }
  #read .thumbs figure { margin: 0; text-align: center; }
  #read .thumbs img { height: 74px; width: auto; max-width: 150px; object-fit: contain;
                      border: 1px solid #22304F; border-radius: 8px; background: #0D1526; }
  #read .thumbs figcaption { font-size: 11px; color: #8FA3C8; margin-top: 3px; }
  #read section.selfsec { background: #0D1526; border: 1px solid #22304F; border-radius: 10px;
                          padding: 10px 14px; margin: 10px 0; }
  #read section.selfsec h3 { margin: 0 0 3px; font-size: 14.5px; color: #E8B84B; }
  #read section.selfsec .file { color: #8FA3C8; font-size: 11.5px; margin-bottom: 6px; }
  #read section.selfsec pre { white-space: pre-wrap; margin: 0; font-family: inherit;
                              font-size: 13.5px; line-height: 1.5; }
  #read .goaltext { flex: 1; }
  #read .goaltext.done { text-decoration: line-through; color: #8FA3C8; }
  #read .nextmove { color: #2DD4BF; font-size: 12.5px; }
  #read input.goal, #read input.gnext { padding: 8px 10px; border-radius: 8px;
      border: 1px solid #22304F; background: #111B36; color: #E8EAF0; font-size: 14px; }
  #read input.gnext { width: 170px; }
  #read button.mini { padding: 7px 11px; border-radius: 8px; border: 1px solid #22304F;
                      background: #111B36; color: #E8EAF0; cursor: pointer; font-size: 13px; }
  #read form#goalform { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
  #read form#goalform input.goal { flex: 1; min-width: 130px; }
  .empty { color: #8FA3C8; font-size: 14px; padding: 6px 0; }
  @media (prefers-reduced-motion: reduce) { #head { transition: none; } #head.bounce { animation: none; } }
</style>
</head>
<body>
<div id="window">
  <header>
    <img class="mark" src="/brand/icon.jpg" alt="Majordomo icon">
    <h1>MAJORDOMO</h1>
    <button id="fingerprint" title="Soul &amp; Memory" aria-label="Open Soul and Memory"></button>
    <div class="spacer"></div>
    <span class="watch">● On watch</span>
  </header>

  <div id="stage">
    <div id="bubble">Watching for mail…</div>
    <div id="headwrap">
      <img id="head" src="/brand/roboto-head.png" alt="Domo — Roboto's robot head">
      <div id="headstatus"></div>
    </div>
  </div>

  <div id="chat">
    <div id="log"></div>
    <form id="composer">
      <input type="text" id="text" placeholder="Ask Majordomo…" autocomplete="off">
      <label class="approve"><input type="checkbox" id="approve"> approve actions</label>
      <button type="submit" class="send">Send</button>
    </form>
  </div>

  <nav id="reads">
    <button data-read="ideas">Ideas</button>
    <button data-read="feed">Feed</button>
    <button data-read="goal">Goal</button>
    <button data-read="artifact">Artifact</button>
  </nav>

  <div id="steps"></div>
  <div id="agents"></div>

  <div id="read">
    <button class="close" id="readclose">Close</button>
    <h2 id="readtitle"></h2>
    <div class="sub" id="readsub"></div>
    <div id="readbody"></div>
  </div>
</div>

<script>
  document.getElementById('fingerprint').innerHTML = FINGERPRINT_INLINE;

  // --- the face: bubble, steps, and agent dots move together ---
  const STEPS = ['Plan', 'Build', 'Write', 'Check', 'Done'];
  const AGENTS = ['Domo', 'Mail', 'Memory', 'Brief', 'Gate'];
  const SCENES = [
    { line: 'Checking mail…', step: 0, agent: 1 },
    { line: 'Filing a fact to memory…', step: 2, agent: 2 },
    { line: 'Watching for mail…', step: 3, agent: 0 },
    { line: 'Morning brief is ready.', step: 4, agent: 3 },
    { line: 'Asking before acting.', step: 3, agent: 4 },
  ];
  const stepsEl = document.getElementById('steps');
  STEPS.forEach((name, i) => {
    const s = document.createElement('div'); s.className = 'step'; s.dataset.i = i;
    s.innerHTML = '<div class="dot"></div><div></div>';
    s.lastChild.textContent = name; stepsEl.appendChild(s);
    if (i < STEPS.length - 1) { const b = document.createElement('div'); b.className = 'bar'; stepsEl.appendChild(b); }
  });
  const agentsEl = document.getElementById('agents');
  AGENTS.forEach((name, i) => {
    const a = document.createElement('span'); a.className = 'agent-dot'; a.dataset.i = i;
    a.textContent = name; agentsEl.appendChild(a);
  });
  const bubble = document.getElementById('bubble');
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let scene = 0, readOpen = false;
  function showScene() {
    const sc = SCENES[scene % SCENES.length]; scene++;
    bubble.textContent = sc.line;
    stepsEl.querySelectorAll('.step').forEach(el => el.classList.toggle('on', +el.dataset.i <= sc.step));
    agentsEl.querySelectorAll('.agent-dot').forEach(el => el.classList.toggle('on', +el.dataset.i === sc.agent));
  }
  showScene();
  setInterval(() => { if (!readOpen) showScene(); }, 3400);

  // --- the head: tap, lean, blink — transforms only, image untouched ---
  const head = document.getElementById('head');
  const headStatus = document.getElementById('headstatus');
  const HEAD_LINES = ['Right here.', 'On it.', 'Watching the house.', 'At your service.'];
  let headLine = 0, leanTimer = null;
  head.addEventListener('click', () => {
    headStatus.textContent = HEAD_LINES[headLine++ % HEAD_LINES.length];
    if (!reduceMotion) { head.classList.remove('bounce'); void head.offsetWidth; head.classList.add('bounce'); }
  });
  document.getElementById('stage').addEventListener('pointermove', (e) => {
    if (reduceMotion || e.pointerType === 'touch') return;
    const r = head.getBoundingClientRect();
    const dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2);
    const dist = Math.hypot(dx, dy);
    if (dist < 340) {
      head.style.transform = 'translate(' + (dx / 46) + 'px,' + (dy / 60) + 'px) rotate(' + (dx / 130) + 'deg)';
      clearTimeout(leanTimer);
      leanTimer = setTimeout(() => { head.style.transform = ''; }, 260);
    }
  });
  if (!reduceMotion) setInterval(() => {
    head.classList.add('blink'); setTimeout(() => head.classList.remove('blink'), 170);
  }, 4600);

  // --- the chat window: the real /chat API, session "window" ---
  const log = document.getElementById('log');
  function add(text, cls) {
    const div = document.createElement('div');
    div.className = cls; div.textContent = text;
    log.appendChild(div); log.scrollTop = log.scrollHeight;
  }
  document.getElementById('composer').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = document.getElementById('text');
    const text = input.value.trim(); if (!text) return;
    add(text, 'msg user'); input.value = '';
    const res = await fetch('/chat', { method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ message: text, session_id: 'window',
        approve: document.getElementById('approve').checked }) });
    const data = await res.json();
    for (const ev of data.events) {
      if (ev.kind === 'tool_call') add('⚙ ' + ev.text, 'tool');
      if (ev.kind === 'declined') add('⛔ ' + ev.text, 'tool');
    }
    add(data.reply, 'msg agent');
  });

  // --- the reads: briefing panels inside the window ---
  const readEl = document.getElementById('read');
  const readTitle = document.getElementById('readtitle');
  const readSub = document.getElementById('readsub');
  const readBody = document.getElementById('readbody');
  const readButtons = document.querySelectorAll('nav#reads button');
  function openRead(name) {
    readOpen = true; readEl.classList.add('open');
    readButtons.forEach(b => b.classList.toggle('active', b.dataset.read === name));
    readBody.innerHTML = '';
    if (name === 'ideas') showIdeas();
    if (name === 'feed') showFeed();
    if (name === 'goal') showGoals();
    if (name === 'artifact') showArtifact();
    if (name === 'soul') showSoul();
  }
  function closeRead() {
    readOpen = false; readEl.classList.remove('open');
    readButtons.forEach(b => b.classList.remove('active'));
  }
  document.getElementById('readclose').addEventListener('click', closeRead);
  readButtons.forEach(b => b.addEventListener('click', () =>
    (readEl.classList.contains('open') && b.classList.contains('active')) ? closeRead() : openRead(b.dataset.read)));
  document.getElementById('fingerprint').addEventListener('click', () =>
    (readEl.classList.contains('open') && readTitle.textContent === 'Soul & Memory') ? closeRead() : openRead('soul'));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeRead(); });

  function showIdeas() {
    readTitle.textContent = 'Ideas';
    readSub.textContent = 'Worth a look — Domo keeps the list short.';
    const ul = document.createElement('ul');
    ['Give Domo a real brain: plug in any provider key, or a local model, and the demo answers become real ones.',
     'Leave the daemon on overnight — the morning brief is assembled and waiting before you ask.',
     'Wire one MCP server you already use; every tool it serves joins the registry behind the same approval gate.',
     'Say "remember…" once — memory is a plain file you can read, edit, and back up.'].forEach(t => {
      const li = document.createElement('li'); li.textContent = t; ul.appendChild(li);
    });
    readBody.appendChild(ul);
  }

  async function showFeed() {
    readTitle.textContent = 'Feed';
    readSub.textContent = 'Latest activity — your conversations with Domo.';
    readBody.innerHTML = '<div class="empty">Loading…</div>';
    const sessions = await (await fetch('/sessions')).json();
    readBody.innerHTML = '';
    if (!sessions.length) { readBody.innerHTML = '<div class="empty">Nothing yet — say hello in the chat window.</div>'; return; }
    sessions.slice(0, 8).forEach(s => {
      const row = document.createElement('div'); row.className = 'row';
      const label = document.createElement('span');
      label.textContent = (s.title || 'Conversation') + ' · ' + s.message_count + ' messages';
      const when = document.createElement('span'); when.className = 'size';
      when.textContent = (s.created_at || '').slice(0, 10);
      row.appendChild(label); row.appendChild(when); readBody.appendChild(row);
    });
  }

  async function showGoals() {
    readTitle.textContent = 'Goal';
    readSub.textContent = 'Your goals, and the next move on each. Saved on this machine.';
    readBody.innerHTML = '<div class="empty">Loading…</div>';
    const goals = await (await fetch('/goals')).json();
    readBody.innerHTML = '';
    if (!goals.length) {
      const d = document.createElement('div'); d.className = 'empty';
      d.textContent = 'No goals yet — add the first one below.'; readBody.appendChild(d);
    }
    goals.forEach(g => {
      const row = document.createElement('div'); row.className = 'row';
      const check = document.createElement('input'); check.type = 'checkbox'; check.checked = !!g.done;
      check.title = 'Mark done';
      check.addEventListener('change', async () => {
        await fetch('/goals/' + g.id + '/done', { method: 'POST',
          headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ done: check.checked }) });
        showGoals();
      });
      const text = document.createElement('div'); text.className = 'goaltext' + (g.done ? ' done' : '');
      text.textContent = g.text;
      const nm = document.createElement('div'); nm.className = 'nextmove';
      nm.textContent = g.next_move ? 'Next: ' + g.next_move : 'No next move yet';
      text.appendChild(document.createElement('br')); text.appendChild(nm);
      const input = document.createElement('input'); input.className = 'gnext';
      input.placeholder = 'Set next move…'; input.value = g.next_move || '';
      const save = document.createElement('button'); save.className = 'mini'; save.textContent = 'Save';
      save.addEventListener('click', async () => {
        await fetch('/goals/' + g.id + '/next-move', { method: 'POST',
          headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ next_move: input.value }) });
        showGoals();
      });
      const del = document.createElement('button'); del.className = 'mini'; del.textContent = 'Remove';
      del.addEventListener('click', async () => {
        await fetch('/goals/' + g.id, { method: 'DELETE' }); showGoals();
      });
      row.appendChild(check); row.appendChild(text); row.appendChild(input);
      row.appendChild(save); row.appendChild(del);
      readBody.appendChild(row);
    });
    const form = document.createElement('form'); form.id = 'goalform';
    const gtext = document.createElement('input'); gtext.className = 'goal'; gtext.placeholder = 'New goal…';
    const gnext = document.createElement('input'); gnext.className = 'goal'; gnext.placeholder = 'Next move…';
    const addBtn = document.createElement('button'); addBtn.className = 'mini'; addBtn.type = 'submit'; addBtn.textContent = 'Add goal';
    form.appendChild(gtext); form.appendChild(gnext); form.appendChild(addBtn);
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const t = gtext.value.trim(); if (!t) return;
      await fetch('/goals', { method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ text: t, next_move: gnext.value.trim() }) });
      showGoals();
    });
    readBody.appendChild(form);
  }

  const BRAND = [
    { name: 'roboto-head.png', tag: 'IMAGE' },
    { name: 'icon.jpg', tag: 'IMAGE' },
    { name: 'banner.jpg', tag: 'IMAGE' },
    { name: 'window.gif', tag: 'IMAGE' },
    { name: 'fingerprint.svg', tag: 'IMAGE' },
  ];
  function tagFor(name) {
    const ext = name.split('.').pop().toLowerCase();
    return { html: 'HTML', htm: 'HTML', json: 'JSON', md: 'DOC', txt: 'DOC',
             docx: 'DOC', pptx: 'DOC', xlsx: 'DOC', pdf: 'DOC',
             png: 'IMAGE', jpg: 'IMAGE', jpeg: 'IMAGE', gif: 'IMAGE', svg: 'IMAGE', webp: 'IMAGE' }[ext] || 'FILE';
  }
  function fileRow(name, href, size, tag) {
    const row = document.createElement('div'); row.className = 'row';
    const t = document.createElement('span'); t.className = 'tag' + (tag === 'IMAGE' ? ' img' : '');
    t.textContent = tag;
    const n = document.createElement('span'); n.textContent = name;
    row.appendChild(t); row.appendChild(n);
    if (size !== null && size !== undefined) {
      const s = document.createElement('span'); s.className = 'size';
      s.textContent = size < 1024 ? size + ' B' : Math.round(size / 102.4) / 10 + ' KB';
      row.appendChild(s);
    }
    const a = document.createElement('a'); a.className = 'dl'; a.href = href;
    a.setAttribute('download', ''); a.textContent = 'Download';
    row.appendChild(a);
    return row;
  }

  async function showArtifact() {
    readTitle.textContent = 'Artifact';
    readSub.textContent = 'The files shelf — everything in the workspace, plus his brand files. Tap to download.';
    readBody.innerHTML = '';
    const thumbs = document.createElement('div'); thumbs.className = 'thumbs';
    [['icon.jpg', 'Icon'], ['banner.jpg', 'Banner'], ['window.gif', 'The window'], ['fingerprint.svg', 'Fingerprint']]
      .forEach(([file, caption]) => {
        const fig = document.createElement('figure');
        const img = document.createElement('img'); img.src = '/brand/' + file; img.alt = caption;
        const cap = document.createElement('figcaption'); cap.textContent = caption;
        fig.appendChild(img); fig.appendChild(cap); thumbs.appendChild(fig);
      });
    readBody.appendChild(thumbs);
    const files = await (await fetch('/files')).json();
    if (!files.length) {
      const d = document.createElement('div'); d.className = 'empty';
      d.textContent = 'The workspace is empty — ask Domo to make something and it lands here.';
      readBody.appendChild(d);
    }
    files.forEach(f => readBody.appendChild(fileRow(f.name, '/files/' + encodeURIComponent(f.name), f.size, tagFor(f.name))));
    BRAND.forEach(b => readBody.appendChild(fileRow(b.name, '/brand/' + b.name, null, b.tag)));
  }

  async function showSoul() {
    readTitle.textContent = 'Soul & Memory';
    readSub.textContent = 'Who he is, who he serves, and what he keeps — read-only here; edit the files to change him.';
    readBody.innerHTML = '<div class="empty">Loading…</div>';
    const sections = await (await fetch('/self-data')).json();
    readBody.innerHTML = '';
    sections.forEach(s => {
      const sec = document.createElement('section'); sec.className = 'selfsec';
      const h = document.createElement('h3'); h.textContent = s.title;
      const f = document.createElement('div'); f.className = 'file';
      f.textContent = s.file + ' · read-only';
      const pre = document.createElement('pre');
      pre.textContent = s.text === null ? 'This file is missing.' : s.text;
      sec.appendChild(h); sec.appendChild(f); sec.appendChild(pre);
      readBody.appendChild(sec);
    });
  }
</script>
</body>
</html>
"""


# Majordomo's mark, inlined for the /self header and the window's
# fingerprint button — the same gold fingerprint that ships as
# assets/fingerprint.svg in the repository.
FINGERPRINT_SVG = """<svg viewBox="0 0 100 100" width="30" height="30" role="img" aria-label="Majordomo fingerprint mark">
  <path d="M 52.8 44.7 A 5.5 6.2 0 1 1 47.7 44.4" fill="none" stroke="#E8B84B" stroke-width="3.2" stroke-linecap="round"/>
  <path d="M 45.6 39.3 A 10.5 11.8 0 1 1 40.9 44.1" fill="none" stroke="#E8B84B" stroke-width="3.2" stroke-linecap="round"/>
  <path d="M 52.7 32.9 A 15.5 17.4 0 1 1 46.0 33.2" fill="none" stroke="#E8B84B" stroke-width="3.2" stroke-linecap="round"/>
  <path d="M 35.5 33.8 A 20.5 23.0 0 1 1 30.2 44.1" fill="none" stroke="#E8B84B" stroke-width="3.2" stroke-linecap="round"/>
  <path d="M 47.8 21.5 A 25.5 28.6 0 1 1 41.3 23.2" fill="none" stroke="#E8B84B" stroke-width="3.2" stroke-linecap="round"/>
  <path d="M 22.4 35.6 A 30.5 34.2 0 1 1 19.5 50.0" fill="none" stroke="#E8B84B" stroke-width="3.2" stroke-linecap="round"/>
  <path d="M 40.8 11.6 A 35.5 39.8 0 1 1 35.0 14.0" fill="none" stroke="#E8B84B" stroke-width="3.2" stroke-linecap="round"/>
  <path d="M 72.7 86.2 A 39.5 44.2 0 0 1 27.3 86.2" fill="none" stroke="#E8B84B" stroke-width="3.2" stroke-linecap="round"/>
  <path d="M 14.2 31.3 A 39.5 44.2 0 0 1 85.8 31.3" fill="none" stroke="#E8B84B" stroke-width="3.2" stroke-linecap="round"/>
</svg>"""

_SELF_TITLES = {
    "SOUL.md": "Soul",
    "IDENTITY.md": "Identity",
    "USER.md": "User",
    "MEMORY.md": "Memory",
}

_SELF_STYLE = """
  :root { color-scheme: dark; }
  body { margin: 0; font-family: system-ui, sans-serif; background: #060A14; color: #E8EAF0; }
  header { padding: 14px 18px; border-bottom: 2px solid #E8B84B; display: flex;
           justify-content: space-between; align-items: center; }
  header .brand { display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 20px; margin: 0; color: #E8B84B; letter-spacing: .04em; }
  header span, header a { color: #2DD4BF; font-size: 12px; }
  main { padding: 16px 18px 60px; max-width: 760px; margin: 0 auto; }
  section { background: #0D1526; border: 1px solid #22304F; border-radius: 12px;
            padding: 14px 18px; margin: 14px 0; }
  section h2 { margin: 0 0 4px; font-size: 16px; color: #E8B84B; }
  section .file { color: #8FA3C8; font-size: 12px; margin-bottom: 8px; }
  section pre { white-space: pre-wrap; line-height: 1.5; margin: 0;
                font-family: inherit; font-size: 14px; }
  .missing { color: #8FA3C8; font-style: italic; }
  p.note { color: #8FA3C8; font-size: 13px; line-height: 1.5; }
"""


def render_self_page(store: SelfStore) -> str:
    """The /self page: the self files, read-only, in the app's style.

    Soul, Identity, User, and the curated Memory section — the same
    files the agent assembles into its system prompt, shown exactly
    as they sit on disk. Editing happens in the files themselves.
    """
    sections: list[str] = []
    for name in SELF_FILES:
        text = store.read(name)
        if text is None:
            body = '<p class="missing">This file is missing.</p>'
        else:
            body = f"<pre>{html.escape(text.strip())}</pre>"
        sections.append(
            f"<section><h2>{_SELF_TITLES[name]}</h2>"
            f'<div class="file">{name} · read-only — edit the file to change him</div>'
            f"{body}</section>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Majordomo — Soul &amp; Memory</title>
<style>{_SELF_STYLE}</style>
</head>
<body>
<header><div class="brand">{FINGERPRINT_SVG}<h1>MAJORDOMO</h1></div><a href="/">← the window</a></header>
<main>
<p class="note">Who he is, who he serves, and what he keeps — the plain files at the
top of the data directory, assembled into his system prompt on every turn.</p>
{"".join(sections)}
</main>
</body>
</html>
"""


def self_sections(store: SelfStore) -> list[dict[str, Any]]:
    """The self files as JSON, for the window's Soul & Memory read."""
    return [
        {
            "file": name,
            "title": _SELF_TITLES[name],
            "text": (text.strip() if (text := store.read(name)) is not None else None),
        }
        for name in SELF_FILES
    ]


class ChatRequest(BaseModel):
    """One chat message from the page (or any API client)."""

    message: str
    session_id: str | None = None
    approve: bool = False


class GoalCreate(BaseModel):
    """A new goal from the window's Goal read."""

    text: str
    next_move: str = ""


class GoalNextMove(BaseModel):
    """A replacement next move for one goal."""

    next_move: str


class GoalDone(BaseModel):
    """A done/reopen flag for one goal."""

    done: bool


def create_app(settings: Settings | None = None, provider: Provider | None = None) -> FastAPI:
    """Build the FastAPI app around one runtime."""
    settings = settings or Settings()
    runtime: Runtime = build_runtime(settings, provider=provider)
    goals = GoalStore(settings.data_dir / "goals.json")

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        async def tick() -> None:
            while True:
                await asyncio.sleep(30)
                try:
                    now = datetime.now(UTC)
                    fired = runtime.schedules.fire_due(now)
                    for reminder in fired:
                        runtime.sessions.append(
                            "inbox",
                            {
                                "role": "assistant",
                                "content": f"⏰ Reminder: {reminder.text}",
                            },
                        )
                    # Initiative runs with the tick: mail watch +
                    # escalation append their own lines to the inbox.
                    runtime.initiative.tick(now, fired)
                except Exception:  # the tick must never kill the app; it logs instead
                    log.exception("scheduler.tick_failed")

        task = asyncio.create_task(tick())
        yield
        task.cancel()
        runtime.close()

    app = FastAPI(title="Majordomo", version=__version__, lifespan=lifespan)
    app.state.runtime = runtime
    app.state.goals = goals

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return PAGE.replace("FINGERPRINT_INLINE", _fingerprint_js())

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "provider": runtime.provider.name}

    @app.post("/chat")
    def chat(request: ChatRequest) -> dict[str, Any]:
        result = runtime.agent.run(
            request.session_id,
            request.message,
            approver=approve_all if request.approve else approve_none,
        )
        return {
            "session_id": result.session_id,
            "reply": result.text,
            "events": [{"kind": e.kind, "text": e.text, "tool": e.tool} for e in result.events],
        }

    @app.get("/sessions")
    def sessions() -> list[dict[str, Any]]:
        return runtime.sessions.list_sessions()

    @app.get("/memory")
    def memory() -> list[dict[str, str]]:
        return [{"id": e.id, "kind": e.kind, "text": e.text} for e in runtime.memory.list()]

    @app.get("/self", response_class=HTMLResponse)
    def self_page() -> str:
        return render_self_page(runtime.self_store)

    @app.get("/self-data")
    def self_data() -> list[dict[str, Any]]:
        return self_sections(runtime.self_store)

    @app.get("/goals")
    def list_goals() -> list[dict[str, Any]]:
        return goals.list()

    @app.post("/goals", status_code=201)
    def add_goal(request: GoalCreate) -> dict[str, Any]:
        text = request.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="A goal needs text.")
        return goals.add(text, request.next_move.strip())

    @app.post("/goals/{goal_id}/next-move")
    def goal_next_move(goal_id: int, request: GoalNextMove) -> dict[str, Any]:
        goal = goals.set_next_move(goal_id, request.next_move.strip())
        if goal is None:
            raise HTTPException(status_code=404, detail="No such goal.")
        return goal

    @app.post("/goals/{goal_id}/done")
    def goal_done(goal_id: int, request: GoalDone) -> dict[str, Any]:
        goal = goals.set_done(goal_id, request.done)
        if goal is None:
            raise HTTPException(status_code=404, detail="No such goal.")
        return goal

    @app.delete("/goals/{goal_id}")
    def goal_delete(goal_id: int) -> dict[str, Any]:
        if not goals.delete(goal_id):
            raise HTTPException(status_code=404, detail="No such goal.")
        return {"deleted": goal_id}

    @app.get("/files")
    def list_files() -> list[dict[str, Any]]:
        root = runtime.workspace.root
        entries: list[dict[str, Any]] = []
        for path in sorted(root.rglob("*")):
            if path.is_file():
                stat = path.stat()
                entries.append(
                    {
                        "name": path.relative_to(root).as_posix(),
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                    }
                )
        return entries

    @app.get("/files/{name:path}")
    def download_file(name: str) -> FileResponse:
        try:
            path = runtime.workspace.resolve(name)
        except ValueError:
            raise HTTPException(status_code=404, detail="No such file.") from None
        if not path.is_file():
            raise HTTPException(status_code=404, detail="No such file.")
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(path, media_type=media_type, filename=path.name)

    @app.get("/brand/{name}")
    def brand_file(name: str) -> FileResponse:
        media_type = _BRAND_FILES.get(name)
        path = _STATIC / name
        if media_type is None or not path.is_file():
            raise HTTPException(status_code=404, detail="No such brand file.")
        return FileResponse(path, media_type=media_type, filename=name)

    return app


def _fingerprint_js() -> str:
    """The fingerprint SVG as a JS string literal for the window page."""
    return json.dumps(FINGERPRINT_SVG)
