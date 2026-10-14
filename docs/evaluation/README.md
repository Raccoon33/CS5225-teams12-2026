# Evaluation evidence

Evidence for the experiments in [evaluation-plan.md](../evaluation-plan.md), stored under one directory per experiment as agreed in decision **D-E5**: raw data, the script that produced it, and the date.

```
docs/evaluation/
  <experiment>/
    README.md            what was measured, when, and which claim each file supports
    scripts/             the code that produced the raw output
    raw/<YYYY-MM-DD>/    unedited output, one directory per run
    data/                derived tables other issues consume
```

Conventions:

- **Raw output is never edited.** If a run is wrong or superseded, it stays and the README says so.
- **No credentials in this tree.** Scripts read tokens from the environment.
- **A run without its script is incomplete evidence** and must be labelled as such, because D-E5 requires the script version.

| Evidence                                             | Directory                    | Status                                                                   |
| ---------------------------------------------------- | ---------------------------- | ------------------------------------------------------------------------ |
| OneMap feasibility and source-level commute coverage | [feasibility/](feasibility/) | Reviewed archive, with discrepancies and candidate-selection limitations |
| E6 bad-file/PITR recovery                            | [e6/](e6/)                   | Procedure; not run                                                       |
| E8 rental audit                                      | [e8/](e8/)                   | Source-level audit; integrated acceptance still pending                  |
| E9 hosting costs                                     | [e9/](e9/)                   | Reproducible assumption model; measured account/usage inputs pending     |
| Other experiments                                    | planned                      | Execution after implementation, 30 Oct–8 Nov baseline                    |

Use lowercase experiment IDs going forward; the named feasibility archive and historical raw files remain. A renamed directory does not change its measurements.
