# Learned perception POC: findings

Running notes from the overnight experiment (2026-10-18). Numbers are from the G14 with the
game running at 2560x1440.

## Where the time goes

| What | Cost | Source |
|---|---|---|
| Run-loop phase check (about 8 template matches) | 16 ms per look | harness/test_replay.py, 36 recorded frames |
| Navigator screen check (full-frame OCR + detectors) | 477 ms per look | harness/test_replay.py, 23 recorded frames |
| One navigation (world to a book row's start screen) | 11.2 s average, 1.1 s per step | harness/nav_timing.py, 60 navigations |
| MobileNetV3-small, 320x180, untuned | about 17 ms per frame (4060 or CPU) | harness/ml/train.py |

OCR is about 0.48 s of each 1.1 s navigation step; the rest is waiting for the screen to settle
and game animation. A job navigates once and then repeats runs with 再次进行, so navigation is
a few percent of a long job. Mission time is set by the game (loading, the run, the result).

**Conclusion: learned perception does not pay for itself on speed here.** Replacing the phase
check gains nothing (it is already 16 ms); a perfect, free screen classifier would cut at most
about 40% of a navigation, about 5 s per job, and only if the following action does not need
OCR anyway (most book steps read text to choose where to click). Any case for a model has to
be robustness or scaling to new screens.

## Open questions being tested

- Can a classifier tell the open world from a run? The rule-based in_team() check cannot (it
  matches the HUD, which both have), which caused real failures this week.
- How much hand-checking does an honest evaluation need, and do the rules' labels hold up
  under a contact-sheet audit?
- What does a new screen or a game patch cost: retraining from auto-labelled soak data, or
  writing a rule?
