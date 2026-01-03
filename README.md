# AGI (Ask anything)

Minimal Flask app that routes prompts to a tool-backed agent to do various tasks based on prompt of using using various tools

image generation, video generation, audio generation, google search, avatar generation, google maps,video editing, ad generation

with a  planning agent.

## What is included
- Web UI at `/` with an agent prompt form.
- Tools page at `/tools`.
- API endpoints for agent streaming, image/video generation, merging videos, and
  recent prompt storage (Redis-backed).

## Quick start
1) Create a virtualenv and install dependencies:
```
python -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```
2) Copy env example and fill what you need:
```
cp env.example .env
```
3) Run the server:
```
python app.py
```
App listens on `http://localhost:7171` by default. Set `PORT` to change it.

## Redis (recent prompts)
If `REDIS_URL` is set, prompts sent to `/api/agent` are stored in a Redis list.
Fetch them with:
```
GET /api/recent-prompts
```

## API overview
- `POST /api/agent` (SSE stream) - main agent runner
- `POST /api/generate-image` - image generation
- `POST /api/generate-video` - video generation
- `POST /api/merge-videos` - merge two uploaded videos
- `GET /api/recent-prompts` - recent prompts (requires Redis)
- `GET /files?path=...` - serve files under project root

## Configuration
See `env.example` for all supported environment variables.
