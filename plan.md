# ChenEduSys - Development Plan

## Guiding Principles

1. **Each phase produces a runnable, testable deliverable** — never a half-built system.
2. **Dependencies flow downward**: UI → Services → Transport → Core. Build bottom-up.
3. **Every component has unit tests** before moving to the next phase.
4. **Integration tests between phases** validate that layers work together.
5. **One developer can build each phase** — no parallel-work bottlenecks.
6. **Test before you build the next thing** — each phase's test plan must fully pass before starting the next phase.

## Test Strategy Overview

Every phase has **four levels of testing**:

| Level | Purpose | When | Who |
|---|---|---|---|
| **Unit tests** | Verify individual functions/classes in isolation | During development (every commit) | Automated (pytest) |
| **Integration tests** | Verify components work together correctly | After component is complete | Automated (pytest) |
| **Edge-case tests** | Find bugs in boundary conditions and error paths | During and after development | Automated (pytest) |
| **Smoke tests (manual)** | Verify the full user-facing flow works | Phase sign-off | Developer manually |

### Test file naming convention
```
tests/
├── unit/              # Fast, no I/O, no network, no GUI
│   ├── test_<module>.py
├── integration/       # Multi-component, may use mocks/fakes
│   ├── test_<flow>.py
├── edge_cases/        # Boundary + error condition tests
│   ├── test_<module>_edge.py
└── e2e/               # Full workflow (Phase 5+)
    └── test_<scenario>.py
```

---

## Phase 0: Project Foundation

**Deliverable:** `python -m chenedusys` launches a window. Event bus works. Config loads.

### Tasks

| # | Task | Files | Test |
|---|---|---|---|
| 0.1 | Create `pyproject.toml`, `environment.yml`, package skeleton | `pyproject.toml`, `environment.yml`, `src/chenedusys/__init__.py` | `conda env create` + `pip install -e .` |
| 0.2 | Implement EventBus (publish/subscribe) | `core/event_bus.py`, `core/events.py` | `test_event_bus.py` |
| 0.3 | Implement config system (pydantic-settings) | `core/config.py` | `test_config.py` |
| 0.4 | Implement logging setup | `core/logger.py` | logs to stdout + file |
| 0.5 | Define core data models | `core/models.py` (User, Meeting, Stroke dataclasses) | `test_models.py` |
| 0.6 | Create QApplication bootstrap | `app.py`, `__main__.py` | window appears |
| 0.7 | Create placeholder login window | `ui/windows/login.py` | window with label "Login" |
| 0.8 | Verify cross-platform install | — | works on Linux + Windows |

### Test Plan: Phase 0

#### Unit Tests (`tests/unit/`)

**`test_event_bus.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Subscribe and publish | Subscribe to topic, publish event | Handler receives the event payload |
| Multiple subscribers | 3 handlers on same topic | All 3 receive the event |
| Unsubscribe | Subscribe, then unsubscribe, then publish | Handler does NOT receive event |
| Publish to empty topic | Publish with no subscribers | No error, returns silently |
| Typed event payload | Publish `LoginSuccess(user="alice")` | Handler receives correct typed dataclass |
| Async handler | Subscribe with async function | Handler executes, no crash |
| Handler exception | Handler raises RuntimeError | Other handlers still run; exception is logged, not swallowed |
| Thread safety | Publish from 2 threads simultaneously | All events delivered, no corruption |

**`test_config.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Load from TOML file | Valid TOML with all fields | Config object has correct values |
| Load from env vars | Set env vars with `CHENEDUSYS_` prefix | Env vars override TOML values |
| Missing optional fields | TOML with only required fields | Defaults applied for missing fields |
| Invalid TOML syntax | Malformed TOML | Raises `ConfigError` with clear message |
| Unknown field in TOML | TOML with extra unknown field | Raises validation error (strict mode) |
| Config file not found | No config file on disk | Creates default config, logs warning |
| Save config back | Modify config, call save() | File on disk updated with new values |

**`test_models.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| User creation | `User(id=..., username="alice", role="teacher")` | Object created with correct fields |
| Meeting creation | `Meeting(id=..., teacher_id=..., title="Math")` | Object created, `status="waiting"` |
| Stroke serialization | Create Stroke with points, serialize to dict | Round-trip: dict → Stroke → dict matches |
| Model immutability | Try to modify frozen dataclass | Raises `FrozenInstanceError` |

**`test_logger.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Log to file | Log a message | Message appears in log file |
| Log rotation | Write > 5MB of logs | Log file rotates, old file archived |
| Log levels | Set level to WARNING | DEBUG/INFO messages suppressed |

#### Edge-Case Tests (`tests/edge_cases/`)

| Test Case | Input | Expected Result |
|---|---|---|
| EventBus: publish 10,000 events rapidly | Stress test | All delivered, no memory leak (check with tracemalloc) |
| EventBus: handler that subscribes during publish | Handler subscribes to same topic while being called | No infinite loop, new handler gets NEXT event only |
| Config: concurrent read/write | Two threads reading/writing config | No crash, last-write-wins, no corruption |
| Models: Stroke with 0 points | Empty stroke | Serialization produces empty list, no crash |
| Models: Stroke with NaN coordinates | `Point(x=float('nan'), y=1.0)` | Validation error raised |

#### Smoke Tests (Manual)

| Step | Action | Expected Result |
|---|---|---|
| 1 | `conda env create -f environment.yml` | Environment created without errors |
| 2 | `conda activate chenedusys && python -m chenedusys` | A window appears on screen |
| 3 | Close the window | Application exits cleanly, no error in terminal |
| 4 | `pytest tests/` | All tests pass |
| 5 | Repeat steps 1-4 on Windows | Same results |

