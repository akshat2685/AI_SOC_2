---
name: managing-python-dependencies
description: |
  Ensures proper Python dependency management, avoiding global `pip install` and
  adhering to project-specific tooling.
---
# Python Dependency Management Rule
...
venv + pip workflow:
- Always use `.venv/bin/pip` or `.venv/bin/python` (explicit path).
- After installing, run: `.venv/bin/pip freeze > requirements.txt`.
- When setting up: `.venv/bin/pip install -r requirements.txt`.
