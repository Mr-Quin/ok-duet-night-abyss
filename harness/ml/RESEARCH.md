# Vision-based game automation: what exists and what is worth trying here

Survey done 2026-10-19 with web research (three parallel passes: bot frameworks, research
agents, perception building blocks). Key claims were spot-checked against the primary page;
those are marked (checked). Everything else is as reported by the source and should be
re-read before building on it.

## What the mature open-source bots do

The projects with real users all keep rules (templates, colour masks, OCR, page graphs) for
screens and menus, and use small learned models only where a template cannot work.

| Project | Learned models | Rules / classical |
|---|---|---|
| [MaaEnd](https://github.com/MaaEnd/MaaEnd) (Arknights: Endfield, 3D) | per-frame ONNX detector feeding combat state; zone classifier; camera-heading model from the minimap (checked) | masked ZNCC minimap matching with a motion-limited search window; combat as fixed-order rules or a user timeline (checked); offline screenshot node tests in CI |
| [BetterGI](https://github.com/babalae/better-genshin-impact) (Genshin) | YOLOv8 ONNX for some detections; tiny fitted model for fishing | SIFT minimap-to-map localisation with local then global search; waypoint pathing with stuck detection and escape; community route repository |
| [ZZZ-OneDragon](https://github.com/OneDragon-Anything/ZenlessZoneZero-OneDragon) | YOLOv8 event detector; YOLOv8 classifier for attack flashes (dodge) | battle state machine with user scripts |
| [ok-wuthering-waves](https://github.com/ok-oldking/ok-wuthering-waves) (same framework as us) | one-class YOLOv8 detector (echoes) | everything else templates and OCR |
| [MAA](https://github.com/MaaAssistantArknights/MaaAssistantArknights), [ALAS/SRC](https://github.com/LmeSzinc/StarRailCopilot), [March7th](https://github.com/moesnow/March7thAssistant) | little or none | templates, OCR, page-graph UI navigation; MAA keeps a screenshot test set |

No project found uses a CNN for screen classification, which matches our result in FINDINGS.md.

The recurring 3D navigation recipe (BetterGI, MaaEnd): localise from the minimap every frame,
turn toward the next waypoint, walk, detect "stuck" from position change over a window, run an
escape routine, and fail a point explicitly after a timeout. MaaEnd warns against filling
localisation gaps with predicted positions because the error accumulates (checked).

## Research agents that play from pixels

| Work | Scale | Takeaway for one game, one developer |
|---|---|---|
| [NitroGen](https://arxiv.org/abs/2601.02427) (2026) | 40k hours, 1,000+ games, actions parsed from videos (checked); ~500M params, 256x256 input, gamepad output | open weights; fine-tuning on one game helps most in combat. Gamepad output and coarse input are a poor fit |
| [Open-P2P](https://arxiv.org/abs/2601.04575) (2026) | 8,300 h human play, up to 1.2B params, real time on a consumer GPU, data and code released (checked) | closest open recipe for a small keyboard/mouse policy |
| [Lumine](https://arxiv.org/abs/2511.08892) (2025) | Qwen2-VL-7B, ~2,400 h contractor play, 4 datacenter GPUs | proof that a gacha action RPG can be played from pixels; not released, far beyond our budget. Half its errors are perception (small objects, losing targets) |
| [CombatVLA](https://arxiv.org/abs/2503.09527) (2025) | 3B, action tracker logging inputs with video, one game's combat (checked) | same scope as us, but ~1.85 s per decision with the game paused |
| [VPT](https://arxiv.org/abs/2206.11795) (2022) | inverse dynamics model trained on logged play, then labels unlabelled video | the cheap trick that transfers: a few hours of input-logged play can label everything else |
| SIMA 2, Game-TARS, Cradle, UI-TARS | closed or seconds per step | a vision-language model as a slow planner over scripted skills works for menus and recovery, not real-time combat |

Still research-only: hours of free navigation in 3D from pixels, surviving game patches without
retraining, precise combat from a general model.

## Perception building blocks

- Detectors run in 1 to 8 ms on a T4-class GPU (vendor numbers), so latency is not the issue.
  Prefer Apache-2.0 detectors (RT-DETR, RF-DETR, D-FINE) over AGPL YOLO if the bot is
  published. Labels can be bootstrapped with Grounding DINO and then corrected by hand.
- Small vision-language models (Qwen3-VL-2B, Florence-2) are too slow and nondeterministic for
  the loop; useful offline as a labeller for frames the rules call unknown.
- DINOv2/SigLIP embeddings: nearest-centroid over several shots beats the 1-NN we tried;
  better as an unknown-screen detector than as a classifier.
- Outcome labels are free from our own runs: frames before an HP drop (attack tells), frames
  where the walker got blocked (obstacles).

## Recommendation

1. **Combat perception as small detectors feeding rules**, the MaaEnd and ZZZ-OD pattern:
   enemy boxes and an attack-flash classifier. Label from recorded full frames (auto-boxed,
   hand-corrected) and from HP-drop events. Stop if a detector fine-tuned on a few hundred
   corrected frames is below mAP50 0.6, or an attack-tell classifier below AUC 0.7 on held-out
   runs.
2. **Minimap localisation** for defence walking and getting back on route. DNA shows a minimap
   top left inside runs; first check it is matchable (masked ZNCC or SIFT against a stitched
   map, as BetterGI and MaaEnd). Stop if position error exceeds about 1 m on more than 10% of
   200 hand-checked frames.
3. **Log the player's own inputs** alongside recorded frames when the user plays by hand. It
   costs nothing now and is the data an inverse dynamics model or a narrow combat policy would
   need later.
4. **Offline per-screen assertions**, which MaaEnd and MAA run in CI and we already have in
   tests/test_nav_screens.py and harness/test_world.py; keep growing them from soak frames.

Not now: end-to-end policies (fine-tuning NitroGen or Open-P2P) until rule-based combat
plateaus, and a vision-language model on the hot path.