### Acceptance Criteria
- [ ] `conda activate chenedusys && python -m chenedusys` shows a window
- [ ] `pytest tests/unit/` passes all unit tests
- [ ] EventBus pub/sub works with typed events
- [ ] Config loads from TOML file
- [ ] All edge-case tests pass
- [ ] All smoke tests pass on Linux AND Windows

### Do NOT build in this phase
- No networking code
- No real UI functionality (just placeholder windows)
- No authentication logic

---

## Phase 1: Paint Component

**Deliverable:** A standalone touchpad drawing widget that can be tested independently.

### Depends on
- Phase 0 (event bus, models)

### Tasks

| # | Task | Files | Test |
|---|---|---|---|
| 1.1 | Implement PaintEngine (stroke model, undo stack, canvas state) | `services/paint_engine.py` | `test_paint_engine.py` |
| 1.2 | Implement PaintCanvas widget (QTabletEvent for pen input) | `ui/widgets/paint_canvas.py` | `test_paint_canvas.py` (pytest-qt) |
| 1.3 | 1-finger = pen drawing mode | `ui/widgets/paint_canvas.py` | draw a line → stroke appears |
| 1.4 | 2-finger = canvas panning (viewport moves, strokes stay fixed) | `ui/widgets/paint_canvas.py` | pan → old strokes don't move |
| 1.5 | Eraser mode (mouse-based area erase) | `ui/widgets/paint_canvas.py`, `ui/widgets/toolbar.py` | click eraser → erase area |
| 1.6 | Clear button (reset canvas) | `ui/widgets/toolbar.py` | click clear → canvas empty |
| 1.7 | ESC exits eraser mode | `ui/widgets/paint_canvas.py` | ESC → back to pen mode |
| 1.8 | Stop button (disable paint component) | `ui/widgets/toolbar.py` | click stop → canvas frozen |
| 1.9 | PaintCanvas emits EventBus events for all actions | integration | stroke → event fired |

### Test Plan: Phase 1

#### Unit Tests (`tests/unit/`)

**`test_paint_engine.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Add a stroke | 3 points with pen color black | Stroke stored, stroke_count == 1 |
| Add multiple strokes | 5 strokes sequentially | stroke_count == 5 |
| Erase stroke by point | Click on a point that intersects a stroke | That stroke removed, stroke_count decremented |
| Erase in eraser mode with radius | Erase with radius 10px near a stroke | Strokes within 10px are removed |
| Clear all strokes | Call clear() | stroke_count == 0, canvas is empty |
| Undo last stroke | Draw 2 strokes, call undo() | stroke_count == 1, first stroke remains |
| Stroke serialization | Create stroke, serialize to dict, deserialize | Round-trip produces identical stroke |
| Get strokes in viewport | Draw strokes, query viewport (0,0,100,100) | Only strokes intersecting viewport returned |
| Stroke properties preserved | Red pen, width 3px, 5 points | All properties match after storage |
| Empty canvas clear | clear() on already empty canvas | No error, stroke_count still 0 |

**`test_paint_canvas.py`** (pytest-qt with qtbot)

#### Integration Tests (`tests/integration/`)

**`test_paint_eventbus.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Stroke fires event | Add stroke to PaintEngine | `paint.stroke` event published on EventBus |
| Clear fires event | Call clear() on PaintEngine | `paint.clear` event published |
| Erase fires event | Erase a stroke | `paint.erase` event published with stroke ID |
| Event payload correct | Draw stroke, check event payload | Payload contains stroke data matching what was drawn |
| Mode change fires event | Switch to eraser mode | `paint.mode_change` event with mode="eraser" |
| Remote stroke applied | Publish `paint.remote_stroke` event | Stroke appears in PaintEngine |

#### Edge-Case Tests (`tests/edge_cases/`)

| Test Case | Input | Expected Result |
|---|---|---|
| Very fast drawing | 1000 points in < 1 second | All strokes recorded, no frame drops, no crash |
| Single point stroke | Tap without moving (1 point) | Stroke with 1 point stored and rendered as a dot |
| Stroke at canvas boundary | Draw at (0,0) and (max_x, max_y) | Strokes render correctly at edges |
| Panning to negative coordinates | Pan viewport to (-500, -500) | Strokes still render correctly, no crash |
| Panning far away then back | Pan 10000px away, pan back | Strokes still intact, same position |
| Erase while panning | Start erasing during a pan gesture | Eraser does NOT activate during 2-finger pan |
| Rapid mode switching | Switch pen→eraser→pen 50 times rapidly | Final mode is correct, no leaked state |
| Stroke with identical points | All 10 points at same (100, 100) | Renders as a dot, no crash |
| Canvas resize | Resize window from small to large | Strokes scale/position correctly |
| Large number of strokes | 500 strokes on canvas | Rendering remains smooth (< 16ms per frame) |

#### Smoke Tests (Manual)

| Step | Action | Expected Result |
|---|---|---|
| 1 | Run app, open paint canvas | Canvas appears with dashed border (~1/2 height x 1/3 width) |
| 2 | Draw with 1 finger on touchpad | Pen stroke appears on screen |
| 3 | Draw multiple lines | Each line is separate, visible |
| 4 | Use 2 fingers to pan | Canvas viewport moves, drawn lines stay at original positions |
| 5 | Draw after panning | New stroke appears in new viewport position |
| 6 | Click eraser button, move mouse over a stroke | Stroke disappears where mouse passes |
| 7 | Press ESC | Eraser mode exits, pen mode restored |
| 8 | Click clear button | All strokes disappear |
| 9 | Click stop button | Canvas becomes non-interactive (no drawing, no panning) |
| 10 | Draw for 5 minutes continuously | No slowdown, no memory error |

