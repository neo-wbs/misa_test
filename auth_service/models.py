from dataclasses import dataclass
from enum import Enum

class Role(str, Enum):
    USER  = "user"
    ADMIN = "admin"

# Entity — hat eine ID, kann sich verändern
@dataclass
class User:
    id: int
    email: str
    password_hash: str
    role: Role = Role.USER