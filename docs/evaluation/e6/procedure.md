# E6 bad-rent-file and DynamoDB recovery procedure

**Experiment:** E6

**Status:** Procedure only; not yet run

**Environment:** Dedicated `eval` stage only

## Question

Does a malformed rent input fail before publication, while searches continue to use the last validated snapshot unchanged? Separately, can the table be restored to a known-good point with DynamoDB point-in-time recovery (PITR), and how long does that take?

The bad-file test and the PITR drill are separate phases. A correctly rejected file should not require restoration. PITR tests recovery from an accidental write or deletion that bypasses normal validation.

## Preconditions

Do not start the experiment until all of the following exist:

1. The `eval` stack is deployed with the rent ingestion path, immutable rent snapshots, and an atomic `RENT/CURRENT` pointer.
2. DynamoDB PITR reports `PointInTimeRecoveryStatus = ENABLED`, and its earliest/latest restorable timestamps include the planned recovery point.
3. A rent-ingestion failure metric and CloudWatch alarm are deployed and initially in `OK` state.
4. A known-good source file has been published as snapshot A. Record its source digest, snapshot ID, pointer item, item count, and expected town/flat-type keys.
5. Fixed group/search fixtures and every needed commute entry are already loaded. This prevents route availability or changing group inputs from contaminating the rent comparison.
6. The ingestion task has an explicit expected-key manifest for the drill. It must identify a removed town as invalid without hard-coding the historical assumption that Singapore always has 26 towns.
7. Clock sources use UTC, and the operator has permission to read metrics, run ingestion, invoke searches, and restore to a new table. Deleting the restored table after review requires separate authorization.

AWS documents that DynamoDB PITR restores into a **new table**, not in place. A restore does not automatically carry over settings including tags, TTL, alarms, streams, and PITR, so the drill must verify or reapply them before any cutover. See [AWS's DynamoDB restore documentation](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/pointintimerecovery_restores.html).

## Phase A — rejected-file isolation

### Establish the baseline

1. Read and save `RENT/CURRENT` and the snapshot-A metadata.
2. Execute the fixed searches and save their completed API responses.
3. Canonicalise responses for comparison by removing only request-specific identifiers and timestamps. Preserve the rent snapshot ID and period, ranked/excluded towns, rent values, sample sizes, quality status, reasons, scores, and member outcomes.
4. Start a continuity probe using the same fixed searches. Record every request's timestamp, status code, completion state, rent snapshot ID, and canonical response digest until five minutes after the failed ingestion or until the alarm enters `ALARM`, whichever is later.

### Build W5 fixtures

Derive four files from the known-good source without changing anything else:

1. **Renamed column:** rename `monthly_rent` to `rent`.
2. **Negative rent:** replace one valid `monthly_rent` with `-1`.
3. **Missing town:** remove every row for one town required by the drill's expected-key manifest.
4. **Combined W5:** apply all three mutations to one file.

Run the three single-fault files first so validation evidence proves each condition is detected even if the production validator stops after its first error. Then run the combined W5 file used by the evaluation plan.

### Inject and observe

For every fixture:

1. Record injection time `T0` and invoke the normal ingestion entry point.
2. Save the structured validation result and execution logs. They must identify the relevant schema, value, or completeness failure without publishing.
3. Read `RENT/CURRENT` again with a strongly consistent read.
4. Check for partially written items under the rejected candidate snapshot ID. Staging items may exist only if they are unreachable and the implementation's cleanup contract permits them; record their count.
5. Continue the search probe and record the first time `T_alarm` at which the CloudWatch alarm enters `ALARM`.
6. Execute the baseline searches again and compare canonical response digests.

### Phase-A pass conditions

- Every invalid input is rejected and no invalid snapshot becomes current.
- `RENT/CURRENT` remains byte-for-byte equivalent to the recorded snapshot-A pointer.
- All searches attempted during the incident receive successful responses from snapshot A.
- Before/after canonical search responses are identical.
- No unknown rent is represented as zero.
- The failure alarm enters `ALARM`; report `T_alarm - T0`. No target is claimed until the team approves one.
- Evidence records the number of searches attempted, answered, failed, and changed.

Any failed condition makes Phase A fail. Do not proceed as though PITR compensates for a publication-integrity failure.

## Phase B — PITR restoration drill

Run this phase only after Phase A evidence is safely stored.

1. Record a known-good recovery timestamp `T_good` within DynamoDB's reported restorable window and before the corruption injection.
2. In the `eval` table only, deliberately overwrite a copy of `RENT/CURRENT` or one known snapshot item with a marked corrupt value. Record `T_corrupt`, the exact key, and the before/after values.
3. Confirm the test detects the corruption. Do not direct normal shared environments at the corrupt table.
4. Record `T_restore_start` and call `RestoreTableToPointInTime` with `T_good` and a new, unique target table name.
5. Poll the target table until `TableStatus = ACTIVE`; record `T_restore_active` and any restore error.
6. On the restored table, verify the snapshot-A pointer, expected keys, item counts, and recorded item value. Confirm the marked corruption is absent.
7. Reapply or verify the non-restored operational settings needed for a usable table: tags, TTL, alarms, streams, deletion protection, and PITR. Record each setting rather than assuming it was copied.
8. Point an isolated verification deployment at the restored table and rerun the canonical baseline searches. Do not change the shared `dev` or production configuration.
9. Record `T_recovery_verified` after the restored-table searches match the baseline.
10. Preserve the evidence before requesting approval to delete the restored table and any temporary verification resources.

Report two durations:

- **DynamoDB restore duration:** `T_restore_active - T_restore_start`.
- **Verified recovery duration:** `T_recovery_verified - T_restore_start`.

### Phase-B pass conditions

- The restored table reaches `ACTIVE` without modifying the source table.
- Snapshot-A invariants and the deliberately corrupted item are restored to their `T_good` values.
- Canonical searches against the isolated restored-table deployment match the baseline.
- Restore and verified-recovery durations are recorded even if they miss a later team-approved target.

## Evidence to retain

Store the following under `docs/evaluation/e6/` after the run:

- redacted commands and UTC timestamp log;
- hashes and mutation manifests for the good and W5 input files;
- structured validation outputs for all four invalid fixtures;
- before/after `RENT/CURRENT` values and rejected-candidate item counts;
- canonical baseline, during-incident, and after-test search outputs plus their diff;
- continuity-probe summary;
- CloudWatch alarm history and `T_alarm - T0`;
- PITR status before the drill, restore request metadata, target-table status history, and both durations;
- restored-table invariant checks and the isolated verification-search diff;
- cleanup approval and outcome.

## Current blockers

This procedure cannot yet produce an E6 result. It requires issue #28's ingestion implementation, an `eval` deployment with PITR and alarms, a team-approved expected-key policy, and fixed integrated search fixtures. Until those exist, E6 must remain “not run”; the snapshot design alone is not evidence that searches survived a bad input or that restoration succeeded.
