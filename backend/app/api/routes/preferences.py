"""User preferences endpoints (spec §11.2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...db.session import get_db
from ...models import User
from ...schemas.schemas import PreferencesOut, PreferencesPatch
from ...services.domain import get_preferences
from ..deps import get_current_user

router = APIRouter(prefix="/users", tags=["preferences"])


@router.get("/me/preferences", response_model=PreferencesOut)
def read_preferences(user: User = Depends(get_current_user),
                     session: Session = Depends(get_db)) -> PreferencesOut:
    return PreferencesOut.model_validate(get_preferences(session, user))


@router.patch("/me/preferences", response_model=PreferencesOut)
def patch_preferences(body: PreferencesPatch, user: User = Depends(get_current_user),
                      session: Session = Depends(get_db)) -> PreferencesOut:
    pref = get_preferences(session, user)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(pref, field, value)
    session.commit()
    return PreferencesOut.model_validate(pref)
