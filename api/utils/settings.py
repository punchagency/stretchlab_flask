import boto3

s3 = boto3.client("s3")

BUCKET_NAME = "stretchlabprofilepicture"


def save_image_to_s3(
    image_data, image_name, content_type="image/jpeg", region_name="eu-north-1"
):
    try:
        s3.upload_fileobj(
            Fileobj=image_data,
            Bucket=BUCKET_NAME,
            Key=image_name,
            ExtraArgs={
                "ContentType": content_type,
                # "ACL": "public-read",
            },
        )

        image_url = f"https://{BUCKET_NAME}.s3.{region_name}.amazonaws.com/{image_name}"
        return {"status": "success", "url": image_url}

    except Exception as e:
        return {"status": "error", "message": str(e)}


def delete_image_from_s3(image_name):
    try:
        s3.delete_object(Bucket=BUCKET_NAME, Key=image_name)
        return {"status": "success", "message": "Image deleted successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
