# Masthead Memory

Fresh template. This repo ships with no session state: the memory file starts empty and is
written only by the running machine. Nothing personal is stored here, and per `RULES.md` no
secrets ever are.

The filesystem is the source of truth for what is in flight — read `drafts/*/piece.md`
rather than trusting a cache here. This file holds the pointers a session needs to resume
without re-deriving them.

## Session Context

### Active Voice
- voice: (unset)
- set_at: (unset)

### Active Piece
- piece: (unset)
- path: (unset)
- stage: (unset)

### Current Step
- step: (unset)
- turn: (unset)
- persona: (unset)

## Voice Registry
<!-- One line per pack under voice/. Slug — who it is, what it writes, register in three words. -->
- demo-dana — FICTIONAL demo persona: infrastructure engineer; technical explainers, incident
  write-ups, architecture notes; clipped, evidence-first, verdict-clear
- demo-mira — FICTIONAL demo persona: field-notes essayist; narrative nonfiction about systems
  and the people who run them; scene-led, patient, plain-spoken

## In-Flight Pieces
Read `drafts/*/piece.md` to discover.
Nothing cached here — source of truth is the filesystem.
(The three folders shipped in this repo are demo pieces at three different stages; see README.md.)

## Recent Oracle Runs
- (none yet)

## Lessons Applied This Session
- (none yet)
