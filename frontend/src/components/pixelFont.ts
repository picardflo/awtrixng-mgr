/**
 * Matrix font, 5 pixels tall, variable width.
 *
 * AWTRIX states that "the font does not have a fixed size and I uses less space
 * than W", which changes the moment text starts scrolling. The preview must
 * therefore reproduce a variable width, or it would lie about overflow.
 *
 * Glyphs are written out row by row — readable and editable — then compiled
 * once into column masks.
 *
 * The firmware uppercases text by default (the UPPERCASE setting), so we do the
 * same and define no lowercase glyphs.
 */

const GLYPHS: Record<string, string[]> = {
  " ": ["00", "00", "00", "00", "00"],

  "0": ["111", "101", "101", "101", "111"],
  "1": ["010", "110", "010", "010", "111"],
  "2": ["111", "001", "111", "100", "111"],
  "3": ["111", "001", "111", "001", "111"],
  "4": ["101", "101", "111", "001", "001"],
  "5": ["111", "100", "111", "001", "111"],
  "6": ["111", "100", "111", "101", "111"],
  "7": ["111", "001", "010", "010", "010"],
  "8": ["111", "101", "111", "101", "111"],
  "9": ["111", "101", "111", "001", "111"],

  A: ["010", "101", "111", "101", "101"],
  B: ["110", "101", "110", "101", "110"],
  C: ["011", "100", "100", "100", "011"],
  D: ["110", "101", "101", "101", "110"],
  E: ["111", "100", "110", "100", "111"],
  F: ["111", "100", "110", "100", "100"],
  G: ["011", "100", "101", "101", "011"],
  H: ["101", "101", "111", "101", "101"],
  I: ["1", "1", "1", "1", "1"],
  J: ["001", "001", "001", "101", "010"],
  K: ["101", "101", "110", "101", "101"],
  L: ["100", "100", "100", "100", "111"],
  M: ["10001", "11011", "10101", "10001", "10001"],
  N: ["101", "111", "111", "101", "101"],
  O: ["111", "101", "101", "101", "111"],
  P: ["110", "101", "110", "100", "100"],
  Q: ["111", "101", "101", "111", "001"],
  R: ["110", "101", "110", "101", "101"],
  S: ["011", "100", "010", "001", "110"],
  T: ["111", "010", "010", "010", "010"],
  U: ["101", "101", "101", "101", "111"],
  V: ["101", "101", "101", "101", "010"],
  W: ["10001", "10001", "10101", "11011", "10001"],
  X: ["101", "101", "010", "101", "101"],
  Y: ["101", "101", "010", "010", "010"],
  Z: ["111", "001", "010", "100", "111"],

  ":": ["0", "1", "0", "1", "0"],
  ".": ["0", "0", "0", "0", "1"],
  ",": ["0", "0", "0", "1", "1"],
  "-": ["000", "000", "111", "000", "000"],
  "+": ["000", "010", "111", "010", "000"],
  "=": ["000", "111", "000", "111", "000"],
  "/": ["001", "001", "010", "100", "100"],
  "\\": ["100", "100", "010", "001", "001"],
  "!": ["1", "1", "1", "0", "1"],
  "?": ["111", "001", "010", "000", "010"],
  "'": ["1", "1", "0", "0", "0"],
  "\"": ["101", "101", "000", "000", "000"],
  "°": ["111", "101", "111", "000", "000"],
  "%": ["101", "001", "010", "100", "101"],
  "(": ["01", "10", "10", "10", "01"],
  ")": ["10", "01", "01", "01", "10"],
  "<": ["001", "010", "100", "010", "001"],
  ">": ["100", "010", "001", "010", "100"],
  "*": ["101", "010", "111", "010", "101"],
  "#": ["01010", "11111", "01010", "11111", "01010"],
  "&": ["110", "100", "111", "101", "111"],
  "$": ["011", "110", "011", "110", "010"],
  "@": ["01110", "10001", "10111", "10000", "01110"],
  "_": ["000", "000", "000", "000", "111"],
  "|": ["1", "1", "1", "1", "1"],
};

export const GLYPH_HEIGHT = 5;
/** Blank column inserted between two characters. */
export const LETTER_SPACING = 1;

/** A compiled glyph: one value per column, bit i = row i. */
type Glyph = number[];

const COMPILED: Record<string, Glyph> = {};
for (const [char, rows] of Object.entries(GLYPHS)) {
  const width = rows[0].length;
  const columns: Glyph = [];
  for (let x = 0; x < width; x += 1) {
    let mask = 0;
    for (let y = 0; y < GLYPH_HEIGHT; y += 1) {
      if (rows[y][x] === "1") mask |= 1 << y;
    }
    columns.push(mask);
  }
  COMPILED[char] = columns;
}

const FALLBACK = COMPILED["?"];

function glyphFor(char: string): Glyph {
  return COMPILED[char.toUpperCase()] ?? FALLBACK;
}

/**
 * Rasterise a string into pixel columns.
 * Returns an array of masks: `columns[x] & (1 << y)` gives the pixel.
 */
export function rasterize(text: string): number[] {
  const columns: number[] = [];
  for (const char of text) {
    if (columns.length > 0) {
      for (let i = 0; i < LETTER_SPACING; i += 1) columns.push(0);
    }
    columns.push(...glyphFor(char));
  }
  return columns;
}

export function textWidth(text: string): number {
  return rasterize(text).length;
}
