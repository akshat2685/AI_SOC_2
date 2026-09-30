import sys
import os
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# Set dummy API keys and env vars to avoid startup errors
os.environ["GEMINI_API_KEY"] = "test-dummy-key"
os.environ["GOOGLE_API_KEY"] = "test-dummy-key"
os.environ["POSTGRES_URL"] = "postgresql://user:password@localhost/db"
os.environ["NEO4J_AUTH"] = "neo4j/password"
os.environ["KAFKA_BOOTSTRAP_SERVERS"] = "localhost:9092"
os.environ["SECRET_KEY"] = "secret"
os.environ["AUDIT_SECRET_KEY"] = "test_audit_secret"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["QDRANT_URL"] = "http://localhost:6333"

# Mock hvac for vault client
mock_hvac = MagicMock()
mock_client = MagicMock()
mock_client.is_authenticated.return_value = True
mock_hvac.Client.return_value = mock_client
sys.modules['hvac'] = mock_hvac

sys.modules['sklearn'] = MagicMock()
sys.modules['sklearn.ensemble'] = MagicMock()
sys.modules['sklearn.pipeline'] = MagicMock()
sys.modules['sklearn.impute'] = MagicMock()
sys.modules['sklearn.preprocessing'] = MagicMock()
sys.modules['sklearn.compose'] = MagicMock()
sys.modules['clickhouse_connect'] = MagicMock()
sys.modules['psycopg'] = MagicMock()
# psycopg2 must be a real module package, not a bare MagicMock: app code does
# `from psycopg2.extras import RealDictCursor`, which fails against a mock
# ("'psycopg2' is not a package"). Register a minimal package stub instead,
# and only when the real driver is unavailable.
try:
    import psycopg2  # noqa: F401
except ImportError:
    import types

    _psycopg2 = types.ModuleType("psycopg2")
    _psycopg2.__path__ = []
    _extras = types.ModuleType("psycopg2.extras")

    class RealDictCursor:  # minimal stand-in; never used to run queries in tests
        pass

    _extras.RealDictCursor = RealDictCursor
    _psycopg2.extras = _extras
    sys.modules["psycopg2"] = _psycopg2
    sys.modules["psycopg2.extras"] = _extras
