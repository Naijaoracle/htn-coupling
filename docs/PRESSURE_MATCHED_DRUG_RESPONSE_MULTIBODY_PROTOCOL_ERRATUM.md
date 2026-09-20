# Erratum: multi-body norepinephrine protocol run count

**Date:** 2026-09-20

**Protocol revision:** `b3bf60fc3abb24d3a029e359a9a907c2ac4471c4`

The protocol says: “For each accepted body, run each route twice in fresh Pulse processes (eight runs per accepted body pair).” The parenthetical is an arithmetic and wording error.

The intended and executed design was two routes (direct and modifier) × two fresh-process repeats per route: **four challenged runs per accepted body pair**. For the four accepted bodies, this gives 4 bodies × 2 routes × 2 repeats = **16 challenged runs**. The precommitted configuration specified two repeats per route, and the completed result manifest records 16 completed challenge runs with all eight route-pair gates passing.

This erratum clarifies the run count only. It does not change the protocol, dose, endpoints, acceptance criteria, or analysis. The original precommitted protocol file remains unchanged so its recorded hash continues to identify the text used for the experiment.
