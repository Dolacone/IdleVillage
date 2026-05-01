---
title: Deployment
doc_type: operations
last_reviewed: 2026-05-01
source_paths:
  - Dockerfile
  - fly.toml
  - data
---

# Deployment

IdleVillage runs as a single Docker container deployed to [Fly.io](https://fly.io).

## Files

| File | Purpose |
| :--- | :--- |
| `Dockerfile` | Builds the production container image. Excludes `tests/` to keep the image small. |
| `fly.toml` | Fly.io app configuration. App name: `idle-village`, region: `nrt` (Tokyo), 256 MB shared VM. |
| `data/` | Persistent volume mount point. Contains `village.db` (SQLite database). Mounted at `/app/data` in the container. |

## Local Setup

1. Copy `.env.example` and fill in `DISCORD_TOKEN`.
2. Install dependencies: `pip install -r src/requirements.txt`.
3. Run: `python src/main.py`.

## Production Deploy

```sh
fly deploy
```

The `data/` volume (`idle_village`) is mounted at `/app/data` and persists across deploys. Never delete the volume while a v2 database exists.
