# Instagram Group Chat Export — Structural Schema Report

> **Scope**: Schema/structure only. Zero message content quoted. Zero real names.

---

## 1. Group Chat Discovery

### All group chats found (5 folders, ≥3 participants)

| Folder Name | Participants | Notes |
|---|---|---|
| `SemperFi` | 3 | Renamed copy of `sempeghpghaii_866770079517755`; split into `message_1.json` + `message_2.json` |
| `sempeghpghaii_866770079517755` | 3 | Original folder; single `message_1.json`; identical data to SemperFi (minus split) |
| `unarebi_2003518226899102` | 9 | Single `message_1.json` |
| `gamotserili_1309719330782416` | 7 | Single `message_1.json` |
| `lukasali_marttmarimanagadze_and11others_629538656852657` | 15 | Single `message_1.json`; folder name encodes "and 11 others" pattern |

> **Detecting groups programmatically**: Load `message_1.json` from each folder and check `len(participants) >= 3`. Do NOT rely on folder naming patterns — only the participants array is authoritative.

### Duplicate folder pair

`SemperFi/` and `sempeghpghaii_866770079517755/` contain identical data (same `participants`, `title`, `thread_path`, `joinable_mode`). The `SemperFi/` variant was split into 2 message files (`message_1.json` + `message_2.json`), while the original has only `message_1.json`. A `combined_message.json` exists in both, merging all messages into one file.

---

## 2. JSON Schema Differences

### Top-level fields

| Field | 1v1 Chat | Group Chat | Notes |
|---|---|---|---|
| `participants` | `[{name}, {name}]` (2) | `[{name}, {name}, ...]` (3+) | Same structure, different count |
| `messages` | array | array | Same structure |
| `title` | equals participant name | **custom group name** (never equals any participant name) | See §4 |
| `is_still_participant` | `true` | `true` | Same |
| `thread_path` | `inbox/<username_or_id>` | `inbox/<username_or_id>` | Same pattern; **does NOT match folder name** in groups (e.g. `SemperFi/` has `thread_path: "inbox/sempeghpghaii_866770079517755"`) |
| `magic_words` | `[]` | `[]` | Same |
| **`joinable_mode`** | **absent / `null`** | **present with value** | **KEY DIFFERENCE** |

### `joinable_mode` structure (group-only field)

```json
"joinable_mode": {
    "mode": 2,
    "link": "https://ig.me/j/<invite_token>"
}
```

**Important**: `joinable_mode` is present in `message_1.json` and `message_2.json` files but **ABSENT from `combined_message.json`**. This means: if the analyzer reads `combined_message.json`, it will NOT see `joinable_mode`. If it reads individual `message_N.json` files, it WILL see it.

### Message-level fields

All three types (1v1, small groups, large groups) share these base keys:

| Key | Present in 1v1 | Present in Groups | Notes |
|---|---|---|---|
| `sender_name` | ✓ | ✓ | Same |
| `timestamp_ms` | ✓ | ✓ | Same |
| `content` | ✓ (string or `null`) | ✓ (string or `null`) | Same — `null` means media-only message |
| `is_geoblocked_for_viewer` | ✓ | ✓ | Same |
| `is_unsent_image_by_messenger_kid_parent` | ✓ | ✓ | Same |
| `reactions` | ✓ | ✓ | **Present in BOTH** (1v1 also has reactions) |
| `photos` | ✓ | ✓ | Same |
| `videos` | ✓ | ✓ | Same |
| `audio_files` | ✓ | ✓ | Same |
| `share` | ✓ | ✓ | Same |

**Group-only message key**:

| Key | Present in 1v1 | Present in Groups | Notes |
|---|---|---|---|
| `call_duration` | ✗ | ✓ (sometimes) | Integer (e.g. `0`). Appears on "missed video chat" system messages. |

### `photos` sub-structure (same in 1v1 and groups)

```json
"photos": [
    {
        "uri": "...",
        "creation_timestamp": "..."
    }
]
```

### `share` sub-structure (same in 1v1 and groups)

```json
"share": {
    "link": "...",
    "share_text": "...",
    "original_content_owner": "..."
}
```

### `reactions` sub-structure (same in 1v1 and groups)

```json
"reactions": [
    {"reaction": "<emoji>", "actor": "<sender_name>"}
]
```

---

## 3. System / Notification Messages in Groups

### Detected system message pattern

Only **one type** of system/notification message was found across all group chats:

```json
{
    "sender_name": "<NAME>",
    "timestamp_ms": <number>,
    "content": "<NAME> added <NAME> to the group.",
    "is_geoblocked_for_viewer": false,
    "is_unsent_image_by_messenger_kid_parent": false
}
```

**Pattern templates** (for filtering):

| Pattern | Example |
|---|---|
| `<NAME> added <NAME> to the group.` | "X added Y to the group." |
| *(future patterns)* | `left the group`, `removed <NAME> from the group`, `named the group "<title>"`, `changed the group icon`, `created a poll` |

**Key structural insight**: System messages use the same schema as regular messages — there is **no separate `type` field**, no `system_type`, no `message_type`. They are indistinguishable from text messages by structure alone. The only way to identify them is by **string pattern matching on `content`**.

### `content = null` messages (media-only)

