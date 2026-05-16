# ChenEduSys - Project Context & Architecture

## 1. Project Overview

ChenEduSys is a **peer-to-peer (P2P) education platform** designed for
1-on-1 or small-group tutoring. Teachers and students connect directly
over their home networks, coordinated by a lightweight cloud signaling
server running on Google Cloud VM.

**Core principle:** The cloud VM is only a *coordination hub* — all
real-time data (audio, canvas strokes, PDFs) flows P2P between teacher
and student machines.

### Key Constraints (from init.md)

| Constraint | Detail |
|---|---|
| Language | Python, conda-installable |
| Platforms | Linux + Windows |
| Network | Home networks (no static IP, behind NAT) |
| Hub | Google Cloud VM (signaling + accounts only) |
| Data path | P2P between teacher and students |
| Security | Must be considered from day one |
| Camera | Placeholder for future (Phase 2) |
| AI assistant | Future phase |

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Google Cloud VM (Hub)                       │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────────┐ │
│  │  Auth Server  │  │ Signaling Svr │  │  Meeting Registry    │ │
│  │ (accounts,    │  │ (relay IP     │  │  (create/list/join   │ │
│  │  tokens)      │  │  info only)   │  │   meetings)          │ │
│  └──────────────┘  └───────────────┘  └──────────────────────┘ │
└──────────────────────┬──────────────────────────┬───────────────┘
                       │ signaling only            │ signaling only
                       ▼                          ▼
          ┌────────────────────────┐   ┌────────────────────────┐
          │   Teacher Machine      │   │   Student Machine      │
          │   (P2P Server role)    │◄──►│   (P2P Client role)    │
          │                        │   │                        │
          │  ┌──────────────────┐  │   │  ┌──────────────────┐  │
          │  │  ChenEduSys App  │  │   │  │  ChenEduSys App  │  │
          │  │  ┌────────────┐  │  │   │  │  ┌────────────┐  │  │
          │  │  │   UI Layer  │  │  │   │  │  │   UI Layer  │  │  │
          │  │  ├────────────┤  │  │   │  │  ├────────────┤  │  │
          │  │  │  Services   │  │  │   │  │  │  Services   │  │  │
          │  │  ├────────────┤  │  │   │  │  ├────────────┤  │  │
          │  │  │  Transport  │  │  │   │  │  │  Transport  │  │  │
          │  │  └────────────┘  │  │   │  │  └────────────┘  │  │
          │  └──────────────────┘  │   │  └──────────────────┘  │
          └────────────────────────┘   └────────────────────────┘
                     P2P: audio, canvas strokes, PDF sync
```

---

## 3. Technology Choices

### 3.1 GUI Framework: PySide6 (Qt for Python)

**Why PySide6 over alternatives:**

| Framework | Cross-platform | Touch/Stylus | Multimedia | License | Maturity |
|---|---|---|---|---|---|
| **PySide6** | Excellent | Excellent | Built-in | LGPL | High |
| PyQt6 | Excellent | Excellent | Built-in | GPL | High |
| Tkinter | Good | Poor | Poor | PSF | High |
| Kivy | Good | Good | Limited | MIT | Medium |

- Native touch/stylus events via `QTabletEvent` — critical for the paint component
- Built-in networking (`QTcpSocket`, `QUdpSocket`, `QWebSocket`)
- Built-in multimedia (`QAudioInput`, `QAudioOutput`, `QMediaDevices`)
- `QPdfDocument` for PDF rendering without external dependencies
- Signal/slot mechanism provides natural event-driven architecture
- LGPL license allows commercial use

### 3.2 Networking Stack

```
Layer          Technology              Purpose
─────────────────────────────────────────────────────────
Signaling      WebSocket (aiohttp)     Teacher ↔ Cloud VM ↔ Student
P2P Transport  asyncio TCP + UDP       Direct data channels
NAT Traversal  STUN (pystun3)          Discover public IP:port
Encryption     TLS (ssl module)        All connections encrypted
Serialization  MessagePack (msgpack)   Compact binary protocol
```

**Why not WebRTC?**
WebRTC (via aiortc) is powerful but adds significant complexity.
For a small-group education tool, custom asyncio networking over
TCP/UDP with STUN-based NAT traversal is simpler to develop, debug,
and maintain. We can migrate to WebRTC later if needed.

### 3.3 Audio

| Choice | Reason |
|---|---|
| `QAudioInput` / `QAudioOutput` | Already part of PySide6, no extra deps |
| Opus codec (via `opuslib`) | Low-latency voice, well-tested |
| `pyogg` or raw PCM fallback | If Opus proves hard to install |

### 3.4 Content & Paint

| Need | Package |
|---|---|
| PDF rendering | PySide6 `QPdfDocument` + `QPdfPageRenderer` |
| Canvas drawing | PySide6 `QPainter` + `QGraphicsScene` |
| Image processing (Phase 2) | OpenCV (`cv2`) + Pillow |

### 3.5 AI Assistant (Phase 2)

| Need | Package |
|---|---|
| Photo → scan | OpenCV perspective transform + adaptive threshold |
| Question OCR | Multi-modal LLM API (OpenAI / Anthropic SDK) |
| PDF generation | `reportlab` or `fpdf2` |

### 3.6 Infrastructure

| Need | Choice |
|---|---|
| Package management | `conda` (environment.yml) + `pip` (pyproject.toml) |
| Build system | `hatchling` via `pyproject.toml` |
| Logging | Python `logging` with structured handlers |
| Config | `pydantic-settings` (TOML/JSON config files) |
| Testing | `pytest` + `pytest-qt` + `pytest-asyncio` |
| CI | GitHub Actions (lint, test, build) |

---

## 4. Component Architecture (3-Layer Design)

The app uses a **3-layer architecture** with an **event bus** for
loose coupling between components. Each layer only depends on the
layer below it.

```
┌─────────────────────────────────────────────────────────────┐
│                        UI Layer (PySide6)                    │
│   Windows / Widgets / Canvas — only renders state,           │
│   forwards user actions to Services layer                    │
├─────────────────────────────────────────────────────────────┤
│                     Services Layer                            │
│   Business logic: MeetingManager, AuthService,               │
│   ContentSync, AudioService, PaintEngine                     │
│   Communicates via EventBus, owns application state          │
├─────────────────────────────────────────────────────────────┤
│                    Transport Layer                            │
│   Network I/O: SignalingClient, P2PServer, P2PClient,       │
│   Message serialization, TLS, NAT traversal                  │
└─────────────────────────────────────────────────────────────┘

               ┌──────────────┐
               │   EventBus   │  ← cross-cutting: all layers
               │ (pub/sub)    │     can publish/subscribe
               └──────────────┘
