# Evocation Mascot — Sprite Sheet

## Source

Artist-provided sprite sheet, added to the repository 2026-06-12.

## Sprite Sheet

| Property | Value |
|----------|-------|
| File | `evocation_spritesheet.png` |
| Format | PNG, RGBA |
| Dimensions | 2124 × 2016 px |
| Grid | 4 columns × 2 rows (8 frames) |
| Frame size | 531 × 1008 px |

## Animation States

Frames are arranged left-to-right, top-to-bottom in a 4×2 grid:

| Frame | Row | Col | State | Description |
|-------|-----|-----|-------|-------------|
| 0 | 0 | 0 | **Idle** | Default resting pose, gentle breathing |
| 1 | 0 | 1 | **Thinking** | Head tilted, processing / LLM call in-flight |
| 2 | 0 | 2 | **Sniffing Memories** | Nose to ground, searching memory store |
| 3 | 0 | 3 | **Running Tools** | Mid-stride, executing a tool |
| 4 | 1 | 0 | **Success** | Tail wagging, happy — tool succeeded |
| 5 | 1 | 1 | **Error** | Ears drooped — tool or API error |
| 6 | 1 | 2 | **Sleeping** | Curled up, bridge not running |
| 7 | 1 | 3 | **Startup** | Stretching / waking — bridge initializing |

### Frame Timing Recommendations

| State | Frame duration | Loop |
|-------|---------------|------|
| Idle | 800–1200 ms | Ping-pong (frames 0↔0 with subtle transform) |
| Thinking | 400–600 ms | Loop (can use CSS transform on a single frame) |
| Sniffing Memories | 300–500 ms | Loop |
| Running Tools | 200–300 ms | Loop |
| Success | 600–800 ms | Play once, return to Idle |
| Error | 600–800 ms | Play once, return to Idle |
| Sleeping | 1500–2000 ms | Loop (gentle pulse) |
| Startup | 400–600 ms | Play once, then Idle |

## Intended Usage

The sprite sheet is the canonical art asset for the Evocation mascot, used across:

- **VS Code Extension** — rendered in the Mascot panel (`dog.html`) via CSS `background-position` sprite animation or `<canvas>`
- **CLI / TUI** — optional terminal rendering via kitty/wezterm image protocol or sixel
- **Documentation** — static frames extracted for README, website, and marketing

### VS Code Webview Loading

The sprite sheet must be accessible within the extension's webview context. The webview loads resources relative to the extension root (`vscode/`). Copy this file into `vscode/assets/dog/` alongside the Activity Bar icon so it's packaged with the extension.

### Frame Extraction (CSS Sprites)

```css
.dog-sprite {
  width: 531px;
  height: 1008px;
  background-image: url('evocation_spritesheet.png');
  background-size: 2124px 2016px;  /* full sheet */
}
.dog-idle     { background-position: 0 0; }
.dog-thinking { background-position: -531px 0; }
.dog-sniffing { background-position: -1062px 0; }
.dog-running  { background-position: -1593px 0; }
.dog-success  { background-position: 0 -1008px; }
.dog-error    { background-position: -531px -1008px; }
.dog-sleeping { background-position: -1062px -1008px; }
.dog-startup  { background-position: -1593px -1008px; }
```

## VS Code Integration

The sprite sheet is rendered in the **Mascot** sidebar panel via:

- **`vscode/src/assets.ts`** — canonical constants (SPRITE, DOG_STATES, FRAME_DURATIONS)
- **`vscode/src/webview/dog.html`** — webview with `SpriteRenderer`, `DogStateMachine`, and `DogWidget` classes
- **`vscode/src/extension.ts`** — `DogViewProvider` sends `sprite_config` + `tick` messages (state + status)

The DogWidget displays the sprite as the visual centerpiece alongside a dashboard showing workspace, memory count, instincts, provider, and model.

### Architecture

```
extension.ts (DogViewProvider)
  │  sends: sprite_config, tick { state, status }
  ▼
dog.html (DogWidget)
  ├── SpriteRenderer    — CSS background-position per frame
  ├── DogStateMachine   — valid transitions, one-shot auto-return
  └── Dashboard         — workspace / memories / instincts / provider / model
```

### State Transitions

| State | Trigger | Duration | Auto-return |
|-------|---------|----------|-------------|
| startup | Extension activation | 500 ms | → idle |
| idle | Waiting for input | loop | — |
| thinking | LLM reasoning | loop | — |
| sniffing | Memory/context retrieval | loop | — |
| running | Tool execution | loop | — |
| success | Request completed | 700 ms | → idle |
| error | Provider/tool failure | 700 ms | → idle |
| sleeping | Bridge not running / inactivity | loop | — |

## See Also

- `vscode/src/webview/dog.html` — DogWidget implementation (SpriteRenderer + DogStateMachine)
- `vscode/src/extension.ts` — DogViewProvider and dog state management
- `vscode/src/assets.ts` — Sprite constants
- `assets/screenshots/` — application screenshots
- `assets/icons/` — icon assets
