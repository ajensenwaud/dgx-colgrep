Some tests in this repository are failing:

- tests/hermes_state/test_reasoning_roundtrip.py (whole file)
- tests/cli/test_branch_command.py::TestBranchPreservesReasoningFields
- tests/test_tui_gateway_server.py::test_persist_branch_seed_keeps_reasoning_fields
- tests/test_tui_gateway_server.py::test_session_branch_keeps_reasoning_fields

Find the root cause(s) in the source code and fix them so that these tests pass. Do not modify the tests. Fix the whole bug class, sibling code paths included, not just the first site you find. Do not break other tests.

Run tests from the repository root with:

    {TEST_CMD}

When you are done, reply with a short summary of the root cause and the list of files you changed.