### Acceptance Criteria
- [ ] Touchpad pen draws on canvas (1 finger)
- [ ] Two-finger pans the viewport without moving existing strokes
- [ ] Eraser removes strokes at mouse position
- [ ] Clear wipes the canvas
- [ ] ESC exits eraser mode
- [ ] All paint actions fire events on the EventBus
- [ ] All unit, integration, and edge-case tests pass
- [ ] Manual smoke tests pass on touchscreen/touchpad hardware

### Do NOT build in this phase
- No network sync of paint strokes
- No PDF rendering behind the canvas
- No multi-user anything

---

## Phase 2: Hub Server & Authentication

**Deliverable:** Hub server running on Google Cloud. Users can register, login, and see meetings.

### Depends on
- Phase 0 (event bus, models, config)

### Tasks

| # | Task | Files | Test |
|---|---|---|---|
| 2.1 | Hub server: aiohttp app skeleton | `hub_server/main.py` | server starts on localhost |
| 2.2 | Hub server: user registration endpoint (argon2 hashing) | `hub_server/auth.py` | `POST /register` → 201 |
| 2.3 | Hub server: login endpoint (JWT tokens) | `hub_server/auth.py` | `POST /login` → token |
| 2.4 | Hub server: meeting create/list/join endpoints | `hub_server/signaling.py` | CRUD works |
| 2.5 | Hub server: SQLite database for users + meetings | `hub_server/database.py` | data persists |
| 2.6 | Client: SignalingClient (WebSocket to hub) | `transport/signaling.py` | `test_signaling.py` |
| 2.7 | Client: AuthService (login, register, token storage) | `services/auth.py` | `test_auth.py` |
| 2.8 | Client: Login window UI (real login form) | `ui/windows/login.py` | login → dashboard |
| 2.9 | Client: Dashboard window (list meetings, create, join buttons) | `ui/windows/dashboard.py` | shows meeting list |
| 2.10 | Client: Settings window (hub URL config) | `ui/windows/settings.py` | change hub URL |
| 2.11 | Deploy hub server to Google Cloud VM | scripts / docs | accessible from internet |

### Test Plan: Phase 2

#### Unit Tests — Server Side (`tests/unit/`)

**`test_hub_auth.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Register new user | POST /register {username, password} | 201, user stored in DB |
| Register duplicate user | Same username twice | 409 Conflict |
| Register with short password | Password < 8 chars | 400 with "password too short" |
| Register with empty username | username="" | 400 validation error |
| Login correct credentials | POST /login {username, password} | 200, JWT token returned |
| Login wrong password | Correct username, wrong password | 401 Unauthorized |
| Login non-existent user | Username that doesn't exist | 401 Unauthorized |
| JWT token valid | Decode token with secret | Contains correct user_id, not expired |
| JWT token expiry | Token after expiry time | Token validation returns False |
| SQL injection in username | username=`' OR 1=1 --` | Treated as literal string, no data leak |

**`test_hub_signaling.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Create meeting | Authenticated teacher POST /meetings | 201, meeting_id returned |
| List meetings | GET /meetings | 200, list of active meetings |
| Join meeting | Student POST /meetings/{id}/join | 200, added to participant list |
| Join non-existent meeting | Random meeting ID | 404 Not Found |
| Join full meeting | Meeting at max capacity | 403 "meeting full" |
| Create meeting unauthenticated | No auth token | 401 Unauthorized |
| Delete meeting | Teacher DELETE /meetings/{id} | 200, meeting removed from list |
| Meeting auto-cleanup | Meeting idle for 24 hours | Meeting removed (or cron job) |

**`test_hub_database.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| User persistence | Register user, restart server | User still exists after restart |
| Meeting persistence | Create meeting, restart server | Meeting still exists |
| Password not stored plaintext | Query DB directly | Password column contains argon2 hash, not plaintext |

#### Unit Tests — Client Side (`tests/unit/`)

**`test_signaling_client.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Connect to hub | Valid hub URL | WebSocket connection established |
| Connection refused | Invalid hub URL | `ConnectionError` with clear message |
| Login via signaling | Send login message | Receives auth_ok with token |
| Handle auth failure | Wrong credentials | Receives auth_fail event on EventBus |
| Reconnection | Server drops connection | Client auto-reconnects with exponential backoff |
| Heartbeat | Connection idle for 30s | Ping sent, pong received, connection stays alive |

**`test_auth_service.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Successful login | Valid credentials | Token stored in keyring, `auth.login_success` event fired |
| Failed login | Wrong password | No token stored, `auth.login_fail` event fired |
| Token retrieval | After login | get_token() returns stored JWT |
| Logout | Call logout() | Token removed from keyring, `auth.logout` event fired |
| Token expired check | Token with past expiry | `is_token_valid()` returns False |
| Offline login | No network available | Error event, clear message to user |

#### Integration Tests (`tests/integration/`)

**`test_auth_flow.py`** (with real aiohttp test server)
| Test Case | Input | Expected Result |
|---|---|---|
| Full register → login → list meetings | New user registration, then login | Gets token, can list meetings |
| Two users, one meeting | Teacher creates, student joins | Both see updated participant list |
| Token refresh | Near-expiry token | Client refreshes token automatically |
| Concurrent registrations | 10 users register simultaneously | All succeed, no duplicates, no DB corruption |

#### Edge-Case Tests (`tests/edge_cases/`)

