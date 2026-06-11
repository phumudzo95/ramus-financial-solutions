"""
Encryption Service — AWS KMS field-level encryption for PII.
Used to encrypt: ID numbers, income, names, phone numbers, bureau responses.
In development (LocalStack) uses a local fallback key.
"""
from __future__ import annotations
import base64
import logging
import os
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


class EncryptionService:
    """
    Wraps AWS KMS for field-level encryption.
    encrypt() → base64-encoded ciphertext string safe to store in DB.
    decrypt() → plaintext string.
    """

    def __init__(self):
        self._kms = boto3.client("kms", region_name=settings.AWS_REGION)
        self._key_id = settings.AWS_KMS_KEY_ID

        # In dev, fall back to local symmetric encryption if KMS unavailable
        self._dev_mode = settings.ENVIRONMENT == "development"

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return ""
        if self._dev_mode:
            return self._dev_encrypt(plaintext)
        try:
            response = self._kms.encrypt(
                KeyId=self._key_id,
                Plaintext=plaintext.encode("utf-8"),
            )
            return base64.b64encode(response["CiphertextBlob"]).decode("utf-8")
        except ClientError as e:
            logger.error("KMS encrypt failed: %s", e)
            # In degraded state, fall back to dev mode with warning
            if self._dev_mode:
                return self._dev_encrypt(plaintext)
            raise

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext:
            return ""
        if self._dev_mode:
            return self._dev_decrypt(ciphertext)
        try:
            blob = base64.b64decode(ciphertext.encode("utf-8"))
            response = self._kms.decrypt(
                CiphertextBlob=blob,
                KeyId=self._key_id,
            )
            return response["Plaintext"].decode("utf-8")
        except ClientError as e:
            logger.error("KMS decrypt failed: %s", e)
            raise

    # ── Dev fallback (Fernet symmetric encryption) ────────────────────────────

    def _get_dev_fernet(self):
        from cryptography.fernet import Fernet
        key = os.environ.get("DEV_ENCRYPTION_KEY", "")
        if not key:
            key = Fernet.generate_key().decode()
            logger.warning("No DEV_ENCRYPTION_KEY set — using ephemeral key (data lost on restart)")
        return Fernet(key.encode() if len(key) != 44 else key.encode())

    def _dev_encrypt(self, plaintext: str) -> str:
        f = self._get_dev_fernet()
        return f.encrypt(plaintext.encode()).decode()

    def _dev_decrypt(self, ciphertext: str) -> str:
        f = self._get_dev_fernet()
        return f.decrypt(ciphertext.encode()).decode()
