from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Reading, User
from ..schemas import ReadingCreate, ReadingOut, ReadingUpdate

router = APIRouter(prefix="/readings", tags=["readings"])


def _get_owned_or_404(reading_id: int, user: User, db: Session) -> Reading:
    reading = db.get(Reading, reading_id)
    if reading is None:
        raise HTTPException(status_code=404, detail="Reading not found")
    # Permission: a user may only touch their own readings; admins may touch any.
    if reading.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not your reading")
    return reading


@router.post("", response_model=ReadingOut, status_code=status.HTTP_201_CREATED)
def create_reading(
    payload: ReadingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = payload.model_dump(exclude_none=True)
    reading = Reading(user_id=user.id, **data)
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


@router.get("", response_model=list[ReadingOut])
def list_readings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    q = db.query(Reading)
    if user.role != "admin":
        q = q.filter(Reading.user_id == user.id)
    return (
        q.order_by(Reading.taken_at.desc()).offset(offset).limit(limit).all()
    )


@router.get("/{reading_id}", response_model=ReadingOut)
def get_reading(
    reading_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _get_owned_or_404(reading_id, user, db)


@router.put("/{reading_id}", response_model=ReadingOut)
def update_reading(
    reading_id: int,
    payload: ReadingUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    reading = _get_owned_or_404(reading_id, user, db)
    for field, val in payload.model_dump(exclude_none=True).items():
        setattr(reading, field, val)
    db.commit()
    db.refresh(reading)
    return reading


@router.delete("/{reading_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reading(
    reading_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    reading = _get_owned_or_404(reading_id, user, db)
    db.delete(reading)
    db.commit()
