# Task 31 cleanup receipt

- Browser QA Chrome PID: killed and waited after screenshot capture.
- Browser QA dashboard server PID: killed and waited after screenshot capture.
- Chrome user-data dir `/tmp/codescent-task31-chrome-profile`: removed.
- Temp port/log/PID files: removed.
- Fixture state: `tests/fixtures/python-basic/.codescent` removed.
- Python caches: project `__pycache__` directories and `.pytest_cache` removed after verification.
- Adversarial dashboard servers: shut down with `server.shutdown()`.
- Adversarial temp repos: removed by the evidence script.
