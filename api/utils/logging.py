import logging
import boto3
import os
from botocore.exceptions import ClientError
from datetime import datetime


class S3LogHandler(logging.Handler):
    def __init__(
        self,
        bucket_name,
        log_prefix="logs/",
    ):
        super().__init__()
        self.bucket_name = bucket_name
        self.log_prefix = log_prefix
        self.s3_client = boto3.client("s3")

    def emit(self, record):
        try:
            log_entry = self.format(record)
            now = datetime.now().strftime("%Y-%m-%d")
            log_file_name = f"{self.log_prefix}{now}.log"
            try:
                obj = self.s3_client.get_object(
                    Bucket=self.bucket_name, Key=log_file_name
                )
                existing_log = obj["Body"].read().decode("utf-8")
            except self.s3_client.exceptions.NoSuchKey:
                existing_log = ""
            except ClientError as e:
                if e.response["Error"]["Code"] == "NoSuchKey":
                    existing_log = ""
                else:
                    raise
            new_log = existing_log + log_entry + "\n"
            self.s3_client.put_object(
                Bucket=self.bucket_name, Key=log_file_name, Body=new_log.encode("utf-8")
            )
        except Exception:
            self.handleError(record)


def init_logging(log_level=logging.INFO):
    logger = logging.getLogger()
    logger.setLevel(log_level)

    s3_bucket = os.environ.get("LOG_S3_BUCKET")
    if s3_bucket:
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
        )
        s3_handler = S3LogHandler(bucket_name=s3_bucket)
        s3_handler.setLevel(log_level)
        s3_handler.setFormatter(formatter)
        logger.addHandler(s3_handler)
    else:
        raise RuntimeError(
            "LOG_S3_BUCKET environment variable must be set for S3 logging."
        )

    return logger
