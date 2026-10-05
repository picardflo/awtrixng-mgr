/**
 * Ready-made melodies, in the old Nokia ringtone format the firmware speaks.
 *
 * Written rather than borrowed: the collections one finds online are full
 * phone ringtones of twenty or thirty seconds, which is not what a reminder
 * wants. These are short, and pitched high — an eight-bit buzzer has neither
 * bass nor nuance, so what carries across a room is treble and brevity.
 */
export interface Melody {
  /** i18n key suffix, under `melody.` */
  id: string;
  rtttl: string;
}

export const MELODIES: readonly Melody[] = [
  { id: "twoBeeps", rtttl: "bip:d=16,o=6,b=140:c,p,c" },
  { id: "rising", rtttl: "rappel:d=16,o=6,b=120:c,e,g" },
  { id: "chime", rtttl: "carillon:d=8,o=6,b=100:e,c,d,8p,g" },
  { id: "insistent", rtttl: "alerte:d=16,o=7,b=160:c,p,c,p,c,p,c" },
  { id: "pillbox", rtttl: "pilule:d=8,o=6,b=120:c,e,g,e,4c" },
  { id: "falling", rtttl: "fin:d=8,o=6,b=100:g,e,c,4p,4c" },
] as const;

/** Grammar check, enough to catch a typo before the clock swallows it silently.
 *
 *  Deliberately not a full parser: the firmware is the authority on what it
 *  can play, and refusing something it would have accepted would be worse than
 *  letting it through.
 */
export function looksLikeRtttl(value: string): boolean {
  const parts = value.split(":");
  if (parts.length !== 3) return false;
  const [name, settings, notes] = parts;
  if (name.trim() === "") return false;
  if (!/^\s*[dob]\s*=\s*\d+\s*(,\s*[dob]\s*=\s*\d+\s*)*$/i.test(settings)) return false;
  return notes
    .split(",")
    .every((note) => /^\s*(1|2|4|8|16|32)?[a-gp]#?\.?[4-8]?\.?\s*$/i.test(note));
}
