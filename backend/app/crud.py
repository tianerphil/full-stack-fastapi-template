from typing import Any

from sqlmodel import Session, select

from app.core.security import get_password_hash, verify_password
from app.models import User, UserCreate, UserUpdate


def create_user(*, session: Session, user_create: UserCreate) -> User:
    db_obj = User.model_validate(
        user_create, update={"hashed_password": get_password_hash(user_create.password)}
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def update_user(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    extra_data = {}
    if "password" in user_data:
        password = user_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["hashed_password"] = hashed_password
    db_user.sqlmodel_update(user_data, update=extra_data)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


def get_user_by_email(*, session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    session_user = session.exec(statement).first()
    return session_user


def authenticate(*, session: Session, email: str, password: str) -> User | None:
    db_user = get_user_by_email(session=session, email=email)
    if not db_user:
        return None
    if not verify_password(password, db_user.hashed_password):
        return None
    return db_user

# credit related
def has_sufficient_credits(*, session: Session, user_id: int, required_credits: int) -> bool:
    # Query the user's current credit balance
    stmt = select(User.credit_balance).where(User.id == user_id)
    result = session.exec(stmt).first()
    
    if result is None:
        # User not found
        return False
    
    user_credits = result
    
    # Check if the user has enough credits
    return user_credits >= required_credits

# Function to get the user's current credit balance
def get_user_credit_balance(*, session: Session, user_id: int) -> int:
    stmt = select(User.credit_balance).where(User.id == user_id)
    result = session.exec(stmt).first()
    return result if result is not None else 0

# Function to deduct credits
def deduct_user_credits(*, session: Session, user_id: int, amount: int) -> bool:
    user = session.exec(select(User).where(User.id == user_id)).first()
    if user is None:
        return False
    
    if user.credit_balance < amount:
        return False
    
    user.credit_balance -= amount
    session.add(user)
    session.commit()
    return True