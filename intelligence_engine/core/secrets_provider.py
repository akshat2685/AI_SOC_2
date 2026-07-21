import os
import hvac
import logging
from cachetools import TTLCache

logger = logging.getLogger(__name__)

class VaultClient:
    def __init__(self, addr: str, role_id: str = None, secret_id: str = None, token: str = None):
        self.client = hvac.Client(url=addr, token=token)
        if role_id and secret_id and not token:
            self.client.auth.approle.login(role_id=role_id, secret_id=secret_id)
        
        if not self.client.is_authenticated():
            raise Exception("Vault authentication failed")

    def get_secret(self, path: str, key: str) -> str:
        response = self.client.secrets.kv.v2.read_secret_version(path=path)
        return response['data']['data'][key]

    def encrypt(self, path: str, plaintext: str) -> str:
        import base64
        encoded = base64.b64encode(plaintext.encode('utf-8')).decode('utf-8')
        response = self.client.secrets.transit.encrypt_data(
            name=path,
            plaintext=encoded
        )
        return response['data']['ciphertext']

    def decrypt(self, path: str, ciphertext: str) -> str:
        import base64
        response = self.client.secrets.transit.decrypt_data(
            name=path,
            ciphertext=ciphertext
        )
        return base64.b64decode(response['data']['plaintext']).decode('utf-8')

class SecretsManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SecretsManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        vault_addr = os.getenv("VAULT_ADDR", "http://localhost:8200")
        vault_role_id = os.getenv("VAULT_ROLE_ID")
        vault_secret_id = os.getenv("VAULT_SECRET_ID")
        vault_token = os.getenv("VAULT_TOKEN")
        
        # In testing we might mock this, but if failing we raise immediately
        try:
            self.vault_client = VaultClient(
                addr=vault_addr,
                role_id=vault_role_id,
                secret_id=vault_secret_id,
                token=vault_token
            )
        except Exception as e:
            logger.error(f"Failed to initialize Vault client: {e}")
            raise RuntimeError("Vault initialization failed, failing closed.") from e

        # 5-minute TTL cache for KV secrets
        self.kv_cache = TTLCache(maxsize=100, ttl=300)

    def get_secret(self, path: str, key: str) -> str:
        cache_key = f"{path}:{key}"
        if cache_key in self.kv_cache:
            return self.kv_cache[cache_key]
        
        try:
            val = self.vault_client.get_secret(path, key)
            self.kv_cache[cache_key] = val
            return val
        except Exception as e:
            logger.error(f"Failed to get secret {key} from {path}: {e}")
            raise RuntimeError(f"Missing critical secret: {key}") from e

secrets_manager = SecretsManager()
