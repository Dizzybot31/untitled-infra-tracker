# Roadmap — parked ideas

Things deliberately not being built yet, with enough context to pick them up cold.
Nothing here is a commitment. Order is rough priority, not schedule.

---

## 1. Make it local first: "what is being built near me"

**Status:** parked on purpose, 2026-09-12. Pick up once the data foundations are
in place (a second real source, and geography good enough to trust).

### The idea, in the owner's framing

> If I share this online people will talk about things and then things will slip
> away. Instead of overwhelming the user with all the data points, we should ask
> for their location and show the projects closest to them, so they actually care
> about the things near them. As progressive disclosure we can give them stats on
> what other projects across India are pending. Maybe this would allow them to
> feel more personal about the data, and perhaps question their local
> constituency on why the project is being delayed.

### Why it is the right instinct

The product's current failure mode is exactly the one described: a national map
of 707 things produces a reaction ("huh, a lot is late") and then nothing. A
single relevant fact about the road someone drives every week produces a
different reaction, and possibly an action.

It also fits what the data can honestly support. The tracker is weakest as a
national statistical picture — 98% of it is highways, so any "India is X% late"
claim is really "highways are X% late". It is strongest at the level of a single
project, where every figure carries a source and a date. A local-first view plays
to that strength instead of fighting it.

### What we already have that makes this cheaper than it looks

**NHAI publishes the parliamentary constituency for every road project.**
Verified live on 2026-09-12 via the `parliaments_name` field on
`NHAI:adv_upc_wise_alignments_wfs_layers`. Real values:

```
6L of Perole to Taliparamba          -> KASARAGOD | KANNUR
4L of Handia - Rajatalab Section     -> VARANASI | BHADOHI | MIRZAPUR
Kiratpur - Kurali km 28.60-73.20     -> ANANDPUR SAHIB
```

That is the "question your MP" feature sitting in a field we do not currently
fetch. Adding it is one string in the adapter's `propertyName` list plus a
canonical field. It turns a vague aspiration into a join.

`district_name` is already fetched and is 96% populated.

### What actually has to be solved first

1. **Coverage, which is the real blocker.** Only ~a third of drawn projects have
   a precise location, and 98% are roads. "Near me" would today return either
   nothing or a list of highways. Fixing this is the foundation work — it is why
   this is parked behind a second data source, not in front of it.

2. **"Nothing near me" is the common case, not the edge case.** With 707 drawn
   projects across 3.3 million km², most users' 25 km radius will be empty. The
   design has to make an empty local view feel like information ("no monitored
   central-sector project within 25 km — the nearest is 60 km away, here it is"),
   not like a broken page. Get this wrong and the feature is worse than no
   feature.

3. **Do not reach for the browser geolocation prompt first.** It is a permission
   dialog before any value has been demonstrated, it is frequently denied, and it
   is useless on desktop. Prefer: show the national view, offer a text box
   ("Varanasi", a PIN code, a constituency name), and offer precise location as a
   convenience *after* the user has seen what the page does. Geolocation should
   be the shortcut, never the gate.

4. **Location must never leave the browser.** The site is static with no backend,
   so this is easy to honour and worth stating plainly in the UI. Distance
   filtering happens client-side against already-downloaded data. No location in
   a URL, no analytics on it.

5. **Constituency boundaries are a licensing question.** Showing "projects in
   your constituency" by name is free (we would have the field). Drawing
   constituency *boundaries* means sourcing boundary polygons, which runs into
   the map/boundary constraints in `docs/LEGAL.md`. Prefer name-matching over
   polygons unless there is a clear reason.

6. **Tone.** "Ask your MP why this is late" is a short step from asserting that a
   named person is at fault for a delay whose cause the data does not state — the
   sources publish dates, not reasons. Whatever is built must stay on the side of
   *here is what the record says, and who represents this area*, and let the
   reader draw the conclusion. See the defamation note in `docs/LEGAL.md`.

### Sketch of the shape (not a design)

- National view stays the default and the shareable thing.
- One input: "Where do you live?" — text, with an optional "use my location".
- Local view: nearest N projects ordered by distance, each with its status, its
  source, and its constituency. Empty states handled as above.
- Progressive disclosure back outward: "12 projects within 50 km · 41 in Uttar
  Pradesh · 400 past due nationally" — local first, national as context.

### Why not now

The foundations are not done. Adding a location filter over data that is 98%
highways and a third precisely located would produce a feature that looks
personal while telling most users almost nothing. Second source first, geography
second, this third.

---

## 2. Coverage beyond highways

The standing problem behind everything else: 98% of the corpus is NHAI national
highways. Railways, metro, power and ports are represented by a handful of
hand-entered records. Until that changes, every national-level statement the site
makes is really a statement about highways. In progress as of 2026-09-12.

---

## 3. Project imagery

Drone footage and press photography would make individual project pages far more
compelling. Deferred because it is illustration rather than data: it cannot tell
you a project is late, there is no reliable key to match a video to a project
record, and reuse is embed-only. Revisit once project pages are worth enriching —
i.e. after 1 and 2.
