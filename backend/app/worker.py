from datetime import datetime, timezone
import json
from typing import Any, Dict, List
from celery import Celery
from app.core.config import settings
from app.utils import generate_presigned_url, upload_to_s3, delete_from_s3, generate_media_from_text, generate_media_from_media, determine_file_type
from app.models import CreditTransaction, Media, GenerationJob, MediaResponse, MediaType
from sqlmodel import Session
from app.core.db import engine
from app import crud
from app.api.deps import get_db

import logging

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)'
)
logger = logging.getLogger(__name__)

celery_app = Celery("worker", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

celery_app.conf.update(
    task_routes={
        #"app.worker.upload_media_to_s3_task": "main-queue",
        #"app.worker.delete_media_from_s3_task": "main-queue",
        "app.worker.generate_media_from_text_task": "main-queue",
        "app.worker.generate_media_from_media_task": "main-queue",
    },
    worker_hijack_root_logger=False,  # This prevents Celery from hijacking the root logger
    worker_log_format='%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)',
    worker_task_log_format='%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)'
)

# @celery_app.task(name="upload_media_to_s3_task")
# def upload_media_to_s3_task(media_data: str, file_type: str):
#     s3_url = upload_to_s3(media_data, file_type)
#     return s3_url

# @celery_app.task(name="delete_media_from_s3_task")
# def delete_media_from_s3_task(s3_url: str, media_id: int):
#     success = delete_from_s3(s3_url)
#     if success:
#         with Session(engine) as session:
#             media = session.get(Media, media_id)
#             if media:
#                 session.delete(media)
#                 session.commit()
#     return success

@celery_app.task(name="generate_media_from_text_task")
def generate_media_from_text_task(request_data: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    # runpod query
    generated_media = generate_media_from_text(request_data)
    logger.debug(f'Generated media: {len(generated_media)}')
    
    db_generator = get_db()
    
    try:
        session = next(db_generator)
        
        # Create the GenerationJob first
        job = GenerationJob(
            user_id=user_id,
            credits_consumed=request_data['credit_cost'],
            job_type="text_to_image",
            status="completed",
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc)
        )
        session.add(job)
        session.flush()  # This will assign an id to the job

        new_media_entries: List[Media] = []
        for media in generated_media:
            s3_url = upload_to_s3(media['data'])
            
            new_media = Media(
                user_id=user_id,
                media_type=request_data['output_media_type'],
                file_type=media['file_type'],
                positive_prompt=request_data['positive_prompt'],
                negative_prompt=request_data.get('negative_prompt', ''),
                seed=media['seed'],
                sd_model=request_data['sd_model'],
                s3_url=s3_url,
                is_public=request_data['is_public'],
                created_at=datetime.now(timezone.utc),
                generation_job_id=job.id  # Associate with the GenerationJob
            )
            session.add(new_media)
            new_media_entries.append(new_media)
            
        session.flush()

        # prepare response
        generated_media_responses = []
        for media in new_media_entries:
            media_data = media.model_dump()
            media_data['s3_url'] = generate_presigned_url(str(media.s3_url))
            generated_media_responses.append(MediaResponse(**media_data))

        crud.deduct_user_credits(session=session, user_id=user_id, amount=request_data['credit_cost'])
        credit_transaction = CreditTransaction(
            user_id=user_id,
            amount=-request_data['credit_cost'],
            transaction_type="image_generation",
            transaction_date=datetime.now(timezone.utc),
            description=f"Generated {len(new_media_entries)} images from text prompt"
        )
        session.add(credit_transaction)
        session.commit()
        session.refresh(job)
        
        result = {
            "status": "COMPLETED",
            "job_id": job.id,
            "generated_media": [media.model_dump() for media in generated_media_responses],
            "credits_consumed": request_data['credit_cost']
        }

        return result

    except Exception as e:
        session.rollback()
        raise
    finally:
        next(db_generator, None)

@celery_app.task(name="generate_media_from_media_task")
def generate_media_from_media_task(request_data: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    generated_media = generate_media_from_media(request_data)
    logger.debug(f'Generated media: {len(generated_media)}')
    
    db_generator = get_db()
    
    try:
        session = next(db_generator)
        # Determine the input file type
        input_file_type = determine_file_type(request_data['input_image'])
        input_s3_url = upload_to_s3(request_data['input_image'])
        
        # Create the GenerationJob first
        job = GenerationJob(
            user_id=user_id,
            credits_consumed=request_data['credit_cost'],
            job_type="image_to_image",
            status="completed",
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc)
        )
        session.add(job)
        session.flush()  # This will assign an id to the job

        input_media = Media(
            user_id=user_id,
            media_type=MediaType.IMAGE,  # Assuming the input is always an image
            file_type=input_file_type,
            positive_prompt=request_data['positive_prompt'],
            negative_prompt=request_data['negative_prompt'],
            seed=0,
            sd_model=request_data['sd_model'],
            s3_url=input_s3_url,
            is_public=request_data['is_public'],
            created_at=datetime.now(timezone.utc),
            generation_job_id=job.id  # Associate with the GenerationJob
        )
        session.add(input_media)
        session.flush()

        new_media_entries: List[Media] = []
        for media in generated_media:
            s3_url = upload_to_s3(media['data'])
            
            new_media = Media(
                user_id=user_id,
                media_type=request_data['output_media_type'],
                file_type=media['file_type'],
                positive_prompt=request_data['positive_prompt'],
                negative_prompt=request_data['negative_prompt'],
                seed=media['seed'],
                sd_model=request_data['sd_model'],
                s3_url=s3_url,
                is_public=request_data['is_public'],
                origin_id=input_media.id,
                created_at=datetime.now(timezone.utc),
                generation_job_id=job.id  # Associate with the GenerationJob
            )
            session.add(new_media)
            new_media_entries.append(new_media)
            
        session.flush()

        # prepare response
        generated_media_responses = []
        for media in new_media_entries:
            media_data = media.model_dump()
            media_data['s3_url'] = generate_presigned_url(str(media.s3_url))
            generated_media_responses.append(MediaResponse(**media_data))

        crud.deduct_user_credits(session=session, user_id=user_id, amount=request_data['credit_cost'])
        credit_transaction = CreditTransaction(
            user_id=user_id,
            amount=-request_data['credit_cost'],
            transaction_type="image_generation",
            transaction_date=datetime.now(timezone.utc),
            description=f"Generated {len(new_media_entries)} images from input image"
        )
        session.add(credit_transaction)
        session.commit()
        session.refresh(job)
        

        result = {
            "status": "COMPLETED",
            "job_id": job.id,
            #"input_media": input_media_response.model_dump(),
            "generated_media": [media.model_dump() for media in generated_media_responses],
            "credits_consumed": request_data['credit_cost']
        }

        return result

    except Exception as e:
        session.rollback()
        raise
    finally:
        next(db_generator, None)