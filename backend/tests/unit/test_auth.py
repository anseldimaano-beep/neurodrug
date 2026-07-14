import pytest
from app.services.auth_service import AuthService, pwd_context


class TestAuthService:
    def test_password_hash_and_verify(self, db_session):
        service = AuthService(db_session)
        hashed = service.get_password_hash("TestPassword123!")
        assert service.verify_password("TestPassword123!", hashed)
        assert not service.verify_password("WrongPassword", hashed)

    def test_create_access_token(self, db_session):
        service = AuthService(db_session)
        token = service.create_access_token({"sub": "42", "role": 1})
        assert isinstance(token, str)
        assert len(token) > 20

    def test_invalid_password_does_not_verify(self, db_session):
        service = AuthService(db_session)
        hashed = service.get_password_hash("correct_password")
        assert not service.verify_password("wrong_password", hashed)
