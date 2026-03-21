# AGI (Ask anything)

Minimal Flask app that routes prompts to a tool-backed agent to do various tasks based on prompt of using using various tools

image generation, video generation, audio generation, google search, avatar generation, google maps,video editing, ad generation

with a planning agent.

Planner configuration:
- set `OPENAI_API_KEY` to enable OpenAI-based planning/router decisions
- optional: set `OPENAI_PLANNER_MODEL` to override the default planner model

Gmail utilities now include:
- reading today's emails
- searching emails by topic
- listing emails related to a search term
- pulling image/PDF bill attachments from matching emails

## Bill Saver V1
- Backend API stays in Flask.
- New SvelteKit frontend lives in `frontend/`.
- Flow:
  - connect Gmail
  - search by business/provider string
  - scan matching emails and bill attachments
  - dedupe and upload missing files/text to Hyperspell memories
  - run category-specific research
    - Exa for product price comparison
    - Google search for utility/service comparison
    - browser fallback for rides/property/product when needed
  - save research to Hyperspell
  - render savings comparison table

### New bill-saver endpoints
- `GET /api/gmail/status`
- `GET /api/bill-saver/memory-status?business_query=...`
- `POST /api/bill-saver/run`

### Required config for Bill Saver
- `HYPERSPELL_API_KEY`
- `GOOGLE_API_KEY`
- `EXA_API_KEY` for product search
- Gmail OAuth credentials or refresh token
- optional: `OPENAI_API_KEY` for image OCR fallback

### Frontend
```
cd frontend
npm install
npm run dev
```

Set `PUBLIC_API_BASE_URL=http://localhost:7171` when running the frontend if needed.

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
# SavingClaw
