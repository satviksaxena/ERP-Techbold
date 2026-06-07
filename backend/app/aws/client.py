from __future__ import annotations

import logging
import boto3
from botocore.exceptions import ClientError
from app.config import Settings

logger = logging.getLogger(__name__)


class AWSClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.aws_access_key_id = settings.aws_access_key_id
        self.aws_secret_access_key = settings.aws_secret_access_key
        self.aws_region = settings.aws_default_region or "us-east-1"

    def get_session(self) -> boto3.Session:
        if self.aws_access_key_id and self.aws_secret_access_key:
            return boto3.Session(
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                region_name=self.aws_region,
            )
        # Fallback to default credentials chain
        return boto3.Session(region_name=self.aws_region)

    def test_connection(self) -> dict[str, str]:
        """Test AWS connection using STS."""
        try:
            session = self.get_session()
            sts = session.client("sts")
            identity = sts.get_caller_identity()
            return {
                "status": "connected",
                "arn": identity.get("Arn", ""),
                "account": identity.get("Account", ""),
                "user_id": identity.get("UserId", ""),
            }
        except ClientError as exc:
            logger.error("AWS connection failed: %s", exc)
            return {"status": "error", "error": str(exc)}
        except Exception as exc:
            logger.error("Unexpected AWS connection error: %s", exc)
            return {"status": "error", "error": str(exc)}
