# Cornell-KB Session Instructions

This directory is the Cornell-KB project root. Before any implementation, maintenance, retrieval-policy, or pipeline work:

1. Read `LUNA_DS_WORKING_FRAMEWORK.md`.
2. Read `README.md` and the latest relevant plan/status file.
3. Inspect `git status --short --branch` before editing.
4. Treat GPT-5.6 Luna as the staff engineer and architecture authority.
5. Use delegated DeepSeek V4 Pro subagents through CommandCode for bounded implementation, tests, documentation, and independent audits whenever practical.
6. Never parallelize overlapping writers or let a subagent silently redesign the architecture.
7. Require actual test commands and artifacts from every implementation subagent.
8. Keep OpenViking source-grounded retrieval, Hindsight memory, namespace safety, manifest validation, provenance, and production rollback rules from the framework intact.
9. For runtime Cornell queries, use the existing in-session validated query planner. Do not create a second model connection or delegate query planning.
10. Do not commit, push, publish, or modify production workspaces unless the user explicitly requests it.

The detailed operating contract is in `LUNA_DS_WORKING_FRAMEWORK.md`; it is the project authority for the Luna → DeepSeek workflow.
