# Stage 3: optical-site reachability

## Decision

**Outcome C: no shipped openBF vessel is a physical facial-rPPG site.** The named-conduit gap alone looks like outcome B: both models contain bilateral external and internal carotids, and the missing named branches are only a few generations away. That classification is inadequate for the optical claim, however. A camera measures blood-volume variation in the cutaneous microvascular bed, not pressure or flow in a named conduit artery. Adding a facial, superficial temporal, ophthalmic, supraorbital, or supratrochlear segment would still leave the dominant artery-to-dermis transfer unmodelled.

The defensible Stage 4/5 design is therefore a **dual reference-site model**, not a physical-site model:

- use distal external carotid output as the upstream reference for malar, chin, and lower/lateral nose territories;
- use distal internal carotid output as the upstream reference for forehead/glabella, most periorbital territory, and upper nasal dorsum;
- split the nose ROI anatomically or do not assign it to a single carotid system; and
- do not treat the two reference waveforms as interchangeable.

The transfer assumption is deliberately narrow: hypertension-related changes in waveform timing and morphology at the appropriate upstream carotid reference are candidate drivers of changes downstream in its facial cutaneous territory. The present model does **not** predict cutaneous amplitude, optical intensity, phase lag through the terminal tree, or the contribution of ICA–ECA anastomoses. Stage 8 may compare upstream signatures with observed rPPG features; it may not call an openBF carotid trace a simulated rPPG waveform.

## What each camera region samples