| Test Case | Input | Expected Result |
|---|---|---|
| Very long username | 1000-character username | Rejected (max length enforced) |
| Unicode username | `用户名` or `🔥teacher` | Accepted (normalized to NFC form) |
| Password with null bytes | Password containing `\x00` | Rejected or handled safely |
| JWT token tampering | Modify 1 byte of token | Server rejects with 401 |
| Expired meeting cleanup | Create 100 meetings, let them expire | All cleaned up, no resource leak |
| Server restart during operation | Kill server mid-request | Client shows error, allows retry |
| WebSocket reconnect storm | Server goes down/up rapidly 10 times | Client reconnects eventually, doesn't spam |
| Hub server unreachable for 5 min | Block network to hub | Client shows "offline" status, retries in background |

#### Smoke Tests (Manual)

| Step | Action | Expected Result |
|---|---|---|
| 1 | Start hub server locally | Server starts, prints "Listening on port 8443" |
| 2 | Open app, enter hub URL, click Register | Registration succeeds, auto-login |
| 3 | Close app, reopen | Auto-login with stored token |
| 4 | Login as teacher, click "Create Meeting" | Meeting appears in list |
| 5 | Login as student on another machine | Sees the meeting in list |
| 6 | Student clicks "Join" | Both teacher and student see updated participant count |
| 7 | Check OS keyring / credential manager | Token stored securely, no plaintext file |
| 8 | Deploy hub to Google Cloud, repeat steps 2-7 | Works over the internet |
| 9 | Enter wrong password 5 times | Account temporarily locked (rate limiting) |

### Acceptance Criteria
- [ ] Hub server runs on Google Cloud, accessible via public IP
- [ ] User can register with username + password
- [ ] User can login and receive JWT token
- [ ] Teacher can create a meeting (appears in list)
- [ ] Student can see available meetings
- [ ] Client stores token in OS keyring (not plaintext)
- [ ] All unit, integration, and edge-case tests pass
- [ ] Smoke tests pass on both local and Google Cloud

### Do NOT build in this phase
- No P2P connections yet
- No audio
- No content sharing
- Meeting "join" just registers interest, doesn't connect peers yet

---

## Phase 3: P2P Networking

**Deliverable:** Teacher and student establish a direct P2P connection after meeting join.

### Depends on
- Phase 2 (signaling, auth, meeting management)

### Tasks

| # | Task | Files | Test |
|---|---|---|---|
| 3.1 | Define P2P protocol: message framing + channels | `transport/protocol.py` | `test_protocol.py` |
| 3.2 | Implement P2P server (teacher listens for student connections) | `transport/p2p_server.py` | accept one connection |
| 3.3 | Implement P2P client (student connects to teacher) | `transport/p2p_client.py` | connect to local server |
| 3.4 | Implement STUN-based NAT traversal | `transport/nat.py` | discover public IP |
| 3.5 | Implement TLS for P2P connections | `transport/security.py` | encrypted channel |
| 3.6 | Certificate fingerprint exchange via signaling | `transport/signaling.py` | MITM protection |
| 3.7 | MeetingService orchestrates full P2P flow | `services/meeting.py` | `test_meeting.py` |
| 3.8 | Meeting window UI (shows connection status, participants) | `ui/windows/meeting.py` | status: connected |
| 3.9 | Participant bar widget | `ui/widgets/participant_bar.py` | shows who's connected |
| 3.10 | Test NAT traversal across different networks | manual | teacher + student connect |

### Test Plan: Phase 3

#### Unit Tests (`tests/unit/`)

**`test_protocol.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Frame a message | Channel 0x01, payload dict | Correct [length][channel][msgpack] bytes |
| Parse a frame | Valid binary frame | Correct channel + payload dict |
| Frame round-trip | Encode → decode | Payload matches original |
| Oversized message | 10MB payload | Rejected with clear error (max size enforced) |
| Malformed frame | Random bytes | Parse error, no crash |
| Multiple frames in one buffer | 3 frames concatenated | All 3 parsed correctly, no leftover bytes |
| Zero-length payload | Empty payload | Frame with length=0 handled gracefully |
| Channel validation | Channel 0xFF (invalid) | Rejected with "unknown channel" error |

**`test_p2p_server.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Start listening | Call start(port=0) | Server listens on random available port |
| Accept one connection | Client connects | Connection accepted, registered in peer list |
| Reject second connection if max reached | Connect beyond max_participants | Connection rejected with "meeting full" |
| Send message to peer | Send on CONTROL channel | Client receives the message |
| Handle client disconnect | Client drops connection | Server removes peer, fires disconnect event |
| Stop server | Call stop() | All connections closed, port released |

**`test_p2p_client.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Connect to server | Valid IP:port | Connection established, `network.p2p_connected` event |
| Connection refused | Invalid port | `network.p2p_connect_failed` event with error details |
| Send message | Send on CONTROL channel | Server receives the message |
| Receive message | Server sends to client | Client receives, fires event on EventBus |
| Disconnect | Call disconnect() | Clean close, `network.p2p_disconnected` event |

**`test_nat.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| STUN discovery | Call discover_public_ip() | Returns (public_ip, public_port) tuple |
| STUN server unreachable | Bad STUN server address | Returns None with logged warning (not crash) |
| Multiple STUN servers | Primary fails, fallback succeeds | Returns result from fallback server |

**`test_security.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Generate self-signed cert | Call generate_cert() | Returns cert + key pair |
| TLS handshake succeeds | Client connects with server cert | Encrypted channel established |
| Fingerprint mismatch | Client expects cert A, server presents cert B | Connection rejected (MITM detected) |
| Certificate expiry | Expired cert | Handshake fails with clear error |

#### Integration Tests (`tests/integration/`)

**`test_p2p_flow.py`** (two local asyncio endpoints)
| Test Case | Input | Expected Result |
|---|---|---|
| Full connect flow | Server start → client connect → exchange messages | Bidirectional messaging works |
| Multi-peer (1 teacher + 3 students) | 3 clients connect to 1 server | All 3 connected, messages route correctly |
| Reconnect after disconnect | Disconnect client, reconnect | New connection works, peer list updated |
| Concurrent messaging | All peers send 100 messages simultaneously | All messages arrive, no corruption, correct order per channel |
| Large message transfer | Send 1MB message on CONTENT channel | Arrives intact at destination |

**`test_meeting_p2p.py`** (with mock signaling server)
| Test Case | Input | Expected Result |
|---|---|---|
| Full meeting lifecycle | Teacher creates meeting via signaling → student joins → P2P connects | P2P established, both see "Connected" |
| NAT traversal simulation | Mock STUN returns public IPs | Peer info exchanged via signaling, connection attempted |
| Signaling relay fallback | Direct P2P fails | Signaling server relays connection info for retry |

#### Edge-Case Tests (`tests/edge_cases/`)

| Test Case | Input | Expected Result |
|---|---|---|
| Network latency spike | Add 2-second delay to messages | Messages delayed but arrive correctly, no timeout crash |
| Partial message (TCP fragmentation) | Send 10KB in 100-byte chunks | Reassembled correctly at receiver |
| Sudden network drop | Kill connection mid-transfer | Disconnection event fired, auto-reconnect attempted |
| Message ordering across channels | Send AUDIO then PAINT then CONTENT | Each channel's messages arrive in order within that channel |
| Connection flood | 50 connection attempts in 1 second | Legitimate connections still work, excess rejected gracefully |
| Duplicate peer connection | Same student connects twice | First connection closed, second accepted; no duplicate in peer list |
| Server restart | Kill and restart teacher server during active meeting | Students notified, can reconnect when server is back |
| DNS resolution failure | Invalid hostname for P2P server | Clear error, connection failed event, no crash |
| Port already in use | Start P2P server on occupied port | Clear error "port in use", tries next port or reports to user |

#### Smoke Tests (Manual)

| Step | Action | Expected Result |
|---|---|---|
| 1 | Teacher creates meeting on machine A | Meeting listed on hub, P2P server listening |
| 2 | Student joins meeting on machine B (same LAN) | P2P connects, both show "Connected" |
| 3 | Student joins on machine C (different network, via internet) | P2P connects (STUN succeeds), both show "Connected" |
| 4 | Send a text message from teacher | Student sees the message |
| 5 | Disconnect student's network for 10 seconds, reconnect | Auto-reconnect, meeting resumes |
| 6 | Teacher ends meeting | All students disconnected cleanly, meeting removed from list |
| 7 | Check TLS certificate exchange | Wireshark shows encrypted traffic, no plaintext |
| 8 | Test on Windows machine | Same results as Linux |

### Acceptance Criteria
- [ ] Teacher creates meeting → P2P server starts listening
- [ ] Student joins meeting → signaling exchanges peer info
- [ ] P2P connection established (via STUN + direct connect)
- [ ] TLS verified on P2P channel
- [ ] Meeting window shows "Connected" status
- [ ] Participant list updates in real-time
- [ ] Graceful disconnect + reconnect handling
- [ ] All unit, integration, and edge-case tests pass
- [ ] Smoke tests pass across LAN and internet

### Do NOT build in this phase
- No audio streaming yet
- No content sharing yet
- No paint sync yet (just control channel working)

---

## Phase 4: Audio Communication

**Deliverable:** Real-time voice chat between teacher and students over P2P.

### Depends on
- Phase 3 (P2P connection established)

### Tasks

| # | Task | Files | Test |
|---|---|---|---|
| 4.1 | Audio capture (QAudioInput → PCM frames) | `services/audio.py` | capture mic input |
| 4.2 | Opus encoding/decoding | `services/audio.py` | encode → decode → same audio |
| 4.3 | Audio streaming on AUDIO channel | `services/audio.py` | frames arrive at peer |
| 4.4 | Audio playback (Opus → PCM → QAudioOutput) | `services/audio.py` | hear the other person |
| 4.5 | Multi-student audio mixing (teacher side) | `services/audio.py` | hear all students |
| 4.6 | Audio controls widget (mute/unmute, volume) | `ui/widgets/audio_controls.py` | click mute → stops sending |
| 4.7 | Audio indicator in participant bar | `ui/widgets/participant_bar.py` | mic icon shows who's speaking |
| 4.8 | Latency measurement and optimization | `services/audio.py` | < 200ms round-trip |

### Test Plan: Phase 4

#### Unit Tests (`tests/unit/`)

**`test_audio.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Capture produces frames | Start audio capture for 1 second | Non-empty PCM frames produced |
| Opus encode/decode round-trip | PCM frame → encode → decode | Decoded audio matches original within tolerance |
| Encode empty frame | Silent audio (all zeros) | Encodes/decodes without error |
| Frame size consistency | Capture at 20ms frame size | All frames are exactly 20ms worth of samples |
| Mute sends silence | Enable mute | Audio frames sent are all zeros (or not sent at all) |
| Volume scale | Set volume to 0.5 | Output amplitude is half of input |
| Multiple sample rates | 48000Hz and 44100Hz | Both work, resampled if needed |

#### Integration Tests (`tests/integration/`)

**`test_audio_streaming.py`** (with local P2P connection)
| Test Case | Input | Expected Result |
|---|---|---|
| Audio frame arrives at peer | Capture + send 1 second of audio | Frames received on AUDIO channel at peer |
| End-to-end latency | Send timestamped audio frame | Round-trip < 300ms |
| Mute/unmute sync | Teacher mutes | Student stops receiving audio frames (or receives silence) |
| Two students speaking | Both send audio to teacher | Teacher receives both streams, can distinguish them |
| Audio under load | Send audio + paint strokes simultaneously | Audio quality not degraded, no dropouts |
| Audio frame ordering | Send 100 frames | All arrive in order |
| Frame drop under congestion | Overwhelm AUDIO channel | Old frames dropped, recent frames prioritized |

