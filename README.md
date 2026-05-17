# ChenEduSys

Peer-to-peer education platform for 1-on-1 and small-group tutoring.

A teacher and students connect directly over their networks for real-time voice chat, shared PDF viewing, and synchronized paint overlay. A lightweight cloud hub server handles account registration and meeting coordination — all real-time data flows P2P.

## Prerequisites

| Requirement | Linux | Windows |
|---|---|---|
| **Conda** | Miniconda or Anaconda | Miniconda or Anaconda |
| **C compiler** | gcc (usually pre-installed) | Visual Studio Build Tools (for compiling PyAudio) |
| **PortAudio** | `libportaudio2` | Bundled with PyAudio wheel |
| **Opus** | `libopus0` | Bundled with opuslib |
| **ALSA** | `libasound2` | N/A |

### System dependencies

**Linux (Debian/Ubuntu):**
```bash
sudo apt-get install libportaudio2 libasound2 libopus0
```

**Windows:**
No extra system packages needed. PyAudio provides a pre-built wheel that includes PortAudio. If pip fails to build PyAudio, install [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) (select "Desktop development with C++").

## Installation

### 1. Create and activate the conda environment

```bash
conda env create -f environment.yml
conda activate chenedusys
```

This creates a `chenedusys` environment with Python >=3.10 and installs all Python dependencies via pip.

### 2. Verify installation

```bash
# Check all imports work
python -c "import PySide6; import opuslib; import pyaudio; import msgpack; import aiohttp; print('All dependencies OK')"

# Run the test suite
pytest tests/ -q
```

### 3. Run the application

```bash
python -m chenedusys
```

## Hub Server (Cloud Deployment)

The hub server runs on a cloud VM and handles user accounts and meeting coordination.

### Deploy to a server

```bash
# Copy hub server files
scp -r hub_server/ user@your-server:~/chenedusys/

# SSH into the server
ssh user@your-server

# Install dependencies
pip install aiohttp msgpack argon2-cffi PyJWT

# Set a JWT secret and start
export CHENEDUSYS_JWT_SECRET='your-secret-key-here'
cd ~/chenedusys && PYTHONPATH=. python3 -m hub_server.main
```

The server listens on port **8443** by default. Make sure the firewall allows TCP traffic on that port.

### Test the server

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

- **UI Layer**: Login, dashboard, meeting room, paint canvas, audio controls
- **Services**: Auth, audio, paint engine, meeting orchestration
- **Transport**: P2P protocol, TCP server/client, STUN NAT traversal, TLS, signaling
- **Core**: EventBus (pub/sub), config (pydantic-settings), data models

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
├── services/      # Auth, audio, paint engine, meeting
├── transport/     # P2P protocol, server, client, NAT, TLS, signaling
└── ui/            # PySide6 windows and widgets
hub_server/        # Standalone hub server (deploy to cloud)
tests/             # Unit, integration, edge-case tests
```

## License

MIT
