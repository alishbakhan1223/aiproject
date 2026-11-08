# AI-Based Smart CCTV Surveillance System

An intelligent, real-time CCTV surveillance and threat detection platform built with **FastAPI**, **React (Vite)**, **PostgreSQL with pgvector**, and **Ultralytics YOLO / InsightFace**.

The system addresses the limitations of standard passive surveillance by actively analyzing live camera streams for weapons, restricted objects, unauthorized zone intrusions, and recognized or unknown individuals, dispatching immediate alerts with snapshot images to **WhatsApp** and **Telegram**.

---

## 📋 Table of Contents

- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
  - [1. Clone Repository](#1-clone-the-repository)
  - [2. Backend Setup](#2-backend-setup)
  - [3. Frontend Setup](#3-frontend-setup)
  - [4. AI Model Setup](#4-ai-model-setup)
- [Environment Variables](#-environment-variables)
- [Database & Services Setup](#-database--services-setup)
- [How to Run](#-how-to-run)
  - [Option A — One-Click Scripts (Recommended)](#option-a--one-click-scripts-recommended)
  - [Option B — Manual Startup (Separate Terminals)](#option-b--manual-startup-separate-terminals)
- [How to Use the Application](#-how-to-use-the-application)
- [API Endpoints Overview](#-api-endpoints-overview)
- [Troubleshooting](#-troubleshooting)
- [Important Notes](#-important-notes)
- [Author & License](#-author--license)

---

## 🚀 Features

* 🔫 **Real-Time Threat & Weapon Detection** — Detects firearms, knives, grenades, and explosives using specialized YOLOv8 computer vision models.
* 🛡️ **Temporal Multi-Frame Confirmation** — Sliding window tracker suppresses false positives by requiring consecutive detection confirmations before triggering alarms.
* 👤 **Face Recognition (InsightFace & ArcFace)** — Extracts 512-dimensional facial embeddings using the `buffalo_l` model, storing them in PostgreSQL with `pgvector` for instant vector similarity lookup.
* 🆔 **Unknown Person Tracking & Clustering** — Automatically assigns stable tracking IDs (e.g. `Unknown-001`) to unregistered individuals, records sighting history, and allows 1-click promotion to "Known Person".
* 📐 **Interactive Intrusion Zone Editor** — Draw custom polygon intrusion zones directly over live video feeds to detect trespassers.
* 📦 **Restricted Object Detection** — Monitors for restricted or abandoned items (e.g. backpacks, suitcases, laptops).
* 🎥 **Clean MJPEG Live Streaming** — High-performance, low-latency live camera streaming without intrusive bounding boxes obscuring the video feed.
* 📲 **Multi-Channel Alert Dispatcher** — Automated image snapshot alerts sent via **WhatsApp Cloud API** and **Telegram Bot API** with automated fallback and broadcast modes.
* 📊 **Analytics & System Health** — Real-time event log, alert history, detection statistics, and camera worker thread health monitoring.
* 🔐 **Role-Based Access Control (RBAC)** — Secure JWT-based authentication supporting **Admin** and **User** workspaces.

---

## 🛠️ Tech Stack

| Layer | Technology | Details |
|---|---|---|
| **Backend Framework** | **FastAPI** (`>=0.111.0`) | High-performance async REST API & streaming server |
| **ASGI Server** | **Uvicorn** (`>=0.30.0`) | Lightning-fast ASGI production web server |
| **Frontend Framework** | **React 18** (`^18.3.1`) + **Vite 5** (`^5.3.1`) | Fast, reactive single-page interface |
| **Styling** | **Tailwind CSS** (`^3.4.4`) | Modern utility-first responsive design |
| **Database** | **PostgreSQL** (`15+` / `16`) + **pgvector** (`>=0.2.5`) | Relational database with vector similarity indexing |
| **Message Queue / Cache** | **Redis** (`7.x` Alpine) + **Redis Streams** | Event streaming and background task communication |
| **Object & Threat Detection** | **Ultralytics YOLOv8** (`>=8.2.18`) | Object detection (`yolov8n`) & custom threat models |
| **Face Analysis & Embeddings**| **InsightFace** (`>=0.7.3`) + **ONNX Runtime** | ArcFace face detection, alignment, and 512-d embeddings |
| **Deep Learning Engine** | **PyTorch** (`>=2.2.0`) + **Torchvision** (`>=0.17.0`) | Neural network acceleration (CPU or CUDA GPU) |
| **Computer Vision** | **OpenCV** (`opencv-python-headless >=4.9.0`) | Video stream decoding, frame transformation, and MJPEG |
| **Containerization** | **Docker** & **Docker Compose** (`v2.x`) | Containerized Postgres (`ankane/pgvector`) and Redis |

---

## 📁 Project Structure

```text
Smart-surveillance-system/
├── backend/                        # FastAPI Python backend application
│   ├── app/                        # Application core modules
│   │   ├── routers/                # API route handlers (auth, camera, faces, zones, etc.)
│   │   ├── alert_dispatcher.py     # Multi-channel alert dispatcher (WhatsApp & Telegram)
│   │   ├── auth.py                 # JWT token generation, password hashing, and user seeding
│   │   ├── camera_worker.py        # Dedicated background thread per camera for CV inference
│   │   ├── config.py               # Pydantic environment configuration loader
│   │   ├── database.py             # SQLAlchemy engine & session management
│   │   ├── face_engine.py          # InsightFace model wrapper for face embeddings
│   │   ├── main.py                 # FastAPI application factory, CORS, and startup hooks
│   │   ├── models.py               # SQLAlchemy database schema definitions
│   │   ├── object_engine.py        # YOLO object detection wrapper
│   │   ├── schemas.py              # Pydantic request/response validation models
│   │   ├── telegram.py             # Telegram Bot API client for photo & text messages
│   │   ├── weapon_engine.py        # YOLO threat & weapon detection logic
│   │   └── whatsapp.py             # Meta WhatsApp Cloud API client
│   ├── Dockerfile                  # Container definition for backend
│   └── requirements.txt            # Python backend dependencies
├── frontend/                       # Vite + React frontend application
│   ├── src/                        # React source code
│   │   ├── components/             # Reusable UI components (LiveFeed, EventsTable, Nav, etc.)
│   │   ├── pages/                  # Route views (Dashboard, Alerts, Persons, Users, Zones)
│   │   ├── services/ / api.js      # Axios client configuration for backend API
│   │   ├── App.jsx                 # Application root with client-side routing
│   │   └── main.jsx                # React DOM entrypoint
│   ├── package.json                # Frontend package configuration and scripts
│   └── vite.config.js              # Vite bundler configuration
├── models/                         # Local AI model directory
│   └── weapon/                     # Directory for weapon threat models (threat-yolov8n.pt)
├── docker-compose.yml              # Multi-container orchestration (PostgreSQL + Redis)
├── run_all.py                      # Multi-process orchestrator for Backend + Frontend
├── start.bat                       # Windows double-click startup script
├── start.ps1                       # PowerShell startup script
├── CAMERA_SOURCES.md               # Guide for connecting USB webcams and RTSP IP cameras
├── .env.example                    # Template environment variables (no secrets)
└── .gitignore                      # Strict Git ignore configuration
```

---

## ⚙️ Prerequisites

Before installing, ensure your system has the following installed:

1. **Python**: Version `3.10` or `3.11` (64-bit). *(Download from [python.org](https://www.python.org/downloads/))*.
2. **Node.js**: Version `18.x` or `20.x` LTS and `npm`. *(Download from [nodejs.org](https://nodejs.org/))*.
3. **Docker Desktop**: Docker Engine `v20+` and Docker Compose `v2+`. *(Download from [docker.com](https://www.docker.com/products/docker-desktop/))*.
4. **Git**: Installed and available in your terminal path.
5. **Video Source**: Either a local USB webcam (index `0`), a video file, or an RTSP network camera stream.
6. **Hardware (GPU Optional)**: A CUDA-enabled NVIDIA GPU with CUDA 11.8 or 12.x provides faster inference; CPU execution is fully supported out of the box.

---

## 📦 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/alishbakhan1223/aiproject.git
cd aiproject
```

---

### 2. Backend Setup

Create a Python virtual environment and install the required packages:

#### On Windows (PowerShell / Command Prompt):
```powershell
python -m venv backend\venv
backend\venv\Scripts\activate
pip install --upgrade pip
pip install -r backend\requirements.txt
```

#### On Linux / macOS:
```bash
python3 -m venv backend/venv
source backend/venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
```

> **Note on dependencies:** `numpy` is pinned to `<2.0.0` in `requirements.txt` for full binary compatibility with PyTorch, InsightFace, and OpenCV.

---

### 3. Frontend Setup

In a new terminal window, install the React frontend packages:

```bash
cd frontend
npm install
cd ..
```

---

### 4. AI Model Setup

The system utilizes three computer vision models:

1. **General Object Model (`yolov8n.pt`)**:
   - Downloaded automatically by Ultralytics on first run if not present in the project root.
2. **Threat & Weapon Model (`models/weapon/threat-yolov8n.pt`)**:
   - The backend includes an automated downloader from HuggingFace (`Subh775/Threat-Detection-YOLOv8n`).
   - If downloading manually, place the `.pt` file into `models/weapon/threat-yolov8n.pt`.
3. **InsightFace Face Recognition (`buffalo_l`)**:
   - Downloaded automatically by the `insightface` library on first run to your user directory (`~/.insightface/models/buffalo_l`).

---

## 🔐 Environment Variables

The project uses a single root `.env` file to configure secrets, databases, and alerting channels.

### Setup

Copy the template file to create your local `.env`:

```bash
cp .env.example .env
```
*(On Windows Command Prompt: `copy .env.example .env`)*

### Configuration Reference

Edit `.env` in any text editor and supply your settings:

| Variable | Required | Description | Example / Default |
|---|---|---|---|
| `DATABASE_URL` | **Yes** | PostgreSQL connection URL with psycopg2 driver | `postgresql://cctv:cctv123@localhost:5432/cctv_db` |
| `REDIS_URL` | **Yes** | Redis connection URI | `redis://localhost:6379/0` |
| `REDIS_HOST` | No | Host address for Redis | `localhost` |
| `REDIS_PORT` | No | Port for Redis | `6379` |
| `ADMIN_USERNAME` | **Yes** | Initial superadmin username created on startup | `admin` |
| `ADMIN_PASSWORD` | **Yes** | Initial superadmin password | `cctv2024` |
| `JWT_SECRET` | **Yes** | Random secret string for signing JWT authentication tokens | *(Generate with `openssl rand -hex 32`)* |
| `JWT_ALGORITHM` | No | Cryptographic algorithm for JWT | `HS256` |
| `JWT_EXPIRE_MINUTES`| No | Token validity duration in minutes | `480` |
| `WEAPON_DETECTION_ENABLED` | No | Toggle real-time weapon & threat analysis | `true` |
| `WEAPON_MODEL_PATH` | No | Relative path to weapon threat model | `models/weapon/threat-yolov8n.pt` |
| `WEAPON_CONFIDENCE` | No | Minimum confidence threshold for threat detections | `0.35` |
| `WEAPON_CONFIRMATION_COUNT` | No | Number of detections within window before alert fires | `2` |
| `WEAPON_CONFIRMATION_WINDOW_SECONDS` | No | Window duration (seconds) for confirmation hits | `6` |
| `WEAPON_COOLDOWN_SECONDS` | No | Cooldown period between repeated alerts | `10` |
| `WEAPON_CLASSES` | No | Comma-separated target classes | `Gun, Knife` |
| `WEAPON_MULTI_SCALE_ENABLED` | No | Center-crop 2nd pass for distant threats | `true` |
| `ALERT_MODE` | No | `broadcast` (both channels) or `fallback` (primary then backup) | `broadcast` |
| `PRIMARY_ALERT_PROVIDER` | No | Primary channel when in fallback mode (`telegram` or `whatsapp`) | `telegram` |
| `TELEGRAM_ENABLED` | No | Toggle Telegram alerting system | `true` |
| `TELEGRAM_BOT_TOKEN` | Optional | Telegram Bot API token from [@BotFather](https://t.me/BotFather) | `123456789:ABCDef...` |
| `TELEGRAM_CHAT_ID` | Optional | Recipient Telegram user ID or group chat ID | `987654321` |
| `WHATSAPP_ALERT_ENABLED` | No | Toggle WhatsApp alerting system | `true` |
| `WHATSAPP_TOKEN` | Optional | Meta Cloud API System User Access Token | `EAA...` |
| `WHATSAPP_PHONE_NUMBER_ID` | Optional | Phone Number ID from Meta Developer Portal | `104xxxxxxxxxxxx` |
| `WHATSAPP_ADMIN_NUMBER` | Optional | Recipient phone number (with country code, no `+`) | `923001234567` |
| `PUBLIC_BASE_URL` | Optional | Publicly accessible URL (ngrok/Cloudflare) for image links | `http://localhost:8000` |

---

## 🗄️ Database & Services Setup

The application requires **PostgreSQL** (with the `pgvector` extension) and **Redis**.

The fastest and cleanest method is using the included `docker-compose.yml`:

```bash
docker compose up postgres redis -d
```

### Automatic Table Initialization

You do **not** need to manually execute SQL scripts or create tables. 
When the FastAPI backend boots up, it automatically:
1. Executes `CREATE EXTENSION IF NOT EXISTS vector;`
2. Creates all tables (`cameras`, `events`, `users`, `known_faces`, `unknown_persons`, etc.) via `Base.metadata.create_all(bind=engine)`
3. Runs database schema synchronization scripts
4. Seeds the initial admin user using `ADMIN_USERNAME` and `ADMIN_PASSWORD` from `.env`

---

## 🚦 How to Run

### Option A — One-Click Scripts (Recommended)

Make sure **Docker Desktop** is open, then launch both Backend and Frontend with a single command:

#### On Windows:
```cmd
.\start.bat
```
*(Or double-click `start.bat` in File Explorer).*

#### On Linux / macOS or cross-platform PowerShell:
```bash
python run_all.py
```

`run_all.py` automatically checks port availability, starts containers, boots the FastAPI backend, and starts Vite.

---

### Option B — Manual Startup (Separate Terminals)

If you prefer running services independently:

#### Terminal 1: Database & Redis (Docker)
```bash
docker compose up postgres redis -d
```

#### Terminal 2: Backend (FastAPI)
```bash
# Activate your virtual environment first
# Windows: backend\venv\Scripts\activate
# Linux/Mac: source backend/venv/bin/activate

cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

#### Terminal 3: Frontend (React / Vite)
```bash
cd frontend
npm run dev
```

---

### Access URLs

| Component | URL | Notes |
|---|---|---|
| **Frontend Web App** | **`http://localhost:5173`** | User & Admin surveillance dashboard |
| **Backend REST API** | **`http://localhost:8000`** | Base URL for API requests |
| **Interactive API Docs** | **`http://localhost:8000/docs`** | Swagger UI with live endpoint testing |
| **Alternative API Docs** | **`http://localhost:8000/redoc`** | ReDoc OpenAPI specification |

---

## 🖥️ How to Use the Application

### 1. Initial Login
1. Open your browser at **`http://localhost:5173`**.
2. Sign in with the default admin credentials (from `.env`):
   - **Username**: `admin`
   - **Password**: `cctv2024`

### 2. Adding a Camera
1. Navigate to **Cameras** / **Dashboard**.
2. Click **Add Camera**:
   - **Name**: e.g. `Front Entrance`
   - **Source**: 
     - For your laptop/USB webcam: Enter `0` (or `cv2.CAP_DSHOW + 0` on Windows).
     - For an RTSP IP camera: Enter the RTSP URI (e.g. `rtsp://user:pass@192.168.1.100:554/stream`).
     - For a sample video file: Enter the local path (e.g. `data/test_feed.mp4`).
3. Click **Start** to spin up the camera worker inference thread.
4. View the clean, real-time MJPEG stream under the **Live Feed** view.

### 3. Setting Up Intrusion Zones
1. Open the **Zone Editor** page (`/zone-editor`).
2. Select your active camera.
3. Click on the camera canvas to define polygon vertices outlining your sensitive boundary (e.g. cash register, doorway, or restricted perimeter).
4. Save the zone. Any person stepping inside this polygon triggers an immediate trespass alert.

### 4. Registering Known Faces
1. Go to **Persons** (`/persons`).
2. Enter the individual's full name and upload one or more clear front-facing portrait photos.
3. The system extracts 512-dimensional vector embeddings and marks them as **Known**. When this person appears on any camera feed, they are recognized and logged as authorized.

### 5. Managing Unknown Persons
1. When an unrecognized individual appears on camera, they are assigned a unique tracking identity (e.g. `Unknown-001`).
2. Open **Unknown Persons** (`/unknown-persons`) to view facial crops, sighting timestamps, and camera locations.
3. Click **Promote to Known** to convert an unknown individual into a registered identity directly from the dashboard.

### 6. Alerts & Notifications
1. View critical incidents under the **Alerts** page (`/alerts`).
2. Click **Test Telegram Alert** or **Test WhatsApp Alert** in the header to confirm notifications are successfully reaching your phone.

---

## 🔌 API Endpoints Overview

FastAPI automatically generates interactive OpenAPI documentation at **`http://localhost:8000/docs`**.

### Key Endpoints

| Category | Method | Endpoint | Description |
|---|---|---|---|
| **Authentication** | `POST` | `/auth/login` | Authenticate user, returns JWT bearer token |
| | `GET` | `/auth/me` | Fetch authenticated user profile & role |
| **Cameras** | `GET` | `/camera/list` | List all registered camera sources |
| | `POST` | `/camera/add` | Register a new camera stream |
| | `POST` | `/camera/start` | Start inference and streaming thread |
| | `POST` | `/camera/stop` | Stop inference thread |
| **Live Video** | `GET` | `/stream/video_feed/{camera_id}` | Live MJPEG video stream |
| **Known Faces** | `POST` | `/faces/register-face` | Register known person with face photos |
| | `GET` | `/faces/known-faces` | List all registered known identities |
| | `DELETE` | `/faces/known-faces/{id}` | Delete a registered person |
| **Unknowns** | `GET` | `/unknown-persons` | List clustered unknown identities |
| | `POST` | `/unknown-persons/{id}/convert-to-known` | Promote unknown person to known |
| **Zones** | `GET` | `/zones/{camera_id}` | Fetch polygon intrusion zone |
| | `POST` | `/zones` | Create or update polygon intrusion zone |
| **Alerts & Events**| `GET` | `/events` | Paginated security event feed |
| | `GET` | `/alerts` | High-priority threats (weapons, trespass) |
| **Notifications** | `GET` | `/telegram/status` | Check Telegram bot configuration |
| | `POST` | `/send-telegram` | Dispatch test message to Telegram |
| | `POST` | `/send-whatsapp` | Dispatch test message to WhatsApp |
| **System** | `GET` | `/health` | Live status of DB, Redis, and workers |
| | `GET` | `/statistics` | Aggregated threat and detection counts |
| **User Mgmt** | `GET` | `/users` | List users *(Admin only)* |
| | `POST` | `/users` | Create user account *(Admin only)* |

---

## ❓ Troubleshooting

### 1. Port Already in Use (8000, 5173, 5432, 6379)
- **Symptom:** `Error: listen EADDRINUSE: address already in use` or `[Errno 10048]`.
- **Solution:** Run `run_all.py` or `start.bat`, which automatically cleans up stale processes on ports `8000` and `5173`. To manually kill listening processes on Windows:
  ```powershell
  # Find PID for port 8000
  netstat -ano | findstr :8000
  taskkill /F /PID <PID>
  ```

### 2. Camera Not Detected / Blank Video Feed
- **Symptom:** Stream fails to connect or logs `Unable to open camera source`.
- **Solution:**
  - On Windows, standard webcams sometimes require DirectShow backend syntax: add the camera with source `cv2.CAP_DSHOW + 0`.
  - For RTSP cameras, verify the stream is reachable with VLC Media Player (`Media -> Open Network Stream`).
  - See [`CAMERA_SOURCES.md`](./CAMERA_SOURCES.md) for detailed camera troubleshooting and public test streams.

### 3. Missing Modules or NumPy Conflict
- **Symptom:** `ImportError: cannot import name '...' from 'numpy'`.
- **Solution:** Ensure you are in your activated virtual environment and have installed the exact requirements. NumPy must remain `<2.0.0`:
  ```bash
  pip install "numpy>=1.24.3,<2.0.0"
  ```

### 4. Docker / Database Connection Refused
- **Symptom:** `psycopg2.OperationalError: connection to server at "localhost", port 5432 failed`.
- **Solution:** Ensure Docker Desktop is running and containers are healthy:
  ```bash
  docker compose ps
  docker compose up postgres redis -d
  ```

### 5. Telegram / WhatsApp Alerts "Disabled" or "Skipped"
- **Symptom:** Startup log displays `Telegram=Disabled` or `WhatsApp=Disabled`.
- **Solution:**
  - Check your `.env` file. Ensure `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set to real values (placeholder tokens containing `123456` or `your_` are deliberately ignored as safety filters).
  - Restart the backend so Python reloads the new `.env` settings.

---

## ⚠️ Important Notes

* **Excluded Files**: In accordance with security best practices, the following files and folders are strictly excluded from the Git repository:
  - Local configuration files (`.env`, `.env.local`).
  - Local database files and SQL dumps (`*.sql`, `*.db`).
  - Video recordings, CCTV snapshots, and face crops (`data/snapshots/`, `backend/data/`).
  - Heavy ML model checkpoints (`*.pt`, `*.onnx`) and virtual environments.
* **Environment Setup**: Every user must create their own `.env` from `.env.example` with valid credentials before starting the system.

---

## 👩‍💻 Author & License

- **Author**: Alishba ([@alishbakhan1223](https://github.com/alishbakhan1223))
- **Repository**: [https://github.com/alishbakhan1223/aiproject](https://github.com/alishbakhan1223/aiproject)
- **License**: MIT License. Feel free to use, modify, and distribute for educational and commercial projects.
