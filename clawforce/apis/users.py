"""User management endpoints.

- ``GET /api/users`` is open to any authenticated caller and returns only
  ``{id, username}`` so a regular user can pick a person to share with.
- All mutations (create, update role or password, delete) require an admin.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from clawforce.auth import get_current_user, hash_password
from clawforce.core.store.users import VALID_ROLES, UserStore
from clawforce.deps import get_user_store

router = APIRouter(tags=["users"])


class UserPublic(BaseModel):
    id: str
    username: str


class UserAdmin(BaseModel):
    id: str
    username: str
    role: str
    created_at: str


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = "user"


class UserUpdateRequest(BaseModel):
    role: str | None = None
    password: str | None = None


def _require_admin(current: dict) -> None:
    if current.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )


def _require_valid_role(role: str) -> str:
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{role}'. Expected one of: {sorted(VALID_ROLES)}",
        )
    return role


@router.get("/api/users", response_model=list[UserPublic])
def list_users(
    current: dict = Depends(get_current_user),
    store: UserStore = Depends(get_user_store),
):
    """Return id+username for every user. Role and password hash are never exposed
    on this endpoint — callers that need role info must hit ``/api/users/admin``.
    """
    users = store.list_users()
    return [UserPublic(id=u.id, username=u.username) for u in users]


@router.get("/api/users/admin", response_model=list[UserAdmin])
def list_users_admin(
    current: dict = Depends(get_current_user),
    store: UserStore = Depends(get_user_store),
):
    """Admin view of every user, including role and created_at."""
    _require_admin(current)
    users = store.list_users()
    return [
        UserAdmin(id=u.id, username=u.username, role=u.role, created_at=u.created_at) for u in users
    ]


@router.post("/api/users", response_model=UserAdmin, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreateRequest,
    current: dict = Depends(get_current_user),
    store: UserStore = Depends(get_user_store),
):
    _require_admin(current)
    role = _require_valid_role(body.role)
    if not body.username or not body.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="username and password are required",
        )
    try:
        user = store.create_user(
            username=body.username,
            password_hash=hash_password(body.password),
            role=role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return UserAdmin(id=user.id, username=user.username, role=user.role, created_at=user.created_at)


@router.patch("/api/users/{user_id}", response_model=UserAdmin)
def update_user(
    user_id: str,
    body: UserUpdateRequest,
    current: dict = Depends(get_current_user),
    store: UserStore = Depends(get_user_store),
):
    _require_admin(current)
    user = store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    password_hash: str | None = None
    if body.password is not None:
        if not body.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Password cannot be empty"
            )
        password_hash = hash_password(body.password)

    new_role: str | None = None
    if body.role is not None:
        new_role = _require_valid_role(body.role)
        demoting = user.role == "admin" and new_role != "admin"
        # Prevent self-demotion so an admin cannot accidentally lock themselves
        # out of the admin surface; another admin must do it.
        if demoting and user_id == current.get("id"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot change your own admin role; ask another admin",
            )
        # Prevent demoting the last admin.
        if demoting and store.count_admins() <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot demote the last admin user",
            )

    updated = store.update_user(user_id, password_hash=password_hash, role=new_role)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserAdmin(
        id=updated.id,
        username=updated.username,
        role=updated.role,
        created_at=updated.created_at,
    )


@router.delete("/api/users/{user_id}")
def delete_user(
    user_id: str,
    current: dict = Depends(get_current_user),
    store: UserStore = Depends(get_user_store),
):
    _require_admin(current)
    user = store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.role == "admin" and store.count_admins() <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete the last admin user",
        )
    if user_id == current.get("id"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete the currently authenticated user",
        )
    store.delete(user_id)
    return {"ok": True}
