# IMPACT GRAPH

*Rule: Use this to determine exactly which tests to rerun based on file changes.*

**If `skills/cli.py` changes:**
- Need to rerun: CLI Tests
- Need NOT rerun: Memory Tests, Architecture Tests

**If `scripts/dgv.py` changes:**
- Need to rerun: Validator Tests, Graph Tests
- Need NOT rerun: CLI Tests
