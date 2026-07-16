import sys
import os
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# Set dummy API keys to avoid Pydantic validation errors in Langchain
os.environ["GEMINI_API_KEY"] = "test-dummy-key"
os.environ["GOOGLE_API_KEY"] = "test-dummy-key"

# Mock sklearn because it cannot be built in this environment
sys.modules['sklearn'] = MagicMock()
sys.modules['sklearn.ensemble'] = MagicMock()
sys.modules['sklearn.pipeline'] = MagicMock()
sys.modules['sklearn.impute'] = MagicMock()
sys.modules['sklearn.preprocessing'] = MagicMock()
sys.modules['sklearn.compose'] = MagicMock()
sys.modules['clickhouse_connect'] = MagicMock()