#### Edge-Case Tests (`tests/edge_cases/`)

| Test Case | Input | Expected Result |
|---|---|---|
| No microphone available | No audio input device | Graceful message "no mic found", meeting continues without audio |
| Microphone unplugged mid-meeting | Remove USB mic while streaming | Error logged, audio stopped, user notified, meeting continues |
| Feedback loop (speaker → mic) | Play audio that feeds back into mic | System remains stable (no runaway amplification) |
| Very loud input | Audio at max clipping level | No crash, audio clipped cleanly |
| Very quiet input | Near-silent audio | Opus handles it, no encoding errors |
| Network jitter simulation | Random 0-500ms delay on audio frames | Playback buffer absorbs jitter, audio stays smooth |
| Packet loss simulation | Drop 5% of audio frames | Minor quality degradation, no crash, audio continues |
| Long meeting audio | Stream audio for 2 hours continuously | No memory leak, no degradation, stable CPU usage |
| Rapid mute/unmute toggle | Toggle mute 50 times in 5 seconds | Final state correct, no audio glitch |

#### Smoke Tests (Manual)

| Step | Action | Expected Result |
|---|---|---|
| 1 | Start meeting between teacher and student | Both connected |
| 2 | Teacher speaks | Student hears teacher's voice clearly |
| 3 | Student speaks | Teacher hears student's voice clearly |
| 4 | Teacher clicks mute button | Student hears silence, mute icon shows on participant bar |
| 5 | Teacher unmutes | Audio resumes immediately |
| 6 | Adjust volume slider | Volume changes accordingly |
| 7 | Speak for 10 minutes continuously | No quality degradation, no lag increase |
| 8 | Test with 3 students | Teacher hears all 3 students, each student hears teacher |
| 9 | Check CPU usage during audio | < 10% on modern machine |
| 10 | Test on Windows | Same audio quality as Linux |

### Acceptance Criteria
- [ ] Teacher speaks → student hears clearly
- [ ] Student speaks → teacher hears clearly
- [ ] Mute/unmute works instantly
- [ ] Multiple students can speak simultaneously
- [ ] Latency is acceptable for conversation (< 300ms)
- [ ] All unit, integration, and edge-case tests pass
- [ ] Smoke tests pass with real microphones on both platforms

### Do NOT build in this phase
- No video/camera (placeholder only)
- No content sharing

---

## Phase 5: Content Sharing (PDF + Paint Sync)

**Deliverable:** Teacher and students see the same PDF page with synchronized paint overlay.

### Depends on
- Phase 1 (paint component)
- Phase 3 (P2P networking)

### Tasks

| # | Task | Files | Test |
|---|---|---|---|
| 5.1 | PDF rendering widget (QPdfDocument) | `ui/widgets/pdf_viewer.py` | displays PDF pages |
| 5.2 | Content view widget (PDF background + paint overlay) | `ui/widgets/content_view.py` | paint draws over PDF |
| 5.3 | PDF file transfer over CONTENT channel | `services/content_sync.py` | student receives PDF |
| 5.4 | PDF page change sync | `services/content_sync.py` | teacher flips page → student follows |
| 5.5 | Paint stroke sync over PAINT channel | `services/content_sync.py` | teacher draws → student sees stroke |
| 5.6 | Remote paint rendering (apply received strokes) | `services/paint_engine.py` | stroke appears on student canvas |
| 5.7 | Canvas size sync (ensure same viewport dimensions) | `services/content_sync.py` | both see same area |
| 5.8 | Toolbar integration (page nav + drawing tools in meeting) | `ui/widgets/toolbar.py` | all tools work in meeting |
| 5.9 | End-to-end test: full meeting with content sharing | `tests/e2e/` | full flow works |
| 5.10 | Performance optimization (incremental rendering) | paint engine | smooth drawing with PDF loaded |

### Test Plan: Phase 5

#### Unit Tests (`tests/unit/`)

**`test_content_sync.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| PDF file chunking | 5MB PDF file | Split into chunks ≤ 64KB, reassembled correctly |
| Page change message | Teacher on page 3 → sends page_change | Student receives page=3 |
| Stroke sync message | PaintEngine stroke → serialized | Stroke data received matches original |
| Canvas dimensions sync | Teacher canvas 1200x800 | Student receives dimensions, adjusts viewport |
| PDF hash verification | Transfer PDF, check hash | Hashes match (no corruption) |
| Missing PDF request | Student doesn't have PDF | Requests transfer, receives full PDF |

**`test_pdf_viewer.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Render page 1 | Load PDF, render page 1 | Image displayed, correct content |
| Render page N | Jump to page 5 | Correct page rendered |
| Render beyond last page | Request page 999 | Shows last page or error, no crash |
| Empty PDF | 0-page PDF | Shows "empty document" message |
| Corrupted PDF | Random bytes with .pdf extension | Graceful error "cannot open PDF" |
| Password-protected PDF | Encrypted PDF without password | Error message "PDF is encrypted" |
| Large PDF (200 pages) | Load and navigate | Page thumbnails load on demand, no OOM |

**`test_content_view.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| PDF + paint overlay | Load PDF, draw stroke on top | Stroke renders over PDF, both visible |
| Clear paint only | Clear paint overlay | PDF remains, paint removed |
| Page change preserves paint | Change page with existing paint | Paint for page 1 saved, page 2 starts clean |
| Return to page with paint | Go to page 2, return to page 1 | Previous paint on page 1 restored |

#### Integration Tests (`tests/integration/`)

**`test_content_sync_flow.py`** (with local P2P connection)
| Test Case | Input | Expected Result |
|---|---|---|
| Full PDF share | Teacher loads 10-page PDF | Student receives all pages, displays page 1 |
| Page sync | Teacher navigates to page 3 → 5 → 2 | Student follows: page 3 → 5 → 2 |
| Paint sync real-time | Teacher draws 5 strokes | Student sees all 5 strokes appear |
| Paint + page change | Draw on page 1, go to page 2, draw more | Student sees correct paint on each page |
| Eraser sync | Teacher erases a stroke | Stroke disappears on student's view |
| Clear sync | Teacher clicks clear | Student's paint overlay cleared |
| Multiple students receive | Teacher shares PDF to 3 students | All 3 receive and display correctly |
| Late joiner | Student joins after PDF was shared | Student receives PDF on join, synced to current page |

#### Edge-Case Tests (`tests/edge_cases/`)

| Test Case | Input | Expected Result |
|---|---|---|
| Very large PDF (100MB) | Share a large textbook PDF | Transfer completes, pages render on demand, no OOM |
| PDF with images | PDF containing photos/diagrams | Images render correctly on both sides |
| Rapid page flipping | Click through 50 pages in 5 seconds | Student keeps up, no stale pages shown |
| Draw during PDF transfer | Start drawing before PDF fully loads | Drawing works on blank canvas, PDF appears underneath when ready |
| Network interruption during PDF transfer | Disconnect mid-transfer | Transfer resumes or restarts, no partial/corrupted file |
| 500 strokes on one page | Draw continuously for 2 minutes | Both sides render smoothly, sync keeps up |
| Stroke received out of order | Strokes arrive 3→1→2 | PaintEngine reorders and renders correctly |
| Concurrent operations | Draw + flip page + new student joins simultaneously | All operations complete correctly, no race condition |
| Zero-byte PDF file | Try to share an empty file | Clear error "invalid PDF", no crash |
| PDF with special characters in filename | `数学-第三章 (2).pdf` | File shared successfully regardless of filename |

#### Smoke Tests (Manual)

| Step | Action | Expected Result |
|---|---|---|
| 1 | Teacher loads a math PDF (10+ pages) | PDF appears on teacher's screen |
| 2 | Student checks their screen | Same PDF, same page |
| 3 | Teacher navigates to page 5 | Student's view updates to page 5 |
| 4 | Teacher draws a circle over a math problem | Student sees the circle overlay |
| 5 | Teacher writes "Solve this" with touchpad pen | Student sees the writing appear in real-time |
| 6 | Teacher erases part of the writing | Erased part disappears on student's view |
| 7 | Teacher flips to page 6, draws an arrow | Student sees page 6 with arrow |
| 8 | Teacher goes back to page 5 | Student sees page 5 with original circle (paint restored) |
| 9 | Teacher clicks clear | Student's paint overlay cleared, PDF remains |
| 10 | Teacher loads a different PDF | Student's view updates to new PDF |
| 11 | Run for 30 minutes with continuous drawing | No slowdown, no memory leak |
| 12 | Test on Windows | Same behavior as Linux |

### Acceptance Criteria
- [ ] Teacher loads PDF → appears on student's screen
- [ ] Teacher changes page → student's view updates
- [ ] Teacher draws on PDF → paint appears on student's overlay
- [ ] Eraser and clear sync to students
- [ ] Both see the same content at the same time
- [ ] Drawing performance is smooth (no visible lag on local rendering)
- [ ] All unit, integration, and edge-case tests pass
- [ ] Smoke tests pass with real PDFs on both platforms

### This completes the core product.

---

## Phase 6: AI Assistant (Three Sub-Phases)

**Deliverable:** Photo → scanned image → one-question-per-page PDF → LLM tutoring.
Target difficulty: AMC 12 level (US middle/high school math competition).

### Depends on
- Phase 5 (content sharing — generated PDFs can be shared in meetings)

### Architecture

```
Photo ──► [6.1 Scanner] ──► Scanned PNG
                                    │
                              [6.2 Segmenter] ──► Question PDF (1 per page)
                                    │
                              [6.3 LLM Tutor] ──► Structured tutorial
```

Sub-phases 6.1 and 6.2 run **locally** (no API, no LLM). Only 6.3 requires
an external API call.

---

### Sub-Phase 6.1: Photo → High-Quality Scanned Image

**Deliverable:** A phone photo becomes a clean, perspective-corrected PNG.

#### Tasks

| # | Task | Files |
|---|---|---|
| 6.1.1 | Edge detection + 4-point perspective transform | `ai/scanner.py` |
| 6.1.2 | Adaptive contrast/brightness normalization | `ai/scanner.py` |
| 6.1.3 | Output as PNG (lossless, preserves text/line art) | `ai/scanner.py` |
| 6.1.4 | Scanner UI: file open or clipboard paste | `ui/windows/scanner.py` |
| 6.1.5 | Tests | `tests/unit/test_scanner.py` |

#### Test Plan

**`test_scanner.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Perspective correction | Angled photo of paper | Output is top-down rectangle |
| Edge detection | Photo with clear paper edges | 4 corners detected |
| No paper detected | Random photo without paper | Returns None or error |
| Skewed 45 degrees | Paper rotated 45° | Corrected to upright |
| Dark photo | Underexposed image | Brightened to readable |
| High resolution | 4K photo | Processed without OOM |
| Low resolution | 640x480 | Usable output with quality warning |
| Output is PNG | Any valid input | Lossless PNG produced |

---

### Sub-Phase 6.2: Question Segmentation → One-Question-Per-Page PDF

**Deliverable:** Scanned image is split into questions; each becomes a PDF page.

**Approach:** A light local OCR pass (Tesseract via `pytesseract`) extracts
just enough text to detect numbering patterns ("1.", "2.", "1.1", "(a)").
Combined with visual gap analysis, this correctly identifies question
boundaries even when questions follow section headers with no blank line.
The OCR does NOT understand the math — it only detects "this line starts
with a number pattern → new question." Full comprehension is left for the
LLM in 6.3.

#### Tasks

| # | Task | Files |
|---|---|---|
| 6.2.1 | Light OCR pass: Tesseract word-level extraction with bounding boxes | `ai/segmenter.py` |
| 6.2.2 | Numbering pattern detection: "1.", "2.", "1.1", "(a)", "Q1", etc. | `ai/segmenter.py` |
| 6.2.3 | Combine OCR patterns + visual gap analysis for question boundaries | `ai/segmenter.py` |
| 6.2.4 | Handle section headers (non-question text before first numbered item) | `ai/segmenter.py` |
| 6.2.5 | Figure/plot region detection (non-text connected components) | `ai/segmenter.py` |
| 6.2.6 | Crop question regions preserving original image quality | `ai/segmenter.py` |
| 6.2.7 | Generate PDF: each page = one question image + blank answer area | `ai/segmenter.py` |
| 6.2.8 | Handle multi-column layouts | `ai/segmenter.py` |
| 6.2.9 | Tests | `tests/unit/test_segmenter.py` |

#### Test Plan

**`test_segmenter.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Single question | Image with 1 numbered question | PDF with 1 page |
| Multiple questions | Image with 3 numbered questions | PDF with 3 pages |
| Section header + questions | "Section 1 Practice\n1. Consider..." | Header excluded, question detected |
| No gap between questions | "1. question...2. next..." | Both questions split correctly |
| Question with figure | Geometry problem with plot | Figure region included on same page |
| Dense layout | Questions with minimal spacing | Boundaries detected via numbering |
| Empty scan | Blank paper | "No questions detected" |
| Multi-column | Two-column exam layout | Correct column splitting |
| Numbering patterns | "1.", "1.1", "(a)", "Q1" | All patterns recognized |

---

### Sub-Phase 6.3: LLM-Powered Tutoring

**Deliverable:** Reusable prompt + API integration for AMC 12 level math tutoring.

#### Tasks

| # | Task | Files |
|---|---|---|
| 6.3.1 | Design reusable tutoring prompt | `ai/tutor_prompt.py` |
| 6.3.2 | API integration (Claude / GPT-4V multimodal) | `ai/tutor.py` |
| 6.3.3 | Structured output parsing (concept, hints, solution) | `ai/tutor.py` |
| 6.3.4 | Settings UI for API key (keyring storage) | `ui/windows/settings.py` |
| 6.3.5 | Display tutor response in meeting window | `ui/windows/meeting.py` |
| 6.3.6 | Integration: segmented PDF → load into meeting | wiring |
| 6.3.7 | Tests | `tests/unit/test_tutor.py` |

#### Prompt Design Principles

1. **Single-call efficiency**: one image + minimal context → full tutoring response
2. **Structured output**: concept tags, difficulty (1-5), hint ladder (3 hints, escalating), full solution
3. **Subject coverage**: algebra, geometry, combinatorics, number theory, probability
4. **Format**: JSON output for reliable parsing
5. **Language**: support English and Chinese question text

#### Test Plan

**`test_tutor.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Structured prompt generation | Question image metadata | Valid prompt with context |
| API response parsing | Mock JSON response | Structured tutoring object |
| API unreachable | Connection error | Clear error, no crash |
| Invalid API key | 401 response | Clear "auth failed" message |
| Malformed API response | Garbage JSON | Fallback gracefully |
| Prompt reuse | Same prompt, different images | Correct context injection |

#### Integration Tests

**`test_ai_to_meeting.py`**
| Test Case | Input | Expected Result |
|---|---|---|
| Scan → segment → PDF → meeting | Full pipeline | PDF loads in meeting |
| API key persistence | Set key, restart | Key survives restart |

#### Smoke Tests (Manual)

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open a photo of a worksheet | Image loads in scanner |
| 2 | Click "Scan" | Clean perspective-corrected PNG |
| 3 | Click "Segment" | Questions separated into PDF pages |
| 4 | Load segmented PDF into meeting | PDF appears on teacher + student screens |
| 5 | Click "Get Tutorial" on a question | LLM returns step-by-step tutorial |
| 6 | Test with geometry problem (figure) | Figure preserved in segmented PDF |
| 7 | Test with Chinese text | Recognized and handled |

---

## Development Workflow

### Branch Strategy
```
main (stable)
  ├── phase/0-foundation
  ├── phase/1-paint
  ├── phase/2-hub-auth
  ├── phase/3-p2p-network
  ├── phase/4-audio
  ├── phase/5-content-sync
  └── phase/6-ai-assistant
```

Each phase branch merges to `main` only when all acceptance criteria pass.

### Testing Requirements
- **Unit tests:** Every module in `core/`, `transport/`, `services/`
- **Integration tests:** Between layers (signaling client ↔ hub server, P2P client ↔ P2P server)
- **Edge-case tests:** Boundary conditions, error paths, stress scenarios for every module
- **E2E tests:** Full meeting flow (Phase 5+)
- **Manual/smoke tests:** Touchpad input, audio quality, NAT traversal — run before phase sign-off

### CI Pipeline
```
On every push:
  1. Lint (ruff)
  2. Unit tests         → pytest tests/unit/
  3. Edge-case tests    → pytest tests/edge_cases/
  4. Integration tests  → pytest tests/integration/
  5. Build check        → pip install -e .

Before phase merge to main:
  1. All automated tests above pass
  2. Manual smoke test checklist completed
  3. Code review approved
```