```

### 4.1 Why This Architecture

| Goal | How This Achieves It |
|---|---|
| Easy to maintain | Each layer has a single responsibility; changes are isolated |
| Easy to add features | New features = new Service + new UI widgets; layers below unchanged |
| Easy to understand | 3 layers + event bus; new developers grasp the pattern quickly |
| Easy to debug | Each layer testable independently; events are traceable |
| Reduce failure risk | Loose coupling means one component failing doesn't crash others |

### 4.2 EventBus Design

The event bus is the backbone for decoupled communication.

```python
# Event topics (examples)
"auth.login_success"        → user logged in
"auth.logout"               → user logged out
"meeting.created"           → teacher created a meeting
"meeting.joined"            → student joined
"meeting.participant_left"  → someone left
"network.p2p_connected"     → P2P link established
"network.p2p_disconnected"  → P2P link dropped
"content.pdf_loaded"        → PDF file loaded for sharing
"content.pdf_page_changed"  → teacher changed PDF page
"paint.stroke"              → a drawing stroke occurred
"paint.clear"               → canvas cleared
"audio.mute_toggle"         → mute/unmute
"system.error"              → any error
```

**Rules for the EventBus:**
1. Publishers never know who receives — zero coupling
2. Subscribers never block the publisher — handlers run asynchronously
3. Events carry typed payloads (dataclasses) — easy to debug
4. All events are logged at DEBUG level — full audit trail

---

## 5. Package Structure

```
ChenEduSys/
│
├── pyproject.toml                 # Build config, dependencies, metadata
├── environment.yml                # Conda environment definition
├── context.md                     # ← This file (project context)
├── init.md                        # Original project idea
│
├── src/
│   └── chenedusys/                # Main Python package
│       │
│       ├── __init__.py            # Package version, public API
│       ├── __main__.py            # `python -m chenedusys` entry point
│       ├── app.py                 # QApplication bootstrap
│       │
│       ├── core/                  # ── Layer 0: Foundation ──
│       │   ├── __init__.py
│       │   ├── event_bus.py       # Pub/sub event system
│       │   ├── events.py          # All event type definitions (dataclasses)
│       │   ├── config.py          # Settings/config management
│       │   ├── logger.py          # Logging setup
│       │   └── models.py          # Shared data models (User, Meeting, etc.)
│       │
│       ├── transport/             # ── Layer 1: Network I/O ──
│       │   ├── __init__.py
│       │   ├── protocol.py        # Message types + serialization (MessagePack)
│       │   ├── signaling.py       # WebSocket client to cloud hub
│       │   ├── p2p_server.py      # Teacher's P2P listener (asyncio TCP)
│       │   ├── p2p_client.py      # Student's P2P connector (asyncio TCP)
│       │   ├── nat.py             # STUN-based NAT traversal
│       │   └── security.py        # TLS setup, certificate management
│       │
│       ├── services/              # ── Layer 2: Business Logic ──
│       │   ├── __init__.py
│       │   ├── auth.py            # Login, registration, token management
│       │   ├── meeting.py         # Create/join/leave meeting lifecycle
│       │   ├── audio.py           # Voice capture, encode, stream
│       │   ├── content_sync.py    # PDF + paint synchronization
│       │   └── paint_engine.py    # Stroke model, canvas state management
│       │
│       ├── ui/                    # ── Layer 3: User Interface ──
│       │   ├── __init__.py
│       │   ├── theme.py           # Stylesheets, fonts, colors
│       │   ├── windows/
│       │   │   ├── __init__.py
│       │   │   ├── login.py       # Login / Register window
│       │   │   ├── dashboard.py   # Main dashboard (list meetings)
│       │   │   ├── meeting.py     # Active meeting window (the main view)
│       │   │   └── settings.py    # Settings / config window
│       │   └── widgets/
│       │       ├── __init__.py
│       │       ├── paint_canvas.py    # Touchpad drawing canvas widget
│       │       ├── pdf_viewer.py      # PDF page display widget
│       │       ├── content_view.py    # Combined: PDF + paint overlay
│       │       ├── audio_controls.py  # Mute/unmute, volume
│       │       ├── participant_bar.py # Participant list / status
│       │       └── toolbar.py         # Drawing tools (pen, eraser, clear)
│       │
│       └── ai/                    # ── Phase 2: AI Assistant ──
│           ├── __init__.py
│           ├── scanner.py         # Photo → scanned image transform
│           └── question_gen.py    # LLM question recognition → PDF
│
├── hub_server/                    # Cloud signaling server (separate deploy)
│   ├── __init__.py
│   ├── main.py                    # Server entry (aiohttp or FastAPI)
│   ├── auth.py                    # User account endpoints
│   ├── signaling.py               # Meeting signaling relay
│   ├── database.py                # Lightweight DB (SQLite or PostgreSQL)
│   └── requirements.txt           # Server-only dependencies
│
├── tests/                         # ── Test Suite ──
│   ├── conftest.py                # Shared fixtures (QApplication, event bus)
│   ├── unit/
│   │   ├── test_event_bus.py
│   │   ├── test_protocol.py
│   │   ├── test_paint_engine.py
│   │   └── test_models.py
│   ├── integration/
│   │   ├── test_signaling.py      # Test with mock signaling server
│   │   ├── test_p2p.py            # Test P2P connection flow
│   │   └── test_content_sync.py
│   └── e2e/
│       └── test_meeting_flow.py   # Full meeting lifecycle
│
└── docs/
    ├── architecture.md             # Detailed architecture docs
    ├── development.md              # Dev setup guide
    └── deployment.md               # Hub server deployment guide
```

---

## 6. Network Protocol Design

### 6.1 Signaling Protocol (WebSocket → Cloud Hub)

All messages are JSON over WebSocket for simplicity:

```
Client → Server:
  { "type": "register",    "username": "...", "password_hash": "..." }
  { "type": "login",       "username": "...", "password_hash": "..." }
  { "type": "create_meeting", "title": "...", "max_participants": 5 }
  { "type": "join_meeting",   "meeting_id": "...", "token": "..." }
  { "type": "leave_meeting" }
  { "type": "list_meetings" }
  { "type": "relay",       "target": "student_id", "payload": {...} }

Server → Client:
  { "type": "auth_ok",     "token": "...", "user": {...} }
  { "type": "auth_fail",   "reason": "..." }
  { "type": "meeting_created", "meeting_id": "...", "port": 9100 }
  { "type": "meeting_list", "meetings": [...] }
  { "type": "peer_info",   "peer_id": "...", "ip": "1.2.3.4", "port": 9100 }
  { "type": "relay",       "from": "teacher_id", "payload": {...} }
