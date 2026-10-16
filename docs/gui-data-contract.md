# GUI data contract (what the interface needs, and from where)

Written for the UI design that closes development and opens daily use. Every
field below already exists in the product; nothing here needs a new source.

## 1. The self (identity)
- `soul` - the product's own persona document (name, who, tone, limits,
  calibration). One stable self, the one that learns.
- Source: the memory package's soul reader/writer.
- The GUI shows it as the "who am I" pane, editable by the owner only.

## 2. The characters (behaviour per moment)
- **Catalogue**: traits by axis (11 axes: identity, cognition, competence,
  communication, values, tone, social, discipline, limits, context, experience).
- **Recipes**: the printed roles (assistant, engineer, senior_engineer,
  researcher, teacher, auditor, executive, crisis).
- **Current turn**: the composed character + WHY each ingredient was chosen
  (`Selection.explain()` is a ready-to-render string).
- **Lengths**: a spoken turn gets the short form, a written turn the full one.
- Source: the persona package (catalogue, composer, selector, injection).

## 3. The hands (skills)
- **Packs**: role -> skills, with `risk_floor`, required tools, and the
  professional metadata (categories, token budget, requires_evidence).
- **Resolution**: present / drafts / missing per pack, and `resolved` is true
  only when nothing the role names is missing.
- Source: the skills package (packs + the existing registry).

## 4. Memory
- **Structured**: core memory, people, profile, feedback, episodes (existing
  stores).
- **Semantic**: the meaning-based store (count, last writes, top hits for a
  query) - local embedder, no service.
- **Wiki**: the vault pages indexed at boot (count + last reconcile).
- Source: the memory package; the semantic store exposes count/search.

## 5. The hub (Jarvis as lead agent)
- **Role**: `personal-jarvis-lead` in the hub's own registry (id, purpose,
  modelPreferences, destructiveActionsRequireApproval).
- **Profile card**: capabilities, limits, and the recorded write grant.
- **Work**: which hub role is doing what, what waits at the human gate, and what
  is marked GELISTIRILECEK.
- Source: the hub's registries (read-only from the GUI) - the hub stays the
  authority for its own data.

## 6. Verification (trust at a glance)
- Last system sweep: 4873 passed / 0 failed (16 min) and the related slice
  1058 passed.
- Per-area: personas 48, skills 14, mission landing 16, semantic memory 17+live.
- Source: the test run; the number is reported with the date it was taken,
  never presented as live.

## 7. Rules the interface must keep
- **One self, many behaviours**: the character never replaces the soul; the soul
  is shown to the owner, the character is not a second identity.
- **The observer stays invisible**: no learning process, reflection or
  meta-comment is ever surfaced; the background learner is never shown.
- **Limits are visible and last**: the non-negotiables are displayed wherever a
  character is displayed, and a character can never loosen them.
- **Honest state**: an unverified number is labelled unverified; a missing skill
  is labelled missing; nothing is rounded up to look ready.
