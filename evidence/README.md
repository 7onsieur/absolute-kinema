# Independent test evidence

These reports are the record behind this release candidate's claims. They are unedited except that,
in the rc1 report, local test-machine paths were replaced by `<test-workspace>/`. The
`/home/claude/...` path quoted in both reports is the anonymous development-sandbox path that caused
the rc1 test blocker. It is kept as evidence.

| File | Version tested | Tester | Verdict |
|---|---|---|---|
| [`INDEPENDENT_TEST_REPORT_v0.4-rc1.md`](INDEPENDENT_TEST_REPORT_v0.4-rc1.md) | v0.4-rc1 | Independent fresh AI-agent session (earthquakes project) | **Not ready**: 1 blocker (Kokoro tests tied to a developer path), 1 moderate (lead-in stored as a timestamp gap), documentation issues |
| [`RELEASE_ASSESSMENT_v0.4-rc2.md`](RELEASE_ASSESSMENT_v0.4-rc2.md) | v0.4-rc2 | Independent assessment (volcano demo) | **GO, with documented limitations**. No release blockers |

Every rc1 finding was fixed in rc2. The rc1 report's earthquake example was re-rendered with rc2 and
is in [`../examples/earthquakes/`](../examples/earthquakes/README.md).

Neither tester listened to the audio as the human approver. Caption approval is always left to a person.
