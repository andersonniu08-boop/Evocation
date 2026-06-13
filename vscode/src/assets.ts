/**
 * MemoryDog asset paths and constants.
 *
 * Centralizes asset references for the VS Code extension.
 * All paths are relative to the extension root (vscode/).
 */

/** Dog mascot sprite sheet. */
export const DOG_SPRITE_SHEET = "assets/dog/memorydog_spritesheet.png";

/** Activity Bar icon. */
export const DOG_ICON = "assets/dog/idle.png";

/** Dog sprite sheet grid layout. */
export const SPRITE = {
  /** Full sheet dimensions (px). */
  sheetWidth: 2124,
  sheetHeight: 2016,
  /** Individual frame dimensions (px). */
  frameWidth: 531,
  frameHeight: 1008,
  /** Grid layout. */
  columns: 4,
  rows: 2,
} as const;

/** Animation state → (column, row) mapping. */
export const DOG_STATES: Record<string, { col: number; row: number }> = {
  idle:     { col: 0, row: 0 },
  thinking: { col: 1, row: 0 },
  sniffing: { col: 2, row: 0 },
  running:  { col: 3, row: 0 },
  success:  { col: 0, row: 1 },
  error:    { col: 1, row: 1 },
  sleeping: { col: 2, row: 1 },
  startup:  { col: 3, row: 1 },
};

/** Recommended frame durations (ms). */
export const FRAME_DURATIONS: Record<string, number> = {
  idle:     900,
  thinking: 500,
  sniffing: 400,
  running:  250,
  success:  700,
  error:    700,
  sleeping: 1800,
  startup:  500,
};
