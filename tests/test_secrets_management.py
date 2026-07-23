import pytest
import os
import base64
from unittest.mock import patch, MagicMock, AsyncMock, ANY
from sqlalchemy.ext.asyncio import AsyncSession
from cryptography.fernet import Fernet
import httpx

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../intelligence_engine")))

# Mock hvac client at the top level to avoid module import failure
import hvac
mock_hvac = MagicMock()
mock_hvac.Client.return_value.is_authenticated.return_value = True
patch_hvac = patch('hvac.Client', return_value=mock_hvac.Client.return_value)
patch_hvac.start()

os.environ["POSTGRES_URL"] = "postgresql+asyncpg://mock:mock@localhost/mock"
os.environ["NEO4J_AUTH"] = "mock/mock"
os.environ["SECRET_KEY"] = "mockmockmockmockmockmockmockmock"


from intelligence_engine.core.secrets_provider import VaultClient, SecretsManager
from intelligence_engine.core.crypto import EnvelopeCryptoService
from backend.app.domain.models import WebhookEndpoint, TenantKeyStore
import importlib
from intelligence_engine.core.webhook_delivery import deliver_webhook

# 1. Vault fallback and failing closed
def test_secrets_manager_fail_closed():
    # If vault variables are missing or auth fails, it should raise RuntimeError
    with patch.dict(os.environ, {"TESTING": "false", "ENABLE_VAULT": "true"}, clear=True):
        with patch('intelligence_engine.core.secrets_provider.hvac.Client') as MockClient:
            mock_client_instance = MockClient.return_value
            mock_client_instance.is_authenticated.return_value = False
            
            # Save original instance to restore later
            original_instance = SecretsManager._instance
            SecretsManager._instance = None
            
            with pytest.raises(RuntimeError, match="Vault initialization failed, failing closed."):
                sm = SecretsManager()
                
            SecretsManager._instance = original_instance

# 2. EnvelopeCryptoService - Tenant isolation and AES-256-GCM
@pytest.mark.asyncio
async def test_envelope_crypto_tenant_isolation():
    mock_db = AsyncMock(spec=AsyncSession)
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = mock_result
    
    with patch('intelligence_engine.core.crypto.secrets_manager') as mock_sm:
        mock_sm.vault_client.encrypt.return_value = "encrypted_dek_mock"
        
        svc = EnvelopeCryptoService()
        
        tenant_1 = 101
        tenant_2 = 102
        
        # Test encryption for tenant 1
        data = "super_secret_webhook_key"
        encrypted_1 = await svc.encrypt_async(tenant_1, data, mock_db)
        
        # Ensure it decrypts properly for tenant 1
        # The cache has the DEK now
        decrypted_1 = await svc.decrypt_async(tenant_1, encrypted_1, mock_db)
        assert decrypted_1 == bytearray(data.encode('utf-8'))
        
        # For tenant 2, if we try to decrypt tenant 1's data with tenant 2's DEK (AAD mismatch)
        # AESGCM should raise an exception (cryptography.exceptions.InvalidTag)
        from cryptography.exceptions import InvalidTag
        with pytest.raises(InvalidTag):
            await svc.decrypt_async(tenant_2, encrypted_1, mock_db)

# 3. Webhook Delivery unwrap DEK
@pytest.mark.asyncio
async def test_webhook_delivery_unwrap_dek():
    # Test that deliver_webhook successfully unwraps DEK and signs payload
    tenant_id = 1
    url = "https://webhook.site/test"
    secret_encrypted = "mock_encrypted_secret"
    payload = {"alert": "test"}
    history_id = 99
    
    with patch('intelligence_engine.core.webhook_delivery.envelope_crypto.decrypt') as mock_decrypt, \
         patch('intelligence_engine.core.webhook_delivery._update_history_status') as mock_update, \
         patch('intelligence_engine.core.webhook_delivery.httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post, \
         patch('intelligence_engine.core.webhook_delivery.SessionLocal'):
         
        mock_decrypt.return_value = bytearray(b"unwrapped_secret")
        mock_post.return_value.status_code = 200
        
        await deliver_webhook(tenant_id, url, secret_encrypted, payload, history_id)
        
        mock_decrypt.assert_called_once_with(tenant_id, secret_encrypted, ANY)
        mock_post.assert_called_once()
        mock_update.assert_called_once_with(history_id, "delivered", 1, None)

# 4. Migration script correctly converts Fernet to AES-GCM
@pytest.mark.asyncio
async def test_migration_script():
    # Mock settings.SECRET_KEY
    test_key = b"0" * 32
    fernet_key = base64.urlsafe_b64encode(test_key)
    f = Fernet(fernet_key)
    
    original_secret = "my_old_secret"
    encrypted_with_fernet = f.encrypt(original_secret.encode()).decode()
    
    mock_webhook = MagicMock(spec=WebhookEndpoint)
    mock_webhook.id = 1
    mock_webhook.tenant_id = 42
    mock_webhook.secret = encrypted_with_fernet
    
    migration_module = importlib.import_module("backend.migrations.008_phase14_crypto")
    
    with patch.object(migration_module, 'settings') as mock_settings, \
         patch.object(migration_module, 'AsyncSessionLocal') as mock_session_maker, \
         patch.object(migration_module.envelope_crypto, 'encrypt_async') as mock_encrypt:
        
        mock_settings.SECRET_KEY = test_key.decode()
        
        mock_session = AsyncMock()
        mock_session_maker.return_value.__aenter__.return_value = mock_session
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_webhook]
        mock_session.execute.return_value = mock_result
        
        mock_encrypt.return_value = "new_aes_gcm_encrypted_secret"
        
        await migration_module.migrate_secrets()
        
        # Verify envelope crypto was called with the decrypted original secret
        mock_encrypt.assert_called_once_with(42, original_secret, mock_session)
        assert mock_webhook.secret == "new_aes_gcm_encrypted_secret"
        mock_session.add.assert_called_with(mock_webhook)
        mock_session.commit.assert_called()