```

### 6.2 P2P Data Protocol (MessagePack over TCP)

Binary protocol for performance. Each message frame:

```
[4 bytes: length][1 byte: channel][N bytes: msgpack payload]

Channels:
  0x01 = CONTROL    (meeting commands, participant management)
  0x02 = AUDIO      (encoded audio frames)
  0x03 = CONTENT    (PDF pages, page changes)
  0x04 = PAINT      (stroke data)
```

**Channel separation** allows independent processing:
- Audio frames are time-sensitive → high-priority queue
- Paint strokes must be ordered → sequential queue
- Content updates are infrequent → low-priority queue

### 6.3 NAT Traversal Flow

```
1. Teacher starts meeting
2. Teacher's app contacts STUN server → discovers public IP:port
3. Teacher registers meeting with cloud hub, includes public IP:port
4. Student joins meeting via cloud hub
5. Student's app contacts STUN server → discovers own public IP:port
6. Cloud hub exchanges peer info (IPs and ports)
7. Both sides attempt UDP hole punching simultaneously
8. If UDP punching succeeds → direct P2P
9. If UDP punching fails → fall back to TCP with relayed connection info
```

---

## 7. Data Flow: Key Scenarios

### 7.1 Meeting Lifecycle

```
Teacher                          Cloud Hub                     Student
  │                                 │                            │
  ├── create_meeting ──────────────►│                            │
  │                                 │◄──────── list_meetings ────┤
  │                                 ├── meeting_list ────────────►│
  │                                 │◄──────── join_meeting ─────┤
  │◄──── peer_info (student) ──────┤──── peer_info (teacher) ──►│
  │                                 │                            │
  │◄═════════ P2P TCP connection ══════════════════════════════►│
  │                                 │                            │
  ├── [audio, content, paint flows over P2P] ──────────────────►│
```

### 7.2 Paint Synchronization

The paint canvas is a **transparent full-screen overlay**. The teacher's
strokes float above whatever is on screen (PDF, question image, desktop).
For sync, stroke coordinates are stored as **normalized values** (0.0–1.0
relative to screen size) so they render correctly on different screen
resolutions between teacher and student.

```
Teacher draws (Ctrl + touchpad move):
  1. PaintCanvas captures mouse/touchpad position
  2. PaintEngine converts to Stroke (points in canvas-space)
  3. PaintEngine publishes "paint.stroke" event on EventBus
  4. ContentSync normalizes coordinates to 0.0–1.0 range
  5. ContentSync sends stroke on PAINT channel to students
  6. Student's ContentSync denormalizes to their screen size
  7. Student's PaintEngine applies stroke
  8. Student's transparent overlay re-renders with new stroke
```

### 7.3 PDF Content Sync

```
Teacher loads PDF:
  1. File selected → ContentSync reads PDF
  2. ContentSync hashes PDF, checks if student has it (via CONTROL channel)
  3. If student doesn't have it → send PDF bytes on CONTENT channel
  4. Student receives → stores locally → renders page 1
  5. Teacher turns page → sends "page_change: 3" on CONTENT channel
  6. Student renders page 3

Paint overlay on PDF:
  - PDF is the background layer
  - Paint strokes are the foreground layer
  - Both render in the same ContentView widget
  - Teacher's paint syncs to student's overlay
```

---

## 8. Security Design

### 8.1 Authentication

- Password hashing: `argon2` (via `argon2-cffi`)
- Session tokens: JWT (via `PyJWT`) with expiry
- Local storage: OS keyring (via `keyring` package) — never plaintext files

### 8.2 Transport Security

- Signaling: `wss://` (WebSocket over TLS) to cloud hub
- P2P: TLS with self-signed certificates exchanged via signaling channel
  - During signaling, peers exchange certificate fingerprints
  - On P2P connect, verify fingerprint matches → prevents MITM

### 8.3 Application Security

- All user inputs sanitized before processing
- File uploads (PDFs) validated: magic bytes, size limits
- Rate limiting on signaling server endpoints
- No execution of arbitrary code or shell commands from user input

---

## 9. Phased Development Plan

### Phase 0: Project Foundation — COMPLETE

