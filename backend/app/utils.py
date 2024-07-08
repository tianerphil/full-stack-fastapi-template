import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List

import emails  # type: ignore
import jwt
from jinja2 import Template
from jwt.exceptions import InvalidTokenError

from app.core.config import settings
from pydantic import HttpUrl

@dataclass
class EmailData:
    html_content: str
    subject: str


def render_email_template(*, template_name: str, context: dict[str, Any]) -> str:
    template_str = (
        Path(__file__).parent / "email-templates" / "build" / template_name
    ).read_text()
    html_content = Template(template_str).render(context)
    return html_content


def send_email(
    *,
    email_to: str,
    subject: str = "",
    html_content: str = "",
) -> None:
    assert settings.emails_enabled, "no provided configuration for email variables"
    message = emails.Message(
        subject=subject,
        html=html_content,
        mail_from=(settings.EMAILS_FROM_NAME, settings.EMAILS_FROM_EMAIL),
    )
    smtp_options = {"host": settings.SMTP_HOST, "port": settings.SMTP_PORT}
    if settings.SMTP_TLS:
        smtp_options["tls"] = True
    elif settings.SMTP_SSL:
        smtp_options["ssl"] = True
    if settings.SMTP_USER:
        smtp_options["user"] = settings.SMTP_USER
    if settings.SMTP_PASSWORD:
        smtp_options["password"] = settings.SMTP_PASSWORD
    response = message.send(to=email_to, smtp=smtp_options)
    logging.info(f"send email result: {response}")


def generate_test_email(email_to: str) -> EmailData:
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - Test email"
    html_content = render_email_template(
        template_name="test_email.html",
        context={"project_name": settings.PROJECT_NAME, "email": email_to},
    )
    return EmailData(html_content=html_content, subject=subject)


def generate_reset_password_email(email_to: str, email: str, token: str) -> EmailData:
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - Password recovery for user {email}"
    link = f"{settings.server_host}/reset-password?token={token}"
    html_content = render_email_template(
        template_name="reset_password.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "username": email,
            "email": email_to,
            "valid_hours": settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS,
            "link": link,
        },
    )
    return EmailData(html_content=html_content, subject=subject)


def generate_new_account_email(
    email_to: str, username: str, password: str
) -> EmailData:
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - New account for user {username}"
    html_content = render_email_template(
        template_name="new_account.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "username": username,
            "password": password,
            "email": email_to,
            "link": settings.server_host,
        },
    )
    return EmailData(html_content=html_content, subject=subject)


def generate_password_reset_token(email: str) -> str:
    delta = timedelta(hours=settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS)
    now = datetime.utcnow()
    expires = now + delta
    exp = expires.timestamp()
    encoded_jwt = jwt.encode(
        {"exp": exp, "nbf": now, "sub": email},
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    return encoded_jwt


def verify_password_reset_token(token: str) -> str | None:
    try:
        decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return str(decoded_token["sub"])
    except InvalidTokenError:
        return None
# AWS S3 related functions
import boto3
import base64
import io
import uuid
import imghdr
import re
from botocore.exceptions import ClientError
from app.core.config import settings
from urllib.parse import urlparse
from botocore.config import Config

s3_client = boto3.client('s3',
    config=Config(signature_version='s3v4'),
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_REGION
)

def generate_presigned_url(s3_url: str, expiration: int = 3600) -> str:
    parsed_url = urlparse(s3_url)
    bucket_name = parsed_url.netloc.split('.')[0]
    object_key = parsed_url.path.lstrip('/')
    
    presigned_url = s3_client.generate_presigned_url('get_object',
                                Params={'Bucket': bucket_name,
                                        'Key': object_key},
                                ExpiresIn=expiration)
    return presigned_url


def determine_file_type(base64_data: str) -> str:
    try:
        # Check if the string starts with a data URL prefix
        match = re.match(r'data:image/(\w+);base64,', base64_data)
        if match:
            # If it's a data URL, return the image type from the prefix
            return match.group(1)
        
        # If it's not a data URL, try to decode and determine the type
        # Remove any whitespace and newline characters
        base64_data = base64_data.strip()
        
        # Decode the base64 string
        image_data = base64.b64decode(base64_data)
        
        # Use imghdr to determine the image type
        file_type = imghdr.what(None, h=image_data)
        
        return file_type if file_type else "unknown"
    except Exception as e:
        print(f"Error in determine_file_type: {str(e)}")
        return "unknown"
    
def upload_to_s3(media_data: str, is_public: bool = False) -> str:
    try:
        # Decode the base64 string
        file_content = base64.b64decode(media_data)

        # Determine the file type
        file_type = imghdr.what(None, file_content)
        if file_type is None:
            raise ValueError("Unable to determine file type or unsupported image format")

        # Generate a unique filename
        filename = f"{uuid.uuid4()}.{file_type}"

        # Determine the appropriate key based on public/private status
        key = f"{'public' if is_public else 'private'}/{filename}"

        # Set up ExtraArgs
        extra_args = {
            "ContentType": f"image/{file_type}"
        }
        if is_public:
            extra_args["ACL"] = "public-read"

        # Upload the file to S3
        s3_client.upload_fileobj(
            io.BytesIO(file_content), 
            settings.S3_BUCKET_NAME, 
            key,
            ExtraArgs=extra_args
        )

        # Generate and return the S3 URL
        s3_url = f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
        
        return s3_url

    except ValueError as ve:
        raise ve
    except Exception as e:
        raise Exception(f"Error uploading to S3: {str(e)}")

def delete_from_s3(s3_url: str) -> bool:
    try:
        # Parse the S3 URL to extract bucket name and key
        parsed_url = urlparse(s3_url)
        bucket_name = parsed_url.netloc.split('.')[0]
        key = parsed_url.path.lstrip('/')

        # Delete the object
        s3_client.delete_object(Bucket=bucket_name, Key=key)

        # Check if the object still exists
        try:
            s3_client.head_object(Bucket=bucket_name, Key=key)
            # If we can still retrieve the object metadata, deletion failed
            return False
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                # Object not found, which means deletion was successful
                return True
            else:
                # Some other error occurred
                raise

    except ClientError as e:
        print(f"Error deleting object from S3: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

# RunPod serverless related functions
import random
from typing import List
from app.ComfyUIClient import ComfyUIClient
from app.core.config import settings

def generate_media_from_text(request_data: dict) -> List[dict]:
    try:
        client = ComfyUIClient(
            endpoint_url=settings.RUNPOD_ENDPOINT_URL,
            api_key=settings.RUNPOD_API_KEY,
            endpoint_id=settings.RUNPOD_ENDPOINT_ID,
            output_dir=None,  # We don't need local output directory
            input_dir=None    # We don't need local input directory
        )

        # Load and update the workflow
        client.load_workflow(
            filepath=settings.WORKFLOW_TEMPLATE_T2I,  # Assuming you have a text-to-image workflow template
            seed_node_number=3,
            positive_prompt_node_number=6,
            output_node_number=9,
            negative_prompt_node_number=7,
            size_batch_node_number=5
        )

        # Generate a random seed
        seed = random.randint(1, 1500000)

        # Update the seed node
        client.update_seed_node(seed)

        # Update the positive prompt node
        client.update_positive_prompt(request_data['positive_prompt'])

        # Update the negative prompt node (if needed)
        if 'negative_prompt' in request_data and request_data['negative_prompt']:
            client.update_negative_prompt(request_data['negative_prompt'])

        # Update batch size
        client.update_output_batch(request_data['num_outputs'])

        # Request images asynchronously
        response = client.queue_prompt_async()

        if response['status'] == "COMPLETED" and 'output' in response and 'message' in response['output']:
            generated_images = []
            for img_base64 in response['output']['message']:
                output_file_type = determine_file_type(img_base64)
                generated_images.append({
                    "data": img_base64,
                    "file_type": output_file_type,
                    "seed": seed
                })
            return generated_images
        else:
            raise Exception(f"Job failed with status: {response.get('status', 'Unknown')}")

    except Exception as e:
        raise Exception(f"Error in generate_media_from_text: {str(e)}")

def generate_media_from_media(request_data: dict) -> List[dict]:
    try:
        client = ComfyUIClient(
            endpoint_url=settings.RUNPOD_ENDPOINT_URL,
            api_key=settings.RUNPOD_API_KEY,
            endpoint_id=settings.RUNPOD_ENDPOINT_ID,
            output_dir=None,  # We don't need local output directory
            input_dir=None    # We don't need local input directory
        )

        # Load and update the workflow
        client.load_workflow(
            filepath=settings.WORKFLOW_TEMPLATE_I2I,
            load_image_node_number=72,
            seed_node_number=63,
            positive_prompt_node_number=66,
            output_node_number=69,
            negative_prompt_node_number=67,
            size_batch_node_number=65
        )

        # Generate a random seed
        seed = random.randint(1, 1500000)

        # Update the seed node
        client.update_seed_node(seed)

        # Update the positive prompt node (need enhancement logic here)
        client.update_positive_prompt(request_data['positive_prompt'])

        # Update the negative prompt node (need enhancement logic here)
        #client.update_negative_prompt(request_data['negative_prompt'])

        # Update batch size
        client.update_output_batch(request_data['num_outputs'])


        # Determine the input file type
        input_file_type = determine_file_type(request_data['input_image'])

        # update input image in the payload
        client.update_input_image(request_data['input_image'], input_file_type)

        # Request images asynchronously
        response = client.queue_prompt_async()

        if response['status'] == "COMPLETED" and 'output' in response and 'message' in response['output']:
            generated_images = []
            for img_base64 in response['output']['message']:
                output_file_type = determine_file_type(img_base64)
                generated_images.append({
                    "data": img_base64,
                    "file_type": output_file_type,
                    "seed": seed
                })
            return generated_images
        else:
            raise Exception(f"Job failed with status: {response.get('status', 'Unknown')}")

    except Exception as e:
        raise Exception(f"Error in generate_media_from_media: {str(e)}")