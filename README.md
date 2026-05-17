# ChenEduSys

Peer-to-peer education platform for 1-on-1 and small-group tutoring.

A teacher and students connect directly over their networks for real-time voice chat, shared PDF viewing, and synchronized paint overlay. A lightweight cloud hub server handles account registration and meeting coordination — all real-time data flows P2P.

## Quick Start

```bash
git clone git@github.com:luckychen/ChenEduSys.git
cd ChenEduSys
conda env create -f environment.yml
conda activate chenedusys
pytest tests/ -q          # verify everything works
python -m chenedusys      # launch the app
```

> **Linux users:** install system packages first — see [Prerequisites](#prerequisites) below.

## Features

- **Real-time P2P connectivity** — teacher and students connect directly, no relay needed
- **Voice chat** — Opus codec, low-latency, cross-platform (PyAudio)
- **Shared PDF viewing** — teacher controls which page is displayed
- **Paint overlay** — draw, erase, clear on top of any content; synced to all participants
- **Document scanner** — photo to clean, perspective-corrected PNG (OpenCV, runs locally)
- **Question segmenter** — split a scanned worksheet into one-question-per-page PDF (runs locally)
- **AI tutoring** — send a question image to Claude or GPT-4V for structured hints and solutions

## Prerequisites

The only assumption is that you have **conda** (Miniconda or Anaconda) installed.

### Linux (Debian/Ubuntu)

Install these system packages **before** creating the conda environment:

```bash
sudo apt-get install libportaudio2 libasound2 libopus0
```

| Package | Why needed |
|---|---|
| `libportaudio2` | PyAudio links against the PortAudio C library for microphone/speaker access |
| `libasound2` | ALSA — the Linux sound system |
| `libopus0` | opuslib links against the Opus codec C library for voice encoding |

### Windows

No extra system packages needed. PyAudio, opuslib, and PyMuPDF ship pre-built wheels that bundle the required DLLs.

If `pip install PyAudio` fails with a build error, install [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) (select "Desktop development with C++") and retry.

### Optional: OCR support (question segmenter)

The question segmenter works without OCR using visual gap analysis. For better accuracy with numbered questions, install Tesseract:

- **Linux:** `sudo apt-get install tesseract-ocr`
- **Windows:** download the installer from [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki)

The `pytesseract` Python package is already listed in the dependencies — it just needs the Tesseract binary on your PATH.

## Installation

### 1. Clone the repository

```bash
git clone git@github.com:luckychen/ChenEduSys.git
cd ChenEduSys
```

### 2. Create the conda environment

```bash
conda env create -f environment.yml
conda activate chenedusys
```

This creates a `chenedusys` environment with Python >=3.10 and installs all Python dependencies via `pip install -e ".[dev]"`.

### 3. Verify

```bash
# Check all core imports work
python -c "import PySide6; import opuslib; import pyaudio; import msgpack; import aiohttp; print('All dependencies OK')"

# Run the test suite
pytest tests/ -q
```

You should see all tests pass (~346 tests).

### 4. Run the application

```bash
python -m chenedusys
```

Or use the installed entry point:

```bash
chenedusys
```

## Hub Server (Cloud Deployment)

The hub server runs on a cloud VM and handles user accounts and meeting coordination. It is a standalone aiohttp application with no dependency on the client package.

### Deploy

```bash
# 1. Copy hub server files to your server
scp -r hub_server/ user@your-server:~/chenedusys/

# 2. SSH in and install dependencies
ssh user@your-server
cd ~/chenedusys
pip install -r hub_server/requirements.txt

# 3. Set a JWT secret and start
export CHENEDUSYS_JWT_SECRET='your-secret-key-here'
PYTHONPATH=. python3 -m hub_server.main
```

The server listens on **port 8443** by default (`CHENEDUSYS_HUB_PORT` env var to override). Open that port in your firewall.

### Verify

```bash
curl http://YOUR_SERVER_IP:8443/health
# {"status": "ok"}
```

## Configuration

ChenEduSys uses a TOML config file at `~/.chenedusys/config.toml`. All settings can be overridden with environment variables prefixed with `CHENEDUSYS_`.

| Setting | Default | Env var |
|---|---|---|
| Hub URL | `wss://localhost:8443` | `CHENEDUSYS_HUB_URL` |
| Log level | `INFO` | `CHENEDUSYS_LOG_LEVEL` |
| P2P port range | `9100-9200` | `CHENEDUSYS_P2P_PORT_RANGE_START` / `END` |
| STUN servers | `stun:stun.l.google.com:19302` | `CHENEDUSYS_P2P_STUN_SERVERS` |
| Audio sample rate | `48000` | `CHENEDUSYS_AUDIO_SAMPLE_RATE` |

## Architecture

```
UI Layer (PySide6)  →  Services  →  Transport  →  Core (EventBus, Config, Models)
                              ↕
                        Hub Server (cloud, signaling only)
```

- **UI Layer**: Login, dashboard, meeting room, paint canvas, audio controls, scanner, segmenter, tutor panel
- **Services**: Auth, audio, paint engine, meeting orchestration, content sync
- **Transport**: P2P protocol, TCP server/client, STUN NAT traversal, TLS, signaling
- **Core**: EventBus (pub/sub), config (pydantic-settings), data models
- **AI**: Document scanner, question segmenter, LLM tutor (Claude/GPT-4V)

## Development

```bash
conda activate chenedusys
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint
ruff check src/ tests/
```

### Project structure

```
src/chenedusys/
├── core/          # EventBus, config, models, logging
├── services/      # Auth, audio, paint engine, meeting, content sync
├── transport/     # P2P protocol, server, client, NAT, TLS, signaling
├── ui/            # PySide6 windows and widgets
└── ai/            # Document scanner, question segmenter, LLM tutor
hub_server/        # Standalone hub server (deploy to cloud)
tests/             # Unit, integration, edge-case tests (346 total)
```

## Troubleshooting

### PyAudio fails to install on Linux

```
src/_portaudiomodule.c: fatal error: portaudio.h: No such file
```

Fix: `sudo apt-get install libportaudio2 libasound2-dev`

### PyAudio fails to install on Windows

```
error: Microsoft Visual C++ 14.0 or greater is required
```

Fix: install [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) and select "Desktop development with C++".

### PySide6 import error after environment creation

This can happen if the conda solver produced a conflicting package layout. Delete and recreate:

```bash
conda env remove -n chenedusys
conda env create -f environment.yml
```

### Tests fail with "ModuleNotFoundError: No module named 'chenedusys'"

The package must be installed in editable mode. The `environment.yml` handles this, but if you skipped it:

```bash
pip install -e ".[dev]"
```

## License

MIT
