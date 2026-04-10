from pydantic import BaseModel, Field


class SignupRequest(BaseModel):
    user_id: str = Field(min_length=4, max_length=10)
    name: str = Field(min_length=2, max_length=10)
    email: str
    password: str = Field(min_length=4)
    location: str = Field(default="", max_length=100)
    area: float = 0.0
    farmname: str = ""
    profile: str = ""


class LoginRequest(BaseModel):
    user_id: str
    password: str


class FindIdRequest(BaseModel):
    name: str
    email: str


class FindPasswordRequest(BaseModel):
    user_id: str
    email: str


class ResetPasswordRequest(BaseModel):
    user_id: str
    new_password: str = Field(min_length=4)
    reset_token: str


class UserResponse(BaseModel):
    user_id: str
    name: str
    email: str
    location: str
    area: float
    farmname: str
    profile: str
    status: int
