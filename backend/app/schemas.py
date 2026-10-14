from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    location: str = ""

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    category: str = "Other"
    location: str = ""
    date: str
    price: int = Field(default=0, ge=0)
    total_tickets: int = Field(default=100, ge=1)

class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    location: str = ""
    profile_picture: str = ""

class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
