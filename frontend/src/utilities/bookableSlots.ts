import type { TimeInterval } from "./api";

const SLOT_MS = 15 * 60_000;

function floorToSlot(ms: number): number {
  return Math.floor(ms / SLOT_MS) * SLOT_MS;
}

function toUtcStamp(ms: number): string {
  return new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
}

export function bookableSlots(
  available: TimeInterval[],
  durationMinutes: number,
  nowMs = Date.now(),
  limit = 12,
): TimeInterval[] {
  const durationMs = durationMinutes * 60_000;
  const slots: TimeInterval[] = [];
  const nowAligned = floorToSlot(nowMs);
  for (const gap of available) {
    let cursor = floorToSlot(Date.parse(gap.start));
    if (cursor < Date.parse(gap.start)) {
      cursor += SLOT_MS;
    }
    const end = Date.parse(gap.end);
    while (cursor + durationMs <= end) {
      if (cursor >= nowAligned) {
        slots.push({
          start: toUtcStamp(cursor),
          end: toUtcStamp(cursor + durationMs),
        });
        if (slots.length >= limit) {
          return slots;
        }
      }
      cursor += durationMs;
    }
  }
  return slots;
}

export function formatUtcRange(start: string, end: string): string {
  const left = start.replace("T", " ").replace(/\.\d+/, "").replace("Z", "");
  const right = end.replace("T", " ").replace(/\.\d+/, "").replace("Z", "");
  return `${left} – ${right} UTC`;
}
