import os
import sys
import asyncio
import base64
from cryptography.fernet import Fernet
import logging

# Add backend and intelligence_engine to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../intelligence_engine")))

from app.core.config import settings
from app.infrastructure.database import AsyncSessionLocal, engine
from app.domain.models import TenantKeyStore, WebhookEndpoint, Tenant
from core.crypto import envelope_crypto
from sqlalchemy import select, text

logger = logging.getLogger(__name__)

async def migrate_secrets():
    # 1. Prepare fernet
    fernet_key = settings.SECRET_KEY.encode()
    if len(fernet_key) < 32:
        fernet_key = fernet_key.ljust(32, b'0')
    fernet_key = base64.urlsafe_b64encode(fernet_key[:32])
    fernet = Fernet(fernet_key)

    async with AsyncSessionLocal() as db:
        # 2. Create tenant_key_store table if not exists (using raw sql)
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS tenant_key_store (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL REFERENCES tenants(id) UNIQUE,
                encrypted_dek VARCHAR(2048) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            ALTER TABLE tenant_key_store ENABLE ROW LEVEL SECURITY;
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies WHERE policyname = 'tenant_isolation_key_store' AND tablename = 'tenant_key_store'
                ) THEN
                    CREATE POLICY tenant_isolation_key_store ON tenant_key_store
                        USING (tenant_id = current_setting('rls.tenant_id')::int);
                END IF;
            END
            $$;
        """))
        await db.commit()

        # 3. Process webhooks
        result = await db.execute(select(WebhookEndpoint))
        webhooks = result.scalars().all()

        for wh in webhooks:
            # We assume it is encrypted with Fernet
            try:
                decrypted_secret = fernet.decrypt(wh.secret.encode()).decode()
            except Exception as e:
                logger.warning(f"Failed to decrypt webhook {wh.id} with Fernet: {e}. Skipping.")
                continue
            
            # Re-encrypt with EnvelopeCryptoService
            try:
                # EnvelopeCryptoService creates a TenantKeyStore entry if it doesn't exist
                new_encrypted = await envelope_crypto.encrypt_async(wh.tenant_id, decrypted_secret, db)
                wh.secret = new_encrypted
                db.add(wh)
            except Exception as e:
                logger.error(f"Failed to encrypt webhook {wh.id} with EnvelopeCryptoService: {e}")
        
        await db.commit()
        logger.info("Successfully migrated webhook secrets to AES-256-GCM via Vault DEK.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate_secrets())
