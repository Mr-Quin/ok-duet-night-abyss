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

Multi-run jobs confirm it (overnight soak, two cases):

| Mission | Run | Between runs (result, 再次进行, loading) |
|---|---|---|
| 扼守, 3 rounds per run | 92 to 101 s | 12 to 13 s |
| 驱离 | 30 to 32 s | 8 to 9 s |

The gap between runs is the game's result screen and loading; the bot reacts within a few
tenths of a second. A running job is bound by the game.

## The rule-based labels are wrong exactly where it matters

A contact-sheet audit of 126 recorded frames (harness/ml/sheet.py) found the labels right for
menus, start screens, result, round dialogs and loading screens, and wrong on the one
distinction the bot most needs: open world versus in a run. The phase check labels the open
world `in_run` (its HUD template matches both), and the navigator labelled about a third of
non-defence runs `world` because ok-script's full-frame OCR at reduced size cannot read the
small mission panel. A model distilled from these labels would learn the same confusion, so
an independent, hand-checked answer key is required before any model number means anything.

## A better rule, found with the data, beat the need for a model

Scoring every recorded full frame against the top-left icon (exit door inside a run, menu
icon in the open world) separates the two cleanly: runs 0.77 to 0.99, open world 0.22 to 0.53,
nothing in between. Added to the navigator's run detector as a fallback, it turned 30 replayed
frames from world/unknown into the correct `dungeon` (spot-checked by eye); the 19 screen tests
still pass. This is the pattern worth keeping: record labelled frames continuously, audit a
sample, replay detectors offline, and look for the visual cue that separates the confused
classes. A learned model would likely latch onto the same cue; here a 48x76 template was enough
and needs no training or retraining.

## Model results (25 sessions, 3,277 frames, every fifth session held out)

| Model | Screen (339 test frames) | Phase (762 test frames) |
|---|---|---|
| MobileNetV3-small fine-tuned, 320x180, class-balanced | 92.3% | 99.0% |
| Same, frozen ImageNet features, last layer only | 91.0% | 96.7% |
| 1-NN on frozen features, 1 / 5 / 20 examples per class | 59 / 69 / 58% | 42 / 51 / 90% |
| Unseen class flagged by distance, at 95% of known kept | about 24% | 2 to 12% |

Latency 14 to 23 ms per frame on the 4060 or the CPU. Labels are the rules' own (with 36
hand corrections), so these numbers measure imitation, and the earlier sessions still carry
uncorrected world/run mislabels in both train and test.

- The phase model is close to the rules (in_run recall 99.5%) but still wrong about once a
  hundred looks; at several looks a second it would need the same hysteresis and navigator
  confirmation the rules use, and it would still not beat them.
- The screen model has systematic errors (21 run frames called result, result precision 0.125).
- **Few-shot on off-the-shelf features does not work**: 59 to 69% accuracy and a weak
  unseen-screen signal. "Add five frames for a new screen" would need embeddings trained for
  this game (metric learning), which brings retraining back.

A blind audit (harness/ml/audit.py) settled whether the screen model's misses were label noise:
on 40 held-out frames where model and recorded label disagreed, judged by eye without seeing
either label, the recorded label was right 34 times and the model 5 times; on 30 sampled
agreements both were right 30 times. The misses are real model errors, mostly frames from one
dark defence map called `result`, which looks like a map-appearance shortcut rather than
reading the HUD.

What these results do and do not show (after a second opinion): off-the-shelf features with
1-NN fail at few-shot, and this fine-tuned classifier is not ready to replace rules. They do not
prove game-specific metric learning is required; fine-tuned-encoder prototypes with the new
class withheld from training would be the next, cheap test. Speed: OCR is about 41% of a
navigation step, so a screen classifier could save up to about 4 s per navigation, but only on
steps that do not need OCR anyway, and that is 0.4 to 1.1% of a ten-run job.

**Verdict for screen/phase recognition: not worth pursuing now.** Rules plus the data loop
(record, audit, replay, find the separating cue) are faster, more accurate and cheaper to
change for a new screen. The model route becomes interesting only where rules cannot see at
all (enemy positions, attack tells for real combat), and the same recorder and audit tooling is
what that would need first.

## What the offline harness can and cannot show

- Detector replay (test_replay) checks recorded frames against hand-checked labels, offline.
- The recorded world replays one journey exactly, and as a graph in random target orders
  (test_sim_fuzz). On a 60-target recording that was 69 covered successes and 111 coverage gaps
  out of 180 attempts: most attempts were inconclusive, so "no navigator errors" only covers the
  recorded paths. Larger recordings shrink the gaps.
- Replay cannot show how the game reacts to a different action, so live soaks stay the
  end-to-end test; the harness is a fast regression gate before them.

## The walker's marker and distance reading is not a bottleneck

The recorder saves a crop and the walker's reading at every marker lookup. An eye check of all
137 looks from three defence sessions (harness/ml/walk_audit.py):

| | |
|---|---|
| readable distance, read right | 48 of 49 (the miss: 22 read as 23, likely the next frame) |
| no marker in the crop, walker saw none | 24 of 24 |
| marker with no readable distance (inside the defence area, or covered by effects) | 64; walker read a number on 3 (two plausibly right, one possibly 12 read as 2), missed the marker once |

Misreads are about 1 to 2% of looks, and the dangerous kind (a much smaller distance, i.e. a
false arrival) is caught by checking that the wave started. **A learned marker/distance reader
is not worth building now**; the stop criterion set before the check (the rules already avoid
the meaningful errors) is met.

## Where a model could still matter

Places the rules cannot see at all: enemy positions and attack tells for real combat, and
recovery when the character is off the route (fell, knocked back, stuck). Those need labelled
footage first, and the recorder and audit tools built tonight are what that work would start
from.

## Open questions being tested

- Can a classifier tell the open world from a run? The rule-based in_team() check cannot (it
  matches the HUD, which both have), which caused real failures this week.
- How much hand-checking does an honest evaluation need, and do the rules' labels hold up
  under a contact-sheet audit?
- What does a new screen or a game patch cost: retraining from auto-labelled soak data, or
  writing a rule?
