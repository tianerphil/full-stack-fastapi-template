from datetime import date, datetime
from typing import Optional, List
from enum import Enum
from pydantic import EmailStr, Field as PydanticField, HttpUrl
from sqlmodel import Field, Relationship, SQLModel
from sqlalchemy import String, Column, Integer
from sqlalchemy.types import TypeDecorator

# Custom SQLAlchemy type for HttpUrl
class HttpUrlType(TypeDecorator):
    impl = String

    def process_bind_param(self, value, dialect):
        if value is not None:
            return str(value)

    def process_result_value(self, value, dialect):
        if value is not None:
            return HttpUrl(value)

# Enums
class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"

# Link table for many-to-many relationship between Media and Tag
class MediaTag(SQLModel, table=True):
    media_id: int = Field(foreign_key="media.id", primary_key=True)
    tag_id: int = Field(foreign_key="tag.id", primary_key=True)

# User-related models
class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    hashed_password: str = Field(min_length=8)
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    full_name: str | None = Field(default=None, max_length=255)
    
    media: List["Media"] = Relationship(back_populates="owner", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    subscriptions: List["Subscription"] = Relationship(back_populates="user", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    payment_methods: List["PaymentMethod"] = Relationship(back_populates="user", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    credits: List["Credit"] = Relationship(back_populates="user", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    comments: List["Comment"] = Relationship(back_populates="user")
    credit_transactions: List["CreditTransaction"] = Relationship(back_populates="user")
    generation_jobs: List["GenerationJob"] = Relationship(back_populates="user")

# Tag model
class Tag(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True, max_length=50)
    
    media: List["Media"] = Relationship(back_populates="tags", link_model=MediaTag)

# Media-related models
class Media(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    media_type: MediaType
    file_type: str = Field(max_length=10)
    positive_prompt: str = Field(max_length=1000)
    negative_prompt: str | None = Field(default=None, max_length=1000)
    seed: int = Field(ge=0)
    sd_model: str = Field(max_length=100)
    s3_url: HttpUrl = Field(sa_type=HttpUrlType, max_length=255)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_public: bool = Field(default=False)
    origin_id: int | None = Field(default=None, foreign_key="media.id")
    view_count: int = Field(default=0, sa_column=Column(Integer, default=0))
    thumb_up_count: int = Field(default=0, sa_column=Column(Integer, default=0))
    thumb_down_count: int = Field(default=0, sa_column=Column(Integer, default=0))
    
    owner: User = Relationship(back_populates="media")
    origin: Optional["Media"] = Relationship(back_populates="derived_media", sa_relationship_kwargs={"remote_side": lambda: Media.id})
    derived_media: List["Media"] = Relationship(back_populates="origin")
    tags: List[Tag] = Relationship(back_populates="media", link_model=MediaTag)
    comments: List["Comment"] = Relationship(back_populates="media")
    generation_jobs: List["GenerationJob"] = Relationship(back_populates="media")

# Comment model
class Comment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    media_id: int = Field(foreign_key="media.id")
    content: str = Field(max_length=1000)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    user: User = Relationship(back_populates="comments")
    media: Media = Relationship(back_populates="comments")

# Subscription-related models
class Subscription(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    plan_name: str = Field(max_length=50)
    start_date: date
    end_date: date | None = Field(default=None)
    status: str = Field(max_length=20)
    
    user: User = Relationship(back_populates="subscriptions")

class SubscriptionCreate(SQLModel):
    plan_name: str = Field(max_length=50)
    start_date: date

# Payment-related models
class PaymentMethod(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    type: str = Field(max_length=20)
    last_four: str | None = Field(default=None, max_length=4)
    expiry_date: date | None = Field(default=None)
    
    user: User = Relationship(back_populates="payment_methods")

class PaymentMethodCreate(SQLModel):
    type: str = Field(max_length=20)
    last_four: str = Field(max_length=4)
    expiry_date: date

# Credit-related models
class Credit(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    amount: int = Field(ge=0)
    transaction_date: datetime = Field(default_factory=datetime.utcnow)
    
    user: User = Relationship(back_populates="credits")

class CreditCreate(SQLModel):
    amount: int = Field(ge=0)

class CreditTransaction(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    amount: int = Field(ge=-1000000, le=1000000)  # Allow both positive and negative values
    transaction_type: str = Field(max_length=50)  # e.g., "purchase", "generation", "refund"
    transaction_date: datetime = Field(default_factory=datetime.utcnow)
    description: str = Field(max_length=255)
    
    user: User = Relationship(back_populates="credit_transactions")

    # Note: Implement logic to keep only the latest 100 records per user

# Generation Job model
class GenerationJob(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    media_id: int = Field(foreign_key="media.id")
    credits_consumed: int = Field(ge=0)
    job_type: str = Field(max_length=50)  # e.g., "text_to_image", "image_to_image"
    status: str = Field(max_length=20)  # e.g., "pending", "completed", "failed"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    
    user: User = Relationship(back_populates="generation_jobs")
    media: Media = Relationship(back_populates="generation_jobs")

    # Note: Implement logic to keep only the latest 100 records per user
# Authentication-related models
class Token(SQLModel):
    access_token: str
    token_type: str = Field(default="bearer")

class TokenPayload(SQLModel):
    sub: int | None = Field(default=None)

class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=40)
    new_password: str = Field(min_length=8, max_length=40)

class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=40)

# Generic message model
class Message(SQLModel):
    message: str = Field(max_length=1000)

class UserCreate(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=40)
    full_name: str | None = Field(default=None, max_length=255)

class UserUpdate(SQLModel):
    email: EmailStr | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=40)

class UserPublic(SQLModel):
    id: int
    email: EmailStr
    is_active: bool
    full_name: str | None = Field(default=None, max_length=255)

class UsersPublic(SQLModel):
    data: List[UserPublic]
    count: int = Field(ge=0)

class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=40)
    full_name: str | None = Field(default=None, max_length=255)

class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)

# API request/response models

class MediaResponse(SQLModel):
    id: int
    media_type: MediaType
    file_type: str = Field(max_length=10)
    positive_prompt: str | None = Field(default=None, max_length=1000)
    negative_prompt: str | None = Field(default=None, max_length=1000)
    seed: int = Field(ge=0)
    sd_model: str = Field(max_length=100)
    s3_url: HttpUrl
    created_at: datetime
    is_public: bool
    origin_id: int | None = Field(default=None)
    owner_id: int
    tags: List[str]
    view_count: int
    thumb_up_count: int
    thumb_down_count: int

class UploadMediaRequest(SQLModel):
    media_data: str  # Base64 encoded image or video
    media_type: MediaType
    file_type: str = Field(max_length=10)
    positive_prompt: str | None = Field(default=None, max_length=1000)
    negative_prompt: str | None = Field(default=None, max_length=1000)
    sd_model: str | None = Field(default=None, max_length=100)
    is_public: bool = Field(default=False)
    tags: List[str] = Field(default=[])

class UploadMediaResponse(SQLModel):
    s3_url: HttpUrl

class GetMediaByUserRequest(SQLModel):
    user_id: int
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)
    media_type: MediaType | None = Field(default=None)
    is_public: bool | None = Field(default=None)

class GetMediaByUserResponse(SQLModel):
    media: List[MediaResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=100)

class GenerateMediaFromTextRequest(SQLModel):
    positive_prompt: str | None = Field(default=None, max_length=1000)
    negative_prompt: str | None = Field(default=None, max_length=1000)
    media_type: MediaType
    sd_model: str = Field(max_length=100)
    is_public: bool = Field(default=False)
    tags: List[str] = Field(default=[])
    num_outputs: int = Field(default=1, ge=1, le=10)  # Number of media to generate

class GenerateMediaFromTextResponse(SQLModel):
    generated_media: List[MediaResponse]

class GenerateMediaByMediaRequest(SQLModel):
    origin_s3_url: HttpUrl
    positive_prompt: str | None = Field(default=None, max_length=1000)
    negative_prompt: str | None = Field(default=None, max_length=1000)
    sd_model: str | None = Field(max_length=100)
    is_public: bool = Field(default=False)
    tags: List[str] = Field(default=[])
    num_outputs: int = Field(default=1, ge=1, le=10)  # Number of media to generate

class GenerateMediaByMediaResponse(SQLModel):
    generated_media: List[MediaResponse]

class UpdateMediaRequest(SQLModel):
    positive_prompt: str | None = Field(default=None, max_length=1000)
    negative_prompt: str | None = Field(default=None, max_length=1000)
    is_public: bool | None = Field(default=None)
    tags: List[str] | None = Field(default=None)

class UpdateMediaResponse(MediaResponse):
    pass

class DeleteMediaRequest(SQLModel):
    media_id: int = Field(..., ge=1)

class DeleteMediaResponse(SQLModel):
    success: bool
    message: str = Field(max_length=255)
    deleted_media_id: int = Field(ge=1)

class CommentResponse(SQLModel):
    id: int
    user_id: int
    content: str
    created_at: datetime

class GetCommentsRequest(SQLModel):
    media_id: int
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)

class GetCommentsResponse(SQLModel):
    comments: List[CommentResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=100)

class AddCommentRequest(SQLModel):
    media_id: int
    content: str = Field(max_length=1000)

class AddCommentResponse(CommentResponse):
    pass

class UpdateMediaRatingRequest(SQLModel):
    media_id: int
    rating: int = Field(ge=-1, le=1)  # -1 for thumb down, 0 for neutral, 1 for thumb up

class UpdateMediaRatingResponse(SQLModel):
    success: bool
    message: str
    new_thumb_up_count: int
    new_thumb_down_count: int

class CreditTransactionResponse(SQLModel):
    id: int
    amount: int
    transaction_type: str
    transaction_date: datetime
    description: str

class GetCreditTransactionsRequest(SQLModel):
    user_id: int
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)

class GetCreditTransactionsResponse(SQLModel):
    transactions: List[CreditTransactionResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=100)

class GenerationJobResponse(SQLModel):
    id: int
    user_id: int
    media_id: int
    credits_consumed: int
    job_type: str
    status: str
    created_at: datetime
    completed_at: datetime | None

class GetGenerationJobsRequest(SQLModel):
    user_id: int
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)

class GetGenerationJobsResponse(SQLModel):
    jobs: List[GenerationJobResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=100)