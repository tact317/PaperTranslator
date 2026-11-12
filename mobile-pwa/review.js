/* Simple deterministic per-direction spaced repetition; no cloud dependency. */
export const DIRECTIONS = ['en-ja', 'ja-en'];
export function normalizedReview(input, cardId, direction) {
  if (!DIRECTIONS.includes(direction)) throw new Error('Invalid review direction');
  const r = input && typeof input === 'object' ? input : {};
  const finite = (x, fallback) => typeof x === 'number' && Number.isFinite(x) ? x : fallback;
  return {
    key: cardId + ':' + direction,
    cardId, direction,
    repetitions: Math.max(0, Math.min(5000, Math.floor(finite(r.repetitions, 0)))),
    intervalDays: Math.max(0, Math.min(36500, finite(r.intervalDays, 0))),
    ease: Math.max(1.3, Math.min(3, finite(r.ease, 2.5))),
    known: Math.max(0, Math.floor(finite(r.known, 0))),
    again: Math.max(0, Math.floor(finite(r.again, 0))),
    dueAt: Math.max(0, finite(r.dueAt, 0)),
    lastReviewedAt: Math.max(0, finite(r.lastReviewedAt, 0)),
  };
}
export function reviewNext(previous, cardId, direction, remembered, now = Date.now()) {
  const r = normalizedReview(previous, cardId, direction);
  if (remembered) {
    r.intervalDays = r.repetitions === 0 ? 1 : (r.repetitions === 1 ? 3 : Math.min(36500, Math.round(r.intervalDays * r.ease)));
    r.repetitions += 1;
    r.ease = Math.min(3, r.ease + 0.05);
    r.known += 1;
    r.dueAt = now + r.intervalDays * 86400000;
  } else {
    r.repetitions = 0;
    r.intervalDays = 0;
    r.ease = Math.max(1.3, r.ease - 0.2);
    r.again += 1;
    r.dueAt = now + 10 * 60000;
  }
  r.lastReviewedAt = now;
  return r;
}
export function due(card, reviews, direction, now = Date.now()) {
  const r = reviews.get(card.id + ':' + direction);
  return !r || !r.dueAt || r.dueAt <= now;
}
