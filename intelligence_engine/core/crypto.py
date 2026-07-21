import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cachetools import TTLCache
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .secrets_provider import secrets_manager
from backend.app.domain.models import TenantKeyStore
import logging
import ctypes
import sys

logger = logging.getLogger(__name__)

def wipe_memory(b):
    if isinstance(b, bytearray):
        for i in range(len(b)):
            b[i] = 0
    elif isinstance(b, bytes) and b:
        try:
            offset = 32 if sys.maxsize > 2**32 else 16
            ctypes.memset(id(b) + offset, 0, len(b))
        except Exception:
            pass

class EnvelopeCryptoService:
    def __init__(self):
        # Cache plaintext DEK for 10 minutes
        self.dek_cache = TTLCache(maxsize=1000, ttl=600)
        self.transit_key_name = "soc-master-kek"

    def _get_or_create_dek(self, tenant_id: int, db: Session) -> bytearray:
        if tenant_id in self.dek_cache:
            return self.dek_cache[tenant_id]

        keystore = db.query(TenantKeyStore).filter(TenantKeyStore.tenant_id == tenant_id).first()
        if keystore:
            try:
                decrypted_dek_b64 = secrets_manager.vault_client.decrypt(self.transit_key_name, keystore.encrypted_dek)
                plaintext_dek_bytes = base64.b64decode(decrypted_dek_b64)
                plaintext_dek = bytearray(plaintext_dek_bytes)
                wipe_memory(plaintext_dek_bytes)
                self.dek_cache[tenant_id] = plaintext_dek
                return plaintext_dek
            except Exception as e:
                logger.error(f"Failed to decrypt DEK for tenant {tenant_id}: {e}")
                raise RuntimeError("Failed to unwrap DEK") from e

        # Create new DEK (32 bytes)
        plaintext_dek_bytes = os.urandom(32)
        plaintext_dek = bytearray(plaintext_dek_bytes)
        plaintext_dek_b64 = base64.b64encode(plaintext_dek).decode('utf-8')
        wipe_memory(plaintext_dek_bytes)
        
        encrypted_dek = secrets_manager.vault_client.encrypt(self.transit_key_name, plaintext_dek_b64)
        
        new_keystore = TenantKeyStore(tenant_id=tenant_id, encrypted_dek=encrypted_dek)
        db.add(new_keystore)
        db.commit()

        self.dek_cache[tenant_id] = plaintext_dek
        return plaintext_dek

    def encrypt(self, tenant_id: int, data: str, db: Session) -> str:
        dek = self._get_or_create_dek(tenant_id, db)
        aesgcm = AESGCM(dek)
        nonce = os.urandom(12)
        aad = str(tenant_id).encode('utf-8')
        ciphertext = aesgcm.encrypt(nonce, data.encode('utf-8'), aad)
        return base64.b64encode(nonce + ciphertext).decode('utf-8')

    def decrypt(self, tenant_id: int, encrypted_data_b64: str, db: Session) -> bytearray:
        dek = self._get_or_create_dek(tenant_id, db)
        aesgcm = AESGCM(dek)
        encrypted_data = base64.b64decode(encrypted_data_b64)
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        aad = str(tenant_id).encode('utf-8')
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, aad)
        plaintext = bytearray(plaintext_bytes)
        wipe_memory(plaintext_bytes)
        return plaintext

    def evict_cache(self, tenant_id: int):
        if tenant_id in self.dek_cache:
            dek = self.dek_cache[tenant_id]
            wipe_memory(dek)
            del self.dek_cache[tenant_id]

    async def _get_or_create_dek_async(self, tenant_id: int, db: AsyncSession) -> bytearray:
        if tenant_id in self.dek_cache:
            return self.dek_cache[tenant_id]

        result = await db.execute(select(TenantKeyStore).where(TenantKeyStore.tenant_id == tenant_id))
        keystore = result.scalars().first()
        if keystore:
            try:
                decrypted_dek_b64 = secrets_manager.vault_client.decrypt(self.transit_key_name, keystore.encrypted_dek)
                plaintext_dek_bytes = base64.b64decode(decrypted_dek_b64)
                plaintext_dek = bytearray(plaintext_dek_bytes)
                wipe_memory(plaintext_dek_bytes)
                self.dek_cache[tenant_id] = plaintext_dek
                return plaintext_dek
            except Exception as e:
                logger.error(f"Failed to decrypt DEK for tenant {tenant_id}: {e}")
                raise RuntimeError("Failed to unwrap DEK") from e

        plaintext_dek_bytes = os.urandom(32)
        plaintext_dek = bytearray(plaintext_dek_bytes)
        plaintext_dek_b64 = base64.b64encode(plaintext_dek).decode('utf-8')
        wipe_memory(plaintext_dek_bytes)
        
        encrypted_dek = secrets_manager.vault_client.encrypt(self.transit_key_name, plaintext_dek_b64)
        
        new_keystore = TenantKeyStore(tenant_id=tenant_id, encrypted_dek=encrypted_dek)
        db.add(new_keystore)
        await db.commit()

        self.dek_cache[tenant_id] = plaintext_dek
        return plaintext_dek

    async def encrypt_async(self, tenant_id: int, data: str, db: AsyncSession) -> str:
        dek = await self._get_or_create_dek_async(tenant_id, db)
        aesgcm = AESGCM(dek)
        nonce = os.urandom(12)
        aad = str(tenant_id).encode('utf-8')
        ciphertext = aesgcm.encrypt(nonce, data.encode('utf-8'), aad)
        return base64.b64encode(nonce + ciphertext).decode('utf-8')

    async def decrypt_async(self, tenant_id: int, encrypted_data_b64: str, db: AsyncSession) -> bytearray:
        dek = await self._get_or_create_dek_async(tenant_id, db)
        aesgcm = AESGCM(dek)
        encrypted_data = base64.b64decode(encrypted_data_b64)
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        aad = str(tenant_id).encode('utf-8')
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, aad)
        plaintext = bytearray(plaintext_bytes)
        wipe_memory(plaintext_bytes)
        return plaintext

envelope_crypto = EnvelopeCryptoService()