Remote PPG is associated with cutaneous perfusion and blood-volume changes in superficial vascular tissue. Green-light imaging is reported to interrogate roughly the upper millimetre of skin and its capillary/upper arteriovenous networks, which is already downstream of every vessel in either openBF model ([Wieringa et al., 2018](https://pmc.ncbi.nlm.nih.gov/articles/PMC5981460/); [Rasche et al., 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7536393/)). Forehead and cheek are common high-performing ROIs, but optical performance does not make their arterial supply equivalent ([Bondarenko et al., 2025](https://www.nature.com/articles/s41746-025-01814-9)).

| Phase 4 region | Principal named supply | Parent system | Modelling consequence |
|---|---|---|---|
| Forehead / glabella | Supratrochlear and supraorbital arteries, with variable frontal superficial-temporal anastomoses | Ophthalmic ← ICA, with ECA collateral contribution | ICA reference; explicitly acknowledge variable ICA–ECA contribution |
| Malar / cheek | Facial, transverse facial, and zygomatic-orbital contributions | ECA via facial and superficial temporal arteries | ECA reference; no single distal branch is universal |
| Nose | Lateral nasal/angular and infraorbital supply laterally; dorsal nasal/ophthalmic contribution to upper dorsum | Mixed ECA and ICA | Split upper dorsum from lower/lateral nose or exclude a single “nose” proxy |
| Periorbital | Ophthalmic-derived supratrochlear/supraorbital branches medially; superficial temporal, transverse facial, and facial contributions laterally | Mixed, usually ICA reference medially | Define the ROI boundary; “periorbital” alone is not an arterial territory |
| Chin | Mental artery plus submental and inferior-labial anastomoses | ECA via maxillary and facial arteries | ECA reference |

The upper-face mapping is supported by anatomic review and imaging: the supratrochlear is normally a terminal ophthalmic branch, and the ophthalmic is an ICA branch, but anastomoses with angular, dorsal nasal, supraorbital, and superficial-temporal territories are common ([Kleintjes et al. review](https://pmc.ncbi.nlm.nih.gov/articles/PMC7105260/)). A 3-D cadaveric study found ophthalmic-derived periorbital branches alongside variable superficial-temporal, transverse-facial, and facial contributions to the lateral orbit and malar plexus ([Cong et al., 2019](https://pubmed.ncbi.nlm.nih.gov/30192913/)).

The lower and mid-face mapping is likewise not one-vessel-per-ROI. Dye injection of 24 cadavers assigned buccal skin mainly to facial artery with variable transverse-facial participation, and zygomatic skin mainly to superficial temporal with variable transverse-facial participation ([Vacher et al., 2020](https://pubmed.ncbi.nlm.nih.gov/31494018/)). Nasal dissections demonstrate contributions from facial/lateral-nasal, infraorbital, and dorsal-nasal vessels ([Bénateau et al., 2024](https://pubmed.ncbi.nlm.nih.gov/39331142/)). The mental artery arises from the inferior alveolar/maxillary route and anastomoses with submental and inferior-labial branches of the facial artery ([Iwanaga et al., 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7018628/)). All of those chin routes are ECA-derived.

## Shipped-network inventory

The audit used openBF revision `928c046906687c1347bf5496b47325acd0b2c032` and SHA-256-pinned YAML files. Every configured segment, its nodes, dimensions, material value, terminal status, boundary parameters, and computed root distance is recorded in the two inventory CSVs.

| Shipped model | Configured segments | Outlets | Carotid reach | Missing relevant vessels |
|---|---:|---:|---|---|
| `boileau2015/adan56` | 77 | 31 | Bilateral common carotid bifurcates to terminal ECA and terminal ICA, both WK3 | facial, superficial temporal, ophthalmic, supraorbital, supratrochlear |
| `alastruey2007/circle_of_willis` | 33 | 11 | Bilateral ECA terminates at WK3; bilateral ICA continues through `int-carotidII` into MCA/ACA and the Circle of Willis | facial, superficial temporal, ophthalmic, supraorbital, supratrochlear |

`adan56` is the model name, not the number of network rows in the present YAML. The configured file has 77 segments. The Circle-of-Willis model does help the ICA route anatomically by continuing intracranially, but it never emits an ophthalmic branch; it therefore does not reach forehead skin.

### Candidate upstream sites

Distances are cumulative configured lengths along the direct carotid route from the aortic root to the distal end. They are model distances, not subject-specific anatomical measurements.

| Model | Candidate | Direct route (m) | Distal radius (mm) | Terminal? | Use |
|---|---|---:|---:|---|---|
| ADAN56 | `external_carotid_R` | 0.264 | 2.265 | yes, WK3 | ECA facial-territory reference |
| ADAN56 | `internal_carotid_R` | 0.335 | 2.765 | yes, WK3 | ICA/ophthalmic-territory reference |
| Circle of Willis | `13-R-ext-carotid` | 0.428 | 1.500 | yes, WK3 | ECA reference, but stock operating point fails the resting-pressure gate |
| Circle of Willis | `21-R-int-carotidII` | 0.433 | 2.000 | no | closest named upstream reference to an unmodelled ophthalmic origin |
| Circle of Willis | `10-L-ext-carotid` | 0.445 | 1.500 | yes, WK3 | left ECA reference, same pressure problem |
| Circle of Willis | `18-L-int-carotidII` | 0.450 | 2.000 | no | left ICA reference, same pressure problem |

The complete bilateral candidate table also reports shortest graph distance. For the Circle of Willis this can be shorter through vertebrobasilar collateral routes; direct carotid distance is the appropriate quantity for the anatomical path discussed here.

## Resting controls and morphology

### ADAN56

The already-gated Stage 0 run provides a normotensive aortic control (approximately 119/83 mmHg, mean 103.4, pulse pressure 35.4 mmHg). At the distal right references:

| Site | Pressure (SBP/DBP), mmHg | Mean / PP, mmHg | Mean flow, mL/min | End-cycle flow, mL/min |
|---|---:|---:|---:|---:|
| external carotid | 119.3 / 81.5 | 103.0 / 37.8 | 175.7 | 127.6 |
| internal carotid | 126.5 / 80.9 | 102.9 / 45.6 | 286.0 | 208.3 |

Both pressure curves have a rapid systolic upstroke, reflected/secondary systolic structure, and post-systolic decline. The ICA carries greater mean and end-cycle flow than the ECA, consistent with the published qualitative distinction between a low-resistance cerebral ICA bed and a higher-resistance ECA bed ([Kim et al., 2013](https://www.jacc.org/doi/10.1016/j.jcmg.2013.09.015)). This is a morphology plausibility screen, not validation at facial skin.

Charlton's virtual ageing model reports pressure, flow, area, and PPG at multiple arterial sites, including common carotid—not facial or ophthalmic sites. Importantly, it generates distal PPG through an added microvascular Windkessel because those arterioles are absent from the 1-D arterial network ([Charlton et al., 2019](https://doi.org/10.1152/ajpheart.00218.2019)). That precedent supports the reference-site decision and contradicts treating a conduit waveform as a physical optical waveform.

### Circle of Willis

The unmodified shipped example converged in 9 cycles (66.7 s; final convergence RMSE 0.64 mmHg), but its reference pressures are not a normotensive resting state:

| Site | Pressure (SBP/DBP), mmHg | Mean / PP, mmHg | Mean flow, mL/min |
|---|---:|---:|---:|
| left external carotid | 222.3 / 130.9 | 173.3 / 91.4 | 151.7 |
| left internal carotid II | 223.8 / 133.1 | 175.6 / 90.8 | 249.0 |
| right external carotid | 221.3 / 130.9 | 173.5 / 90.4 | 151.8 |
| right internal carotid II | 223.6 / 133.1 | 175.7 / 90.6 | 256.0 |

It is anatomically closer to the ophthalmic take-off but fails the resting-pressure gate. Recalibrating its inlet or terminal boundaries may be useful later, but that would be a new model configuration, not validation of the shipped control. Stage 4 should therefore retain normotensive ADAN56 as the first bridge target.

## Why a conduit extension is not specified now

At the named-artery level the obvious additions would be ECA→facial/angular/lateral-nasal, ECA→superficial-temporal/transverse-facial, and ICA→ophthalmic→supratrochlear/supraorbital/dorsal-nasal paths. Published work supplies useful pieces: in-vivo MRI gives ECA branch flow fractions (facial 26.6 ± 10%, superficial temporal 18.4 ± 6%) ([Bettoni et al., 2018](https://pubmed.ncbi.nlm.nih.gov/29916728/)), and a validated 0-D ECA branch model includes facial and superficial temporal beds ([Ohhara et al., 2016](https://pubmed.ncbi.nlm.nih.gov/26846094/)). Those pieces do not provide a single, source-complete set of length, taper, wall thickness, Young's modulus, and terminal R1/R2/C for a bilateral 1-D facial extension.

More importantly, even a perfectly sourced conduit extension would not close the artery-to-cutaneous-rPPG transfer. Assigning numerical values now would create anatomical precision without optical identifiability. Because the formal classification is C, the outcome-B requirement to specify a build-ready extension is not triggered. If direct optical prediction later becomes essential, the next model is a region-specific terminal microvascular transfer model calibrated to simultaneous carotid/facial measurements—not merely more named tubes.

## Acceptance criteria

1. **Supplying artery identified:** complete, with mixed and anastomotic territories stated rather than forced into one parent.
2. **Both vessel inventories:** complete and machine-readable; 77 and 33 configured segments respectively.
3. **Outcome classified:** C for the optical programme; the narrower conduit-only gap is documented as B.
4. **Extension specification:** not applicable under C; candidate branches and the reason not to fabricate parameters are documented.
5. **Resting morphology:** ADAN56 reference traces pass a qualitative conduit-morphology screen; the Circle-of-Willis control converges but fails the normotensive amplitude gate.
6. **Site question:** answered as dual upstream reference sites with an explicit, limited transfer assumption—not physical facial sites.

## Reproducible artefacts

- `scripts/audit_stage3_networks.py` regenerates both inventories, candidate distances, waveform metrics, hashes, and figures.
- `scripts/run_stage3_openbf_cow.jl` runs the unmodified Circle-of-Willis control and writes its summary and final-cycle outputs.
- `results/stage3/adan56_vessel_inventory.csv`
- `results/stage3/alastruey2007_vessel_inventory.csv`
- `results/stage3/candidate_carotid_sites.csv`
- `results/stage3/adan56_waveform_metrics.csv`
- `results/stage3/circle_of_willis_waveform_metrics.csv`
- `results/stage3/adan56_distal_carotid_pressure.png`
- `results/stage3/circle_of_willis_carotid_pressure.png`
- `results/stage3/audit_manifest.json`
