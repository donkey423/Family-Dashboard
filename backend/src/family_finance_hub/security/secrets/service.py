from datetime import date
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import DocumentSecurityProfile, SecretProfile
from .ports import SecretStore


PERSONAL_UNLOCK_ID = "personal-unlock"


class SecretProfileService:
    def __init__(self, secret_store: SecretStore):
        self.secret_store = secret_store

    def list_profiles(self, session: Session) -> list[SecretProfile]:
        return list(session.scalars(select(SecretProfile).order_by(SecretProfile.created_at.desc())))

    def create_profile(
        self,
        session: Session,
        display_name: str,
        national_id: str,
        birthday: date,
    ) -> SecretProfile:
        display_name = display_name.strip()
        national_id = national_id.strip().upper()
        if not display_name or not national_id:
            raise ValueError("Profile name and national ID must not be empty")
        profile_id = str(uuid4())
        national_id_ref = f"secret-profile:{profile_id}:national-id"
        birthday_ref = f"secret-profile:{profile_id}:birthday"
        refs_written: list[str] = []
        try:
            self.secret_store.set(national_id_ref, national_id.strip().upper())
            refs_written.append(national_id_ref)
            self.secret_store.set(birthday_ref, birthday.isoformat())
            refs_written.append(birthday_ref)
            profile = SecretProfile(
                id=profile_id,
                display_name=display_name,
                national_id_credential_ref=national_id_ref,
                birthday_credential_ref=birthday_ref,
            )
            with session.begin():
                session.add(profile)
                session.flush()
            return profile
        except Exception:
            for reference in refs_written:
                try:
                    self.secret_store.delete(reference)
                except Exception:
                    pass
            raise

    def get_values(self, profile: SecretProfile) -> tuple[str | None, str | None]:
        return (
            self.secret_store.get(profile.national_id_credential_ref),
            self.secret_store.get(profile.birthday_credential_ref),
        )

    def save_personal_unlock(
        self,
        session: Session,
        national_id: str | None,
        birthday: date | None,
    ) -> SecretProfile:
        national_id = national_id.strip().upper() if national_id is not None else None
        if not national_id and birthday is None:
            raise ValueError("請至少提供身分證字號或出生日期")
        written: list[str] = []
        old_refs: list[str] = []
        try:
            with session.begin():
                profile = session.get(SecretProfile, PERSONAL_UNLOCK_ID)
                if profile is None:
                    profile = SecretProfile(
                        id=PERSONAL_UNLOCK_ID,
                        display_name="個人解鎖資料",
                        national_id_credential_ref=f"personal-unlock:{uuid4()}:id",
                        birthday_credential_ref=f"personal-unlock:{uuid4()}:birthday",
                    )
                    session.add(profile)
                if national_id is not None:
                    new_ref = f"personal-unlock:{uuid4()}:id"
                    self.secret_store.set(new_ref, national_id)
                    written.append(new_ref)
                    old_refs.append(profile.national_id_credential_ref)
                    profile.national_id_credential_ref = new_ref
                if birthday is not None:
                    new_ref = f"personal-unlock:{uuid4()}:birthday"
                    self.secret_store.set(new_ref, birthday.isoformat())
                    written.append(new_ref)
                    old_refs.append(profile.birthday_credential_ref)
                    profile.birthday_credential_ref = new_ref
                if session.get(DocumentSecurityProfile, PERSONAL_UNLOCK_ID) is None:
                    session.add(DocumentSecurityProfile(
                        id=PERSONAL_UNLOCK_ID,
                        display_name="個人解鎖資料",
                        institution="通用",
                        secret_profile_id=PERSONAL_UNLOCK_ID,
                    ))
                session.flush()
        except Exception:
            for reference in written:
                try:
                    self.secret_store.delete(reference)
                except Exception:
                    pass
            raise
        for reference in old_refs:
            try:
                self.secret_store.delete(reference)
            except Exception:
                pass
        return profile
