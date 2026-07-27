import sys
import os
from unittest.mock import MagicMock

# Add intelligence_engine and project root to sys.path
engine_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
root_dir = os.path.abspath(os.path.join(engine_dir, '..'))
if engine_dir not in sys.path:
    sys.path.insert(0, engine_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)


# Set dummy API keys to avoid Pydantic validation errors in Langchain
os.environ["GEMINI_API_KEY"] = "test-dummy-key"
os.environ["GOOGLE_API_KEY"] = "test-dummy-key"

os.environ["POSTGRES_URL"] = "postgresql://user:password@localhost/db"
os.environ["DATABASE_URL"] = "postgresql://user:password@localhost/db"
os.environ["SOAR_API_KEY"] = "test-soar-key"
os.environ["SOAR_API_ENDPOINT"] = "https://api.test.example.com/v1/containment"
os.environ["NEO4J_AUTH"] = "neo4j/password"
os.environ["KAFKA_BOOTSTRAP_SERVERS"] = "localhost:9092"
os.environ["SECRET_KEY"] = "secret"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["QDRANT_URL"] = "http://localhost:6333"

# Mock sklearn because it cannot be built in this environment
sys.modules['sklearn'] = MagicMock()
sys.modules['sklearn.ensemble'] = MagicMock()
sys.modules['sklearn.pipeline'] = MagicMock()
sys.modules['sklearn.impute'] = MagicMock()
sys.modules['sklearn.preprocessing'] = MagicMock()
sys.modules['sklearn.compose'] = MagicMock()
sys.modules['clickhouse_connect'] = MagicMock()
sys.modules['psycopg'] = MagicMock()
sys.modules['psycopg2'] = MagicMock()
sys.modules['psycopg2.extras'] = MagicMock()

# Mock hvac for vault client
mock_hvac = MagicMock()
mock_client = MagicMock()
mock_client.is_authenticated.return_value = True
mock_hvac.Client.return_value = mock_client
sys.modules['hvac'] = mock_hvac