Both 1v1 and groups use `null` for `content` when the message contains media (photos, audio, video) instead of text. These are **NOT system messages** — they're user-sent media. In groups, these make up ~2-5% of messages. They carry extra keys like `photos: [...]`, `audio_files: [...]`, `videos: [...]`, `share: {...}`, and/or `reactions: [...]`.

---

## 4. Structural Dynamics for Metric Design

### Active senders vs. listed participants

| Group | Participants | Active Senders | Inactive |
|---|---|---|---|
| `SemperFi` | 3 | 3 | 0 |
| `unarebi_2003518226899102` | 9 | 9 | 0 |
| `gamotserili_1309719330782416` | 7 | 7 | 0 |
| `lukasali_marttmarimanagadze_and11others` | 15 | 13 | **2** |

> In the largest group, 2 of 15 participants never sent any message with content.

### Message share distribution (rough shape)

| Group | Top sender % | Second % | Third % | Distribution shape |
|---|---|---|---|---|
| `SemperFi` (3 members) | ~42% | ~42% | ~16% | **Bipolar** — two equal heavy users, one lighter |
| `unarebi` (9 members) | ~22% | ~21% | ~20% | **Flat/even** — top 3 each ~20%, long tail |
| `gamotserili` (7 members) | ~32% | ~25% | ~23% | **Moderate skew** — top 3 dominate |
| `and11others` (15 members) | ~40% | ~20% | ~16% | **Heavy skew** — top 3 send ~76% |

> No single universal shape. Group size does not predict distribution flatness.

### Reactions in groups

- **Prevalence**: 27–41% of messages carry at least one reaction
- **Multi-reaction messages exist**: Some messages have 2–4 reactions from different participants
- **Reaction types seen**: heart, 😂, 👍, 😎, 😓, 🤔, 😡, 😠 (typical emoji set)
- **Reactions are present in 1v1 too** — not a group-only feature

### Group name (`title`) behavior

- In 1v1 chats: `title` **always equals one participant's display name**
- In group chats: `title` is a **custom group name** — it **never equals any participant's name**
- The folder name does NOT necessarily match the `title`
- `thread_path` does NOT necessarily match the folder name either

---

## 5. Things That Break a 1v1-Only Analyzer

### Critical

1. **`joinable_mode` field**: Present in group `message_N.json` files, absent from `combined_message.json`. If the analyzer assumes `joinable_mode` is always null/missing, it will silently miss group chats. If it tries to access `joinable_mode.mode`, it will crash on 1v1 chats.

2. **`call_duration` field**: Present in some group messages (missed video chat notifications), absent from 1v1. Will cause KeyError or type errors if the analyzer assumes it doesn't exist.

3. **Folder name ≠ `thread_path`**: In groups, the folder name may be a renamed copy (`SemperFi`) while `thread_path` references the original ID (`sempeghpghaii_866770079517755`). If the analyzer uses folder names as identifiers, it will misidentify or duplicate group chats.

4. **`title` never matches participant names in groups**: A 1v1-only analyzer might assume `title == participants[0].name` to identify the other party. This breaks in groups.

5. **`combined_message.json` lacks `joinable_mode`**: If the analyzer prefers `combined_message.json` over individual files, it will lose the group-detection signal. Must check individual `message_1.json` for `joinable_mode`.

### Important

6. **Duplicate folders**: `SemperFi/` and `sempeghpghaii_866770079517755/` are duplicates. The analyzer must deduplicate by `thread_path` or by comparing participant lists, not by folder name.

7. **System messages have no type field**: The analyzer cannot use `msg["type"] == "system"` to filter. Must pattern-match on `content` string. The only confirmed pattern is `<NAME> added <NAME> to the group.`

8. **`content = null` is NOT system messages**: It represents media-only messages (photos, audio, video, share). The analyzer must distinguish these from system messages — both lack text content but have different structures.

9. **Reactions on `content = null` messages**: Media-only messages can have reactions, so checking `msg.get("reactions")` without also checking `msg.get("content")` will overcount reacted messages.

10. **Variable message file counts**: Some group chats have 1 file (`message_1.json`), some have 2+ (`message_1.json` + `message_2.json`). The analyzer must glob for all `message_*.json` files per folder.

### Minor / Edge Cases

11. **`is_still_participant` is always `true`** in all observed chats — not useful as a filter.

12. **`magic_words` is always `[]`** in all observed chats — not useful.

13. **Participant array order**: Not guaranteed to be alphabetical or by join date. Do not assume position-based ordering.

14. **Messages are sorted descending by timestamp** within each file — the analyzer should account for this when computing time-series metrics.

---

## Summary Table: 1v1 vs Group Checklist for Analyzer

```
Analyzer must handle:
├── Participants array: 2 vs 3+ (detect with len >= 3)
├── joinable_mode: null/absent (1v1) vs {mode, link} (groups) — ONLY in message_N.json
├── call_duration: absent (1v1) vs int (groups) — on missed-call messages
├── title: == participant name (1v1) vs custom name (groups)
├── thread_path: matches folder name (1v1) vs may NOT match (groups)
├── System messages: no type field — pattern-match content string
├── content=null: textless user messages (media), NOT system — check for photos/audio/videos/share/reactions keys
├── Reactions: present in BOTH 1v1 and groups
├── Multiple message files per folder: must glob message_*.json
├── Duplicate folders: deduplicate by thread_path or participant set
└── combined_message.json: may lack joinable_mode — don't rely on it for group detection
```
