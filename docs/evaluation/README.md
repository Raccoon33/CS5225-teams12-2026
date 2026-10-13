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

| Experiment                                               | Directory                    | Status                                  |
| -------------------------------------------------------- | ---------------------------- | --------------------------------------- |
| Feasibility checks for #3 (OneMap geocoding and routing) | [feasibility/](feasibility/) | Partial — see its README                |
| E1–E10                                                   | not started                  | Evidence collection runs 30 Oct – 8 Nov |
