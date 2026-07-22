# Contributing to ShieldAI (EDYSOR)

Thank you for your interest in contributing to ShieldAI! We welcome community contributions, bug reports, documentation enhancements, and feature proposals.

---

## 🛠️ Development Setup

1. **Fork & Clone**:
   ```bash
   git clone https://github.com/your-username/AI_SOC_2.git
   cd AI_SOC_2
   ```

2. **Configure Environment**:
   ```bash
   cp .env.example .env
   ```

3. **Start Local Infrastructure**:
   ```bash
   docker compose up -d
   ```

4. **Install Python & Node Dependencies**:
   ```bash
   # Python Backend
   python -m venv .venv
   source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
   pip install -r backend/app/requirements.txt
   pip install -r intelligence_engine/requirements.txt

   # Frontend
   cd frontend
   npm install
   ```

---

## 🧪 Testing Guidelines

Before submitting a Pull Request, verify that all test suites pass clean:

```bash
# Run Python Unit & Integration Tests
python -m pytest tests/

# Code Style Checks
flake8 backend/ intelligence_engine/
```

---

## 📝 Pull Request Workflow

1. Create a descriptive feature branch:
   ```bash
   git checkout -b feature/awesome-detection-rule
   ```
2. Commit your changes following [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat: add anomaly detection rule for DNS tunneling`
   - `fix: resolve race condition in Kafka worker batch commit`
3. Push to your fork and submit a Pull Request targeting the `main` branch.
4. Ensure CI checks pass. A maintainer will review your PR within 48 hours.

---

## 🛡️ Code Standards
- **Python**: Enforce PEP 8 style guidelines. Write type hints (`typing.Dict`, `Optional`, `TypedDict`).
- **SQL Queries**: ALWAYS use SQLAlchemy ORM or parameterized prepared statements. NEVER concatenate strings into SQL queries.
- **Async Efficiency**: Use `async`/`await` for network and database I/O.
