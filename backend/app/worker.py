from celery import Celery
from app.core.config import settings
from app.utils import upload_to_s3, delete_from_s3, generate_media_from_text, generate_media_from_media
from app.models import Media, GenerationJob
from sqlmodel import Session
from app.core.db import engine
from app import crud

celery_app = Celery("worker", broker=settings.REDIS_URL)

celery_app.conf.task_routes = {
    "app.worker.upload_media_to_s3_task": "main-queue",
    "app.worker.delete_media_from_s3_task": "main-queue",
    "app.worker.generate_media_from_text_task": "main-queue",
    "app.worker.generate_media_from_media_task": "main-queue",
}

@celery_app.task(name="upload_media_to_s3_task")
def upload_media_to_s3_task(media_data: str, file_type: str):
    s3_url = upload_to_s3(media_data, file_type)
    return s3_url

@celery_app.task(name="delete_media_from_s3_task")
def delete_media_from_s3_task(s3_url: str, media_id: int):
    success = delete_from_s3(s3_url)
    if success:
        with Session(engine) as session:
            media = session.get(Media, media_id)
            if media:
                session.delete(media)
                session.commit()
    return success

@celery_app.task(name="generate_media_from_text_task")
def generate_media_from_text_task(request_data: dict, user_id: int):
    generated_media = generate_media_from_text(request_data, user_id)
    
    with Session(engine) as session:
        new_media_entries = []
        for media in generated_media:
            new_media = Media(
                user_id=user_id,
                media_type=request_data['media_type'],
                file_type=media.file_type,
                positive_prompt=request_data['positive_prompt'],
                negative_prompt=request_data['negative_prompt'],
                seed=media.seed,
                sd_model=request_data['sd_model'],
                s3_url=media.s3_url,
                is_public=request_data['is_public'],
            )
            session.add(new_media)
            new_media_entries.append(new_media)

        session.commit()
        
        for new_media in new_media_entries:
            for tag_name in request_data['tags']:
                tag = crud.get_or_create_tag(session, tag_name)
                new_media.tags.append(tag)
        
        job = GenerationJob(
            user_id=user_id,
            media_id=new_media_entries[0].id,
            credits_consumed=len(new_media_entries),
            job_type="text_to_image",
            status="completed"
        )
        session.add(job)
        session.commit()

    return [media.id for media in new_media_entries]

@celery_app.task(name="generate_media_from_media_task")
def generate_media_from_media_task(request_data: dict, user_id: int):
    generated_media = generate_media_from_media(request_data, user_id, request_data['origin_s3_url'])
    
    with Session(engine) as session:
        new_media_entries = []
        for media in generated_media:
            new_media = Media(
                user_id=user_id,
                media_type=request_data['media_type'],
                file_type=media.file_type,
                positive_prompt=request_data['positive_prompt'],
                negative_prompt=request_data['negative_prompt'],
                seed=media.seed,
                sd_model=request_data['sd_model'],
                s3_url=media.s3_url,
                is_public=request_data['is_public'],
                origin_id=request_data['origin_media_id'],
            )
            session.add(new_media)
            new_media_entries.append(new_media)

        session.commit()
        
        for new_media in new_media_entries:
            for tag_name in request_data['tags']:
                tag = crud.get_or_create_tag(session, tag_name)
                new_media.tags.append(tag)

        job = GenerationJob(
            user_id=user_id,
            media_id=new_media_entries[0].id,
            credits_consumed=len(new_media_entries),
            job_type="image_to_image",
            status="completed"
        )
        session.add(job)
        session.commit()

    return [media.id for media in new_media_entries]