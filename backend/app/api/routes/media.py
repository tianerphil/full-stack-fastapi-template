from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select, func
from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.models import (
    Media, MediaResponse, UploadMediaRequest, UploadMediaResponse,
    GenerateMediaFromTextRequest, GenerateMediaFromTextResponse,
    GenerateMediaByMediaRequest, GenerateMediaByMediaResponse,
    DeleteMediaResponse, GetMediaByUserRequest, GetMediaByUserResponse,
    UpdateMediaRequest, UpdateMediaResponse, CommentResponse,
    GetCommentsRequest, GetCommentsResponse, AddCommentRequest,
    AddCommentResponse, UpdateMediaRatingRequest, UpdateMediaRatingResponse,
    GenerationJob, GenerationJobResponse, GetGenerationJobsRequest,
    GetGenerationJobsResponse
)
from app.worker import (
    upload_media_to_s3_task, delete_media_from_s3_task,
    generate_media_from_text_task, generate_media_from_media_task
)
from celery.result import AsyncResult

router = APIRouter()

@router.get("/user/{user_id}", response_model=GetMediaByUserResponse)
def get_media_by_user(
    request: GetMediaByUserRequest,
    session: SessionDep,
    current_user: CurrentUser
) -> Any:
    """
    Retrieve media for a specific user.
    """
    if current_user.id != request.user_id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    query = select(Media).where(Media.user_id == request.user_id)
    
    if request.media_type:
        query = query.where(Media.media_type == request.media_type)
    if request.is_public is not None:
        query = query.where(Media.is_public == request.is_public)
    
    total = session.exec(select(func.count()).select_from(query.subquery())).one()
    
    query = query.offset((request.page - 1) * request.per_page).limit(request.per_page)
    media = session.exec(query).all()

    return GetMediaByUserResponse(
        media=[MediaResponse.from_orm(m) for m in media],
        total=total,
        page=request.page,
        per_page=request.per_page
    )

@router.post("/upload", response_model=UploadMediaResponse)
async def upload_media(
    request: UploadMediaRequest,
    current_user: CurrentUser,
    session: SessionDep
):
    task = upload_media_to_s3_task.delay(request.media_data, request.file_type)
    return UploadMediaResponse(task_id=str(task.id))

