# Navigator harness (fork only)

Tests for `src/nav` and the 30/65 task that go further than the unit tests in `tests/`, kept in
the fork because they need recordings of one account's game or a PC running the game.

## Without the game

```
python -m unittest harness/test_world.py
```

Needs only `numpy` and `opencv-python`; no OCR model and no ok-script. The fork CI runs it on
every push to `nav-harness`.

- `TestPrivacy` checks the saved images and OCR text for personal details (see below).
- `TestFixtures` classifies 30 masked screenshots in `fixtures/` with their stored OCR
  results and checks the screen kind and what was read from it (tab, level, auto rounds...).
- `TestRecordedWorld` uses a recorded journey in `world/`:
  - every recorded screen still classifies to the same signature, so a detector change that
    alters how a known screen reads fails here;
  - the journey replays with `TraceBackend`: the navigator is sent to the same targets in the
    same order and must send the same inputs it sent against the real game, step by step.

`SimBackend` (in `sim.py`) treats the recording as a graph instead, so targets can be visited
in orders that were never recorded. It raises `Unexplored` when the navigator tries an input
the recording has no outcome for.

## Recording a world

On the game PC, with `live/service.py` running in the desktop session and the game in front:

```
python -m harness.record_world harness/world 60 --seed 7
```

It sends the navigator to 60 random targets and saves every screen it read (masked by
`privacy.py`, downscaled to 1280 wide), the transitions between them, and the exact trace.
Look through `world/states/*.jpg` by eye before committing a recording.

## Privacy

`privacy.py` decides what is blacked out per screen kind: UID, wallet, chat, profile,
quest and map names, the party HUD and character, team presets, and on screens drawn over a
run (results, in-run menu, round and confirm dialogs, main menu) everything except the panels
the navigator reads. OCR items inside blacked-out regions are dropped from the JSON too.
`TestPrivacy` fails if any saved image shows something in the UID box or any saved OCR text
has a long number in it (HP, currency, IDs), so a new recording cannot slip one in.

## On the game PC

- `live/service.py`: small HTTP service that captures the game window and sends input. It
  refuses input while the game is not the foreground window.
- `live/backend.py`: `LiveBackend`, a navigator backend over that service with its own OCR.
- `live/soak.py`: runs the real 30/65 task through ok-dna for every Lv.30 and Lv.65 entry and
  a few awkward starting points (main menu, another start screen, restarting inside a run,
  自动轮次 off), and checks each run count is reached and the game ends up back in the world.
