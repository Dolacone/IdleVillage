# Module: db-schema

v2 fresh restart database schema. This file is the SSOT for SQLite tables, columns, indexes, and initialization rows only.

Gameplay rules live in the functional module files listed in `preview/README.md`.

## Conventions

- SQLite is the primary database.
- v2 preview is a fresh DB and does not migrate or preserve v1 tables.
- Time fields use UTC ISO-8601 text.
- Boolean fields use integers: `0` = false, `1` = true.
- Enum values are stored as text and validated by application code.
- The app supports the single Discord guild specified by `DISCORD_GUILD_ID`.

## Tables

### village_state

Singleton global metadata row.

```sql
CREATE TABLE village_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  dashboard_channel_id TEXT,
  dashboard_message_id TEXT,
  announcement_channel_id TEXT
);
```

Initial row:

```text
id = 1
dashboard_channel_id = null
dashboard_message_id = null
announcement_channel_id = ANNOUNCEMENT_CHANNEL_ID if provided
```

### stage_state

Singleton current stage row.

```sql
CREATE TABLE stage_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  stages_cleared INTEGER NOT NULL DEFAULT 0,
  current_stage_index INTEGER NOT NULL DEFAULT 0,
  current_stage_type TEXT NOT NULL,
  current_stage_progress INTEGER NOT NULL DEFAULT 0,
  current_stage_target INTEGER NOT NULL,
  stage_started_at TEXT NOT NULL,
  overtime_notified INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);
```

Initial row:

```text
id = 1
stages_cleared = 0
current_stage_index = 0
current_stage_type = gathering
current_stage_progress = 0
current_stage_target = initial target from stage-manager
stage_started_at = current_time
overtime_notified = 0
```

### village_resources

Global shared village resources.

```sql
CREATE TABLE village_resources (
  resource_type TEXT PRIMARY KEY,
  amount INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);
```

Initial rows:

```text
food = 0
wood = 0
knowledge = 0
```

### buildings

Global building state.

```sql
CREATE TABLE buildings (
  building_type TEXT PRIMARY KEY,
  level INTEGER NOT NULL DEFAULT 0,
  xp_progress INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);
```

Initial rows:

```text
gathering_field: level = 0, xp_progress = 0
workshop: level = 0, xp_progress = 0
hunting_ground: level = 0, xp_progress = 0
research_lab: level = 0, xp_progress = 0
```

### players

Global player state keyed by Discord user ID.

```sql
CREATE TABLE players (
  user_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,

  action TEXT,
  action_target TEXT,
  completion_time TEXT,
  last_update_time TEXT,

  ap_full_time TEXT NOT NULL,

  materials_gathering INTEGER NOT NULL DEFAULT 0,
  materials_building INTEGER NOT NULL DEFAULT 0,
  materials_combat INTEGER NOT NULL DEFAULT 0,
  materials_research INTEGER NOT NULL DEFAULT 0,

  gear_gathering INTEGER NOT NULL DEFAULT 0,
  gear_building INTEGER NOT NULL DEFAULT 0,
  gear_combat INTEGER NOT NULL DEFAULT 0,
  gear_research INTEGER NOT NULL DEFAULT 0,

  pity_gathering INTEGER NOT NULL DEFAULT 0,
  pity_building INTEGER NOT NULL DEFAULT 0,
  pity_combat INTEGER NOT NULL DEFAULT 0,
  pity_research INTEGER NOT NULL DEFAULT 0
);
```

Initial player row:

```text
user_id = Discord user ID
created_at = current_time
updated_at = current_time
action = null
action_target = null
completion_time = null
last_update_time = null
ap_full_time = created_at + AP_CAP * AP_RECOVERY_MINUTES
materials_* = 0
gear_* = 0
pity_* = 0
```

### guild_installations

Single supported Discord guild record.

```sql
CREATE TABLE guild_installations (
  guild_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1
);
```

Initial row:

```text
guild_id = DISCORD_GUILD_ID
is_active = 1
```

## Indexes

```sql
CREATE INDEX idx_players_completion_time
ON players (completion_time);

CREATE INDEX idx_players_action
ON players (action);
```
