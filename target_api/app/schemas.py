from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


# ---- auth ----
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    role: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---- readings ----
class Unit(str, Enum):
    mg_dl = "mg/dL"
    mmol_l = "mmol/L"


class Trend(str, Enum):
    rising = "rising"
    falling = "falling"
    steady = "steady"


# Physiologically plausible bounds differ by unit — this cross-field rule is
# the "tricky validation" endpoint. Boundary tests should probe each edge.
_BOUNDS = {
    Unit.mg_dl: (20.0, 600.0),
    Unit.mmol_l: (1.1, 33.3),
}


class ReadingBase(BaseModel):
    value: float
    unit: Unit
    trend: Trend
    note: str | None = Field(default=None, max_length=280)

    @model_validator(mode="after")
    def _check_value_in_range(self):
        low, high = _BOUNDS[self.unit]
        if not (low <= self.value <= high):
            raise ValueError(
                f"value {self.value} out of range for {self.unit.value} "
                f"(expected {low}–{high})"
            )
        return self


class ReadingCreate(ReadingBase):
    taken_at: datetime | None = None


class ReadingUpdate(ReadingBase):
    taken_at: datetime | None = None


class ReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    value: float
    unit: str
    trend: str
    note: str | None
    taken_at: datetime
    created_at: datetime
