import boto3
import pytz
from datetime import datetime
import json
import uuid
import logging

events_client = boto3.client("events")
s3_client = boto3.client("s3")


def create_s3_bucket(username, user_id, region="eu-north-1"):
    prefix = "stretchnote-admin-robot-cache"
    bucket_name = f"{prefix}-{username}-{user_id}"
    try:
        s3_client.create_bucket(
            Bucket=bucket_name, CreateBucketConfiguration={"LocationConstraint": region}
        )
        logging.info(f"Created S3 bucket: {bucket_name} in region {region}")
        return bucket_name
    except s3_client.exceptions.BucketAlreadyExists:
        logging.info(
            f"Bucket name {bucket_name} already exists. Generating a new name."
        )
        return create_s3_bucket(username, f"{user_id}-{str(uuid.uuid4())[:8]}", region)
    except Exception as e:
        logging.error(f"Error creating S3 bucket: {e}")
        raise


def create_user_rule(
    username,
    schedule_time,
    time_zone,
    role_arn,
    bucket_name,
):
    try:
        hour, minute = map(int, schedule_time.split(":"))

        utc_time = datetime(
            2025, 1, 1, hour, minute, tzinfo=pytz.timezone(time_zone)
        ).astimezone(pytz.UTC)
        utc_hour, utc_minute = utc_time.hour, utc_time.minute

        cron_expression = f"cron({utc_minute} {utc_hour} * * ? *)"
        rule_name = f"rule-{username}"

        response = events_client.put_rule(
            Name=rule_name,
            ScheduleExpression=cron_expression,
            State="ENABLED",
            Description=f"Daily rule for user {username}",
        )
        rule_arn = response["RuleArn"]

        events_client.put_targets(
            Rule=rule_name,
            Targets=[
                {
                    "Id": f"target-{username}",
                    "Arn": "arn:aws:lambda:eu-north-1:886351739165:function:TriggerECSTask",
                    "RoleArn": role_arn,
                    "Input": json.dumps(
                        {"Username": username, "BucketName": bucket_name}
                    ),
                }
            ],
        )
        logging.info(f"Created rule {rule_name} with ARN {rule_arn}")
        return rule_arn
    except Exception as e:
        logging.error(f"Error creating user rule for {username}: {e}")
        raise


def update_user_rule_schedule(username, schedule_time, time_zone, state="ENABLED"):
    try:
        hour, minute = map(int, schedule_time.split(":"))

        if time_zone not in pytz.all_timezones:
            raise ValueError(f"Invalid time zone: {time_zone}")

        tz = pytz.timezone(time_zone)
        local_time = tz.localize(datetime(2025, 1, 1, hour, minute))
        utc_time = local_time.astimezone(pytz.UTC)
        utc_hour, utc_minute = utc_time.hour, utc_time.minute

        cron_expression = f"cron({utc_minute} {utc_hour} * * ? *)"

        response = events_client.put_rule(
            Name=f"rule-{username}",
            ScheduleExpression=cron_expression,
            State=state,
            Description=f"Daily rule for user {username} (updated)",
        )
        logging.info(
            f"Updated rule {response['RuleArn']} at {datetime.now().isoformat()}"
        )
        return response["RuleArn"]

    except Exception as e:
        logging.error(f"Error updating rule for {username}: {e}")
        raise
