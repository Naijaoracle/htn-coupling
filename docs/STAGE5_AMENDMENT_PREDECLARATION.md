# Stage 5 amendment predeclaration

This amendment was fixed after the original Stage 5 result and before any
amendment simulation. The original predeclaration and outputs remain intact.

## A1. Taper audit

Audit every shipped ADAN56 `Rp` and `Rd`, and apply openBF's actual taper flag:
`!isapprox(Rd, Rp, atol=1e-4)`. Do not invent distal radii. If the shipped
network is already tapered, the constant-radius limitation in the 2024 openBF
healthy-ageing validation is recorded as not directly transferable to this
configuration. Constant terminal carotid segments remain a site limitation.

## A2. Central-only stiffening

At `E x2.5`, stiffen only the aortic arch, thoracic aorta, abdominal aorta,
brachiocephalic trunk, and bilateral common carotids. Leave every other vessel
and all WK3 compliances at published values. Run this arm with normotensive,
compliance-dominant, and combined Pulse inlets. Compare it against both inlet-
only and uniform-stiffening arms using the original augmentation definition and
noise floor. This is a mechanistic sensitivity arm, not a fitted replacement.

## A3. MAP-matched resistance phenotype

Use linear interpolation between existing `R=1.00` and `R=1.05, C=1.00`
StandardMale endpoints to select the resistance multiplier targeting the
compliance-dominant Pulse MAP of 96.105 mmHg. Accept within 0.5 mmHg; if the
first run misses, permit one secant correction. Compliance remains 1.0. Drive
openBF with its inlet and phenotype-specific resistance scaling, with published
wall properties. Compare its carotid shape against the compliance-dominant
matched-stiffening arm. The comparison is mean-matched but not severity-matched.

## A4. Fractional acute endpoints

Reanalyse the completed 16 acute traces without rerunning Pulse. Define baseline
MAP as the median over scenario time 0 through 29 s. Report first times to 20%,
30%, and 40% falls from that individual run's baseline. No missing crossing is
imputed. The 30% fall is the primary fractional endpoint because MAP 65 is a
31.8% fall from the normotensive StandardMale baseline.

## Decision rule

The original physiological-recognisability failure is overturned only if the
central-only arm restores the predeclared direction at both carotids: wider
pulse pressure, earlier identifiable reflected-wave phase, and increased
augmentation index. An absent secondary extremum is unassessable, not a pass.
Numerical shape separability and physiological recognisability remain separate.