- [x] Initialize project structure (pyproject.toml, environment.yml)
- [x] Implement `core/event_bus.py` + `core/events.py` (15 event types)
- [x] Implement `core/config.py` (pydantic-settings, TOML + env vars)
- [x] Implement `core/logger.py` (console + rotating file handler)
- [x] Implement `core/models.py` (User, Meeting, Point, Stroke)
- [x] Create `app.py` + `__main__.py` — PySide6 QApplication bootstrap
- [x] Create `ui/windows/login.py` (placeholder)
- [x] 41 unit + edge-case tests, all passing
- [x] Installed via `pip install -e ".[dev]"`

### Phase 1: Paint Component — COMPLETE

- [x] Implement `services/paint_engine.py` (stroke model, undo, erase, viewport, pages)
- [x] Implement `ui/widgets/paint_canvas.py` (transparent overlay)
- [x] Implement `ui/widgets/toolbar.py` (clear, stop buttons)
- [x] **Input model:** Ctrl+move = draw, Shift+move = erase (no click/drag needed)
- [x] **Transparent screen overlay** — canvas floats above all desktop content
- [x] **Auto-detect screen size** via `QApplication.primaryScreen().geometry()`
- [x] Frameless always-on-top window (FramelessWindowHint | WindowStaysOnTopHint | Tool)
- [x] ESC = quit app (via window-level keyPressEvent override; QShortcut doesn't work with Tool windows)
- [x] 2-finger touchpad = pan viewport (strokes stay in canvas-space)
- [x] Clean shutdown via `app.quit()`
- [x] 88 tests total (Phase 0 + Phase 1), all passing
- [x] `demo_paint.py` — standalone screen overlay demo

#### Key Design Decisions (Phase 1)

| Decision | Why |
|---|---|
| Ctrl+move to draw (not click+drag) | Touchpad-first UX — no button press needed, just modifier + move |
| Transparent full-screen overlay | Paint floats above any screen content (desktop, PDF, browser) |
| WA_TranslucentBackground + FramelessWindowHint | Qt's way to make a truly transparent overlay window |
| QShortcut doesn't work with Tool window type | Had to override keyPressEvent on the window directly |
| PaintEngine is Qt-free (pure Python) | Testable without GUI; canvas widget is just a renderer + input handler |
| Strokes stored in canvas-space, viewport is a window into it | Panning moves the view without moving strokes — critical for paint sync |

### Phase 2: Hub Server & Authentication — COMPLETE

- [x] `hub_server/main.py` — aiohttp app with REST + WebSocket endpoints
- [x] `hub_server/database.py` — SQLite with users, meetings, participants tables
- [x] `hub_server/auth.py` — argon2 password hashing, JWT token create/validate
- [x] `hub_server/signaling.py` — meeting CRUD, join/leave, WebSocket relay, real-time notifications
- [x] `src/chenedusys/transport/signaling.py` — async WebSocket client with reconnect + heartbeat
- [x] `src/chenedusys/services/auth.py` — client auth service, OS keyring token storage
- [x] `src/chenedusys/ui/windows/login.py` — real login/register form
- [x] `src/chenedusys/ui/windows/dashboard.py` — meeting list, create, join
- [x] JSON error responses (not text/plain) — discovered by tests
- [x] 130 tests total (Phase 0 + 1 + 2), all passing

#### Key Design Decisions (Phase 2)

| Decision | Why |
|---|---|
| aiohttp for hub server | Async, lightweight, good test support via pytest-aiohttp |
| SQLite for hub storage | Simple, no external DB needed, adequate for small-group use |
| JWT tokens for auth | Stateless, no server-side session needed, standard |
| OS keyring for token storage | Never stored in plaintext files |
| Error responses as JSON | aiohttp defaults to text/plain for HTTP errors; tests caught this |
| Teacher auto-added as participant | On create_meeting, teacher is participant #1; max_participants includes teacher |


### Phase 2: Hub Server & Auth (Week 5-6)
**Goal:** Cloud signaling server running, users can register and login.

- [ ] Implement `hub_server/` with aiohttp
- [ ] User registration + login (argon2 passwords, JWT tokens)
- [ ] Meeting create / list / join endpoints
- [ ] Signaling relay (exchange peer connection info)
- [ ] Implement `transport/signaling.py` (client-side WebSocket)
- [ ] Implement `services/auth.py` (client-side auth service)
- [ ] Build `ui/windows/login.py` (real login UI)
- [ ] Build `ui/windows/dashboard.py` (meeting list)
- [ ] Write integration tests with mock server
- [ ] Deploy hub server to Google Cloud VM

### Phase 3: P2P Networking (Week 7-8)
**Goal:** Teacher and student establish direct P2P connection.

- [ ] Implement `transport/protocol.py` (MessagePack framing, channels)
- [ ] Implement `transport/p2p_server.py` (teacher side)
- [ ] Implement `transport/p2p_client.py` (student side)
- [ ] Implement `transport/nat.py` (STUN discovery)
- [ ] Implement `transport/security.py` (TLS, certificate exchange)
- [ ] Implement `services/meeting.py` (meeting lifecycle with P2P)
- [ ] NAT traversal flow: STUN → exchange IPs → connect
- [ ] Build `ui/windows/meeting.py` (meeting room with participant list)
- [ ] Write integration tests (two local P2P endpoints)
- [ ] Test across different NAT types

### Phase 4: Audio Communication (Week 9-10)
**Goal:** Real-time voice chat over P2P.

- [ ] Implement `services/audio.py` (capture, encode, decode, playback)
- [ ] Audio capture via PySide6 QAudioInput
- [ ] Audio playback via PySide6 QAudioOutput
- [ ] Opus encoding/decoding for bandwidth efficiency
- [ ] Stream audio on AUDIO channel (channel 0x02)
- [ ] Build `ui/widgets/audio_controls.py` (mute/unmute, volume)
- [ ] Handle multiple students (mix audio streams for teacher)
- [ ] Test latency and quality

### Phase 5: Content Sharing (Week 11-13)
**Goal:** PDF + paint synchronization between teacher and students.

- [ ] Implement `ui/widgets/pdf_viewer.py` (QPdfDocument rendering)
- [ ] Implement `ui/widgets/content_view.py` (PDF background + paint overlay)
- [ ] Implement `services/content_sync.py` (PDF transfer, page sync, paint sync)
- [ ] PDF file transfer on CONTENT channel
- [ ] Page change sync (teacher controls which page is displayed)
- [ ] Paint stroke sync on PAINT channel
- [ ] Student sees: PDF page + teacher's paint overlay
- [ ] Toolbar: pen, eraser, clear, page navigation
- [ ] Write integration tests for content sync
- [ ] End-to-end test: full meeting with content sharing

### Phase 6: AI Assistant (Future Phase)
**Goal:** Photo scanner + question segmentation via LLM.

- [ ] Implement `ai/scanner.py` (OpenCV perspective correction)
- [ ] Implement `ai/question_gen.py` (multi-modal LLM → question PDF)
- [ ] Settings UI for API key configuration
- [ ] Generate exam PDFs (1 question per page + blank space)
- [ ] Integration with content sharing (use generated PDFs in meetings)

---

## 10. Key Design Decisions & Rationale

### 10.1 Why asyncio + PySide6 (two event loops)?

PySide6 runs its own event loop (`QApplication.exec()`).
The networking layer uses `asyncio`. We bridge them with
`qasync` or a manual integration (calling `asyncio` tasks
from Qt timer callbacks). This separation keeps networking
code testable without Qt and keeps UI code free of networking details.

### 10.2 Why MessagePack over JSON for P2P?

Paint strokes produce many small messages. JSON encoding overhead
becomes significant. MessagePack is binary, compact, and fast.
The signaling server uses JSON (WebSocket) for simplicity since
those messages are infrequent and small.

### 10.3 Why Channel-Based Multiplexing?

Audio, paint, and content have different priority and ordering
requirements. Separate channels allow:
- Audio frames to skip ahead if behind (drop old frames)
- Paint strokes to be strictly ordered
- Content to be low priority

### 10.4 Why Separate Hub Server Deployment?

The hub server (`hub_server/`) is deployed independently on the
Google Cloud VM. It has minimal dependencies (aiohttp + SQLite
is enough to start). This keeps the client package lean and
the server simple.

---

## 11. Risk Mitigation

| Risk | Mitigation |
|---|---|
| NAT traversal fails (symmetric NAT) | STUN + fallback guidance for port forwarding; document router config |
| Audio latency too high | Opus codec (low bitrate, ~20ms frames); measure and tune buffer sizes |
| PySide6 touch support varies by OS | Test on Linux (X11 + Wayland) and Windows early; abstract input handling |
| Package installation issues (conda) | Pin dependency versions; test clean install in CI on both OSes |
| Canvas performance with many strokes | Implement incremental rendering (only redraw changed regions) |
| P2P connection reliability | Heartbeat mechanism; auto-reconnect with backoff; clear error messages |
| Security vulnerabilities | TLS everywhere; input validation; security review before release |
