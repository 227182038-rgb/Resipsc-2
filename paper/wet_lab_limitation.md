# Wet-lab Limitation Statement — resipsc v2.0

## Status of computational claims

resipsc v2.0 is a **computational** method for detecting residual pluripotent
stem cells (PSCs) in single-cell RNA-seq of cell therapy products. Its
quantitative performance claims rest on simulated multi-site data and a real
PBMC negative reference (hybrid training). **No wet-lab orthogonal validation
has been performed for this build.** Specifically, we have not run:

1. **Histological embryoid-body / in vitro clonogenicity assays (HEC)** —
   the 0.001% LOD benchmark reported for HEC in the literature is not
   reproduced here.
2. **ddPCR for LIN28A/ESRG** — the reported 0.0003% sensitivity of
   droplet-digital PCR assays has not been compared side-by-side.
3. **lncRNA flow cytometry** panels — the published 0.0001% floor of
   lncRNA-based detection remains an external reference, not an
   internally validated limit.
4. **In vivo teratoma assays** — ethically and practically out of scope
   for this build; literature priors are used instead.

## Why this is honest framing rather than a flaw

Computational detection from scRNA-seq data is fundamentally a *sampling*
problem: a 0.001% residual fraction implies one PSC among 100,000 cells, so
the achievable limit of detection is governed by the number of cells actually
sequenced. Our spike-in analyses therefore report recall as a function of
fraction and cell count, with bootstrap confidence intervals, rather than
claiming a single LOD number. The wet-lab assays above measure different
biological quantities (viable colony formation; molecular droplet counts)
and a rigorous head-to-head requires clinical specimens.

## Path to clinical validation (future work)

Closing the wet-lab gap requires a clinical collaborator and is planned in
three stages: (i) side-by-side method-comparison on spiked manufacturing
samples across 3 independent sites, comparing resipsc calls against ddPCR
(LIN28A/ESRG) and flow cytometry (TRA-1-60/SSEA-4) with blinded scoring;
(ii) a bridging study on real PSC-derived product batches with orthogonal
confirmation of every non-RELEASE disposition; (iii) regulatory engagement
(FDA pre-submission) to define acceptance criteria under 21 CFR 1271.

Until those studies are complete, resipsc must be labelled
**Research Use Only — NOT FDA-cleared**, and every non-RELEASE disposition
must be confirmed by an orthogonal wet-lab assay before any clinical
decision is made.