@router.patch("/{media_id}", response_model=UpdateMediaResponse)
def update_media(
    media_id: int,
    request: UpdateMediaRequest,
    session: SessionDep,
    current_user: CurrentUser  
) -> Any:
    """
    Update media information.
    """
    media = session.get(Media, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    if media.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    update_data = request.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(media, key, value)
    
    if request.tags is not None:
        media.tags = []
        for tag_name in request.tags:
            tag = crud.get_or_create_tag(session, tag_name)
            media.tags.append(tag)

    session.add(media)
    session.commit()
    session.refresh(media)
    
    return UpdateMediaResponse.from_orm(media)

@router.delete("/{media_id}", response_model=DeleteMediaResponse)
async def delete_media(
    media_id: int,
    current_user: CurrentUser,
    session: SessionDep
):
    media = session.get(Media, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    if media.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    task = delete_media_from_s3_task.delay(media.s3_url, media_id)
    return DeleteMediaResponse(success=True, message="Media deletion initiated", task_id=str(task.id))

@router.post("/generate/text", response_model=GenerateMediaFromTextResponse)
async def generate_media_from_text(
    request: GenerateMediaFromTextRequest,
    current_user: CurrentUser,
    session: SessionDep
):
    """
    Generate media from text prompts.
    this is place holder for celery task.
    it should check credit balance first
    get media from rp serverless 
    then calculate the credit cost for the generation. and generate the credit transactions, and generatejob in the tables
    upload the source and generated media to s3 and save the media metadata including tags in the database
    commit the credit transactions
    """
    if not crud.has_sufficient_credits(session, current_user.id, request.num_outputs):
        raise HTTPException(status_code=400, detail="Insufficient credits")

    task = generate_media_from_text_task.delay(request.dict(), current_user.id)
    return GenerateMediaFromTextResponse(task_id=str(task.id))

@router.post("/generate/media", response_model=GenerateMediaByMediaResponse)
async def generate_media_by_media(
    request: GenerateMediaByMediaRequest,
    current_user: CurrentUser,
    session: SessionDep
):
    """
    Generate media based on existing media.
    this is place holder for celery task.
    it should check credit balance first
    get media from rp serverless 
    then deduct the credit cost for the generation. and generate the credit transactions, and generatejob in the tables
    upload the source and generated media to s3 and save the media metadata including tags in the database
    commit the credit transactions
    """
    if not crud.has_sufficient_credits(session, current_user.id, request.num_outputs):
        raise HTTPException(status_code=400, detail="Insufficient credits")

    task = generate_media_from_media_task.delay(request.dict(), current_user.id)
    return GenerateMediaByMediaResponse(task_id=str(task.id))

@router.get("/task/{task_id}")
async def get_task_status(task_id: str):
    task_result = AsyncResult(task_id)
    if task_result.ready():
        if task_result.successful():
            return {"status": "completed", "result": task_result.result}
        else:
            return {"status": "failed", "error": str(task_result.result)}
    else:
        return {"status": "processing"}

@router.get("/{media_id}/comments", response_model=GetCommentsResponse)
def get_comments(
    request: GetCommentsRequest,
    session: SessionDep,
    current_user: CurrentUser  
) -> Any:
    """
    Get comments for a specific media.
    """
    media = session.get(Media, request.media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    query = select(media.comments).offset((request.page - 1) * request.per_page).limit(request.per_page)
    comments = session.exec(query).all()
    total = len(media.comments)

    return GetCommentsResponse(
        comments=[CommentResponse.from_orm(c) for c in comments],
        total=total,
        page=request.page,
        per_page=request.per_page
    )

@router.post("/comment", response_model=AddCommentResponse)
def add_comment(
    request: AddCommentRequest,
    session: SessionDep,
    current_user: CurrentUser  
) -> Any:
    """
    Add a comment to a media.
    """
    media = session.get(Media, request.media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    comment = crud.create_comment(session, current_user.id, request.media_id, request.content)
    return AddCommentResponse.from_orm(comment)

@router.post("/{media_id}/rate", response_model=UpdateMediaRatingResponse)
def update_media_rating(
    media_id: int,
    request: UpdateMediaRatingRequest,
    session: SessionDep,
    current_user: CurrentUser  
) -> Any:
    """
    Update the rating (thumb up/down) for a media.
    """
    media = session.get(Media, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    if request.rating == 1:
        media.thumb_up_count += 1
    elif request.rating == -1:
        media.thumb_down_count += 1

    session.add(media)
    session.commit()
    session.refresh(media)

    return UpdateMediaRatingResponse(
        success=True,
        message="Rating updated successfully",
        new_thumb_up_count=media.thumb_up_count,
        new_thumb_down_count=media.thumb_down_count
    )

@router.get("/jobs", response_model=GetGenerationJobsResponse)
def get_generation_jobs(
    request: GetGenerationJobsRequest,
    session: SessionDep,
    current_user: CurrentUser  
) -> Any:
    """
    Get generation jobs for a user.
    """
    if current_user.id != request.user_id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    query = select(GenerationJob).where(GenerationJob.user_id == request.user_id)
    total = session.exec(select(func.count()).select_from(query.subquery())).one()
    
    query = query.offset((request.page - 1) * request.per_page).limit(request.per_page)
    jobs = session.exec(query).all()

    return GetGenerationJobsResponse(
        jobs=[GenerationJobResponse.from_orm(j) for j in jobs],
        total=total,
        page=request.page,
        per_page=request.per_page
    )