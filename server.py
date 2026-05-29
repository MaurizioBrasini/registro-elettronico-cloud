from fastapi import FastAPI, APIRouter, HTTPException, Header, Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal
import uuid
from datetime import datetime, timezone


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="Registro Elettronico Scolastico")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =========================================================
# MODELS
# =========================================================
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


Role = Literal["preside", "maestro", "allievo"]


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    full_name: str
    role: Role
    access_token: str = Field(default_factory=lambda: uuid.uuid4().hex)
    student_id: Optional[str] = None  # populated only for allievi
    created_at: str = Field(default_factory=now_iso)


class UserCreate(BaseModel):
    full_name: str
    role: Role


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[Role] = None


class Student(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    first_name: str
    last_name: str
    birth_date: Optional[str] = None
    family_code: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class StudentCreate(BaseModel):
    first_name: str
    last_name: str


class Attendance(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    student_id: str
    date: str
    status: Literal["presente", "assente", "ritardo", "uscita_anticipata"]
    note: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class AttendanceCreate(BaseModel):
    student_id: str
    date: str
    status: Literal["presente", "assente", "ritardo", "uscita_anticipata"]
    note: Optional[str] = None


class Grade(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    student_id: str
    subject: str
    value: float
    type: Literal["orale", "scritto", "pratico"] = "orale"
    description: Optional[str] = None
    date: str
    created_at: str = Field(default_factory=now_iso)


class GradeCreate(BaseModel):
    student_id: str
    subject: str
    value: float
    type: Literal["orale", "scritto", "pratico"] = "orale"
    description: Optional[str] = None
    date: str


class DisciplinaryNote(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    student_id: str
    note_type: Literal["positiva", "negativa"]
    text: str
    date: str
    author: str = "Prof."
    created_at: str = Field(default_factory=now_iso)


class DisciplinaryNoteCreate(BaseModel):
    student_id: str
    note_type: Literal["positiva", "negativa"]
    text: str
    date: str
    author: Optional[str] = "Prof."


class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    content: str
    target: str = "classe"
    author: str = "Prof."
    date: str
    created_at: str = Field(default_factory=now_iso)


class MessageCreate(BaseModel):
    title: str
    content: str
    target: Optional[str] = "classe"
    author: Optional[str] = "Prof."
    date: str


class Homework(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    subject: str
    description: str
    date_assigned: str
    date_due: str
    created_at: str = Field(default_factory=now_iso)


class HomeworkCreate(BaseModel):
    subject: str
    description: str
    date_assigned: str
    date_due: str


class ScheduleSlot(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    day: Literal["lunedi", "martedi", "mercoledi", "giovedi", "venerdi"]
    slot: int
    subject: str
    created_at: str = Field(default_factory=now_iso)


class ScheduleSlotCreate(BaseModel):
    day: Literal["lunedi", "martedi", "mercoledi", "giovedi", "venerdi"]
    slot: int
    subject: str


# =========================================================
# AUTH DEPENDENCIES (magic-link tokens)
# =========================================================
async def get_current_user(x_access_token: Optional[str] = Header(default=None)):
    if not x_access_token:
        raise HTTPException(status_code=401, detail="Token mancante")
    user = await db.users.find_one({"access_token": x_access_token}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Token non valido")
    return user


async def require_writer(user=Depends(get_current_user)):
    if user["role"] not in ("preside", "maestro"):
        raise HTTPException(status_code=403, detail="Solo maestri o preside possono modificare")
    return user


async def require_preside(user=Depends(get_current_user)):
    if user["role"] != "preside":
        raise HTTPException(status_code=403, detail="Solo il preside può eseguire questa operazione")
    return user


# =========================================================
# HELPERS
# =========================================================
async def _list(collection: str, query: dict = None) -> list:
    return await db[collection].find(query or {}, {"_id": 0}).to_list(5000)


def _public_user(u: dict) -> dict:
    """Strip secret fields from a user dict (used in non-preside contexts)."""
    return {k: v for k, v in u.items() if k != "access_token"}


# =========================================================
# PUBLIC ENDPOINTS
# =========================================================
@api_router.get("/")
async def root():
    return {"message": "Registro Elettronico API", "version": "2.0"}


@api_router.get("/auth/me")
async def auth_me(token: str):
    """Public: resolve a magic-link token into a user identity."""
    user = await db.users.find_one({"access_token": token}, {"_id": 0})
    if not user:
        raise HTTPException(404, "Token non riconosciuto. Chiedi un nuovo link al preside.")
    return user  # includes own access_token; caller already has it


# =========================================================
# USER MANAGEMENT (preside only)
# =========================================================
@api_router.get("/users", response_model=List[User])
async def list_users(user=Depends(require_preside)):
    return await _list("users")


@api_router.post("/users", response_model=User)
async def create_user(payload: UserCreate, user=Depends(require_preside)):
    new_user = User(full_name=payload.full_name, role=payload.role)

    # If allievo, also auto-create a Student record so existing pages work
    if payload.role == "allievo":
        parts = payload.full_name.strip().split(maxsplit=1)
        first = parts[0]
        last = parts[1] if len(parts) > 1 else ""
        student = Student(first_name=first, last_name=last)
        await db.students.insert_one(student.model_dump())
        new_user.student_id = student.id

    await db.users.insert_one(new_user.model_dump())
    return new_user


@api_router.patch("/users/{user_id}", response_model=User)
async def update_user(user_id: str, payload: UserUpdate, user=Depends(require_preside)):
    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Utente non trovato")
    if target["role"] == "preside":
        raise HTTPException(400, "Il preside non può essere modificato")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if updates:
        await db.users.update_one({"id": user_id}, {"$set": updates})
        # If full_name changed and user is allievo, also update linked Student
        if "full_name" in updates and target.get("student_id"):
            parts = updates["full_name"].strip().split(maxsplit=1)
            first = parts[0]
            last = parts[1] if len(parts) > 1 else ""
            await db.students.update_one(
                {"id": target["student_id"]},
                {"$set": {"first_name": first, "last_name": last}},
            )
    updated = await db.users.find_one({"id": user_id}, {"_id": 0})
    return updated


@api_router.delete("/users/{user_id}")
async def delete_user(user_id: str, user=Depends(require_preside)):
    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Utente non trovato")
    if target["role"] == "preside":
        raise HTTPException(400, "Il preside non può essere eliminato")
    await db.users.delete_one({"id": user_id})
    # Cascade: if allievo, delete linked student and their related records
    if target.get("student_id"):
        sid = target["student_id"]
        await db.students.delete_one({"id": sid})
        await db.attendance.delete_many({"student_id": sid})
        await db.grades.delete_many({"student_id": sid})
        await db.notes.delete_many({"student_id": sid})
    return {"deleted": 1}


@api_router.post("/users/{user_id}/regenerate-token", response_model=User)
async def regenerate_token(user_id: str, user=Depends(require_preside)):
    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Utente non trovato")
    new_token = uuid.uuid4().hex
    await db.users.update_one({"id": user_id}, {"$set": {"access_token": new_token}})
    target["access_token"] = new_token
    return target


# =========================================================
# STUDENTS  (read: any role; write: preside only)
# =========================================================
@api_router.get("/students", response_model=List[Student])
async def list_students(user=Depends(get_current_user)):
    return await _list("students")


@api_router.post("/students", response_model=Student)
async def create_student(payload: StudentCreate, user=Depends(require_preside)):
    s = Student(**payload.model_dump())
    await db.students.insert_one(s.model_dump())
    return s


@api_router.delete("/students/{student_id}")
async def delete_student(student_id: str, user=Depends(require_preside)):
    res = await db.students.delete_one({"id": student_id})
    await db.attendance.delete_many({"student_id": student_id})
    await db.grades.delete_many({"student_id": student_id})
    await db.notes.delete_many({"student_id": student_id})
    # also remove linked allievo user if any
    await db.users.delete_many({"student_id": student_id})
    return {"deleted": res.deleted_count}


# =========================================================
# ATTENDANCE
# =========================================================
@api_router.get("/attendance", response_model=List[Attendance])
async def list_attendance(
    date: Optional[str] = None,
    student_id: Optional[str] = None,
    user=Depends(get_current_user),
):
    q = {}
    if date:
        q["date"] = date
    if student_id:
        q["student_id"] = student_id
    return await _list("attendance", q)


@api_router.post("/attendance", response_model=Attendance)
async def create_attendance(payload: AttendanceCreate, user=Depends(require_writer)):
    existing = await db.attendance.find_one(
        {"student_id": payload.student_id, "date": payload.date}, {"_id": 0}
    )
    if existing:
        await db.attendance.update_one(
            {"id": existing["id"]},
            {"$set": {"status": payload.status, "note": payload.note}},
        )
        existing.update({"status": payload.status, "note": payload.note})
        return Attendance(**existing)
    a = Attendance(**payload.model_dump())
    await db.attendance.insert_one(a.model_dump())
    return a


# =========================================================
# GRADES
# =========================================================
@api_router.get("/grades", response_model=List[Grade])
async def list_grades(
    student_id: Optional[str] = None,
    subject: Optional[str] = None,
    user=Depends(get_current_user),
):
    q = {}
    if student_id:
        q["student_id"] = student_id
    if subject:
        q["subject"] = subject
    return await _list("grades", q)


@api_router.post("/grades", response_model=Grade)
async def create_grade(payload: GradeCreate, user=Depends(require_writer)):
    g = Grade(**payload.model_dump())
    await db.grades.insert_one(g.model_dump())
    return g


@api_router.delete("/grades/{grade_id}")
async def delete_grade(grade_id: str, user=Depends(require_writer)):
    res = await db.grades.delete_one({"id": grade_id})
    return {"deleted": res.deleted_count}


# =========================================================
# DISCIPLINARY NOTES
# =========================================================
@api_router.get("/notes", response_model=List[DisciplinaryNote])
async def list_notes(student_id: Optional[str] = None, user=Depends(get_current_user)):
    q = {}
    if student_id:
        q["student_id"] = student_id
    return await _list("notes", q)


@api_router.post("/notes", response_model=DisciplinaryNote)
async def create_note(payload: DisciplinaryNoteCreate, user=Depends(require_writer)):
    n = DisciplinaryNote(**payload.model_dump())
    await db.notes.insert_one(n.model_dump())
    return n


@api_router.delete("/notes/{note_id}")
async def delete_note(note_id: str, user=Depends(require_writer)):
    res = await db.notes.delete_one({"id": note_id})
    return {"deleted": res.deleted_count}


# =========================================================
# MESSAGES (BACHECA)
# =========================================================
@api_router.get("/messages", response_model=List[Message])
async def list_messages(target: Optional[str] = None, user=Depends(get_current_user)):
    q = {}
    if target:
        q = {"$or": [{"target": target}, {"target": "classe"}]}
    return await _list("messages", q)


@api_router.post("/messages", response_model=Message)
async def create_message(payload: MessageCreate, user=Depends(require_writer)):
    m = Message(**payload.model_dump())
    await db.messages.insert_one(m.model_dump())
    return m


@api_router.delete("/messages/{msg_id}")
async def delete_message(msg_id: str, user=Depends(require_writer)):
    res = await db.messages.delete_one({"id": msg_id})
    return {"deleted": res.deleted_count}


# =========================================================
# HOMEWORK
# =========================================================
@api_router.get("/homework", response_model=List[Homework])
async def list_homework(subject: Optional[str] = None, user=Depends(get_current_user)):
    q = {}
    if subject:
        q["subject"] = subject
    return await _list("homework", q)


@api_router.post("/homework", response_model=Homework)
async def create_homework(payload: HomeworkCreate, user=Depends(require_writer)):
    h = Homework(**payload.model_dump())
    await db.homework.insert_one(h.model_dump())
    return h


@api_router.delete("/homework/{hw_id}")
async def delete_homework(hw_id: str, user=Depends(require_writer)):
    res = await db.homework.delete_one({"id": hw_id})
    return {"deleted": res.deleted_count}


# =========================================================
# SCHEDULE
# =========================================================
@api_router.get("/schedule", response_model=List[ScheduleSlot])
async def list_schedule(user=Depends(get_current_user)):
    return await _list("schedule")


@api_router.post("/schedule", response_model=ScheduleSlot)
async def create_schedule(payload: ScheduleSlotCreate, user=Depends(require_writer)):
    existing = await db.schedule.find_one(
        {"day": payload.day, "slot": payload.slot}, {"_id": 0}
    )
    if existing:
        await db.schedule.update_one(
            {"id": existing["id"]}, {"$set": {"subject": payload.subject}}
        )
        existing["subject"] = payload.subject
        return ScheduleSlot(**existing)
    s = ScheduleSlot(**payload.model_dump())
    await db.schedule.insert_one(s.model_dump())
    return s


# =========================================================
# REPORT CARD
# =========================================================
@api_router.get("/report-card/{student_id}")
async def get_report_card(student_id: str, user=Depends(get_current_user)):
    student = await db.students.find_one({"id": student_id}, {"_id": 0})
    if not student:
        raise HTTPException(404, "Studente non trovato")
    grades = await db.grades.find({"student_id": student_id}, {"_id": 0}).to_list(5000)
    attendance = await db.attendance.find({"student_id": student_id}, {"_id": 0}).to_list(5000)
    notes = await db.notes.find({"student_id": student_id}, {"_id": 0}).to_list(5000)

    by_subject = {}
    for g in grades:
        by_subject.setdefault(g["subject"], []).append(g["value"])
    averages = {s: round(sum(vs) / len(vs), 2) for s, vs in by_subject.items()}
    absences = sum(1 for a in attendance if a["status"] == "assente")
    delays = sum(1 for a in attendance if a["status"] == "ritardo")
    pos = sum(1 for n in notes if n["note_type"] == "positiva")
    neg = sum(1 for n in notes if n["note_type"] == "negativa")
    overall = round(sum(averages.values()) / len(averages), 2) if averages else 0
    return {
        "student": student,
        "subject_averages": averages,
        "overall_average": overall,
        "absences": absences,
        "delays": delays,
        "positive_notes": pos,
        "negative_notes": neg,
    }


# =========================================================
# DOWNLOAD ENDPOINTS (developer convenience)
# =========================================================
@api_router.get("/download")
async def download_app():
    zip_path = "/app/registro-elettronico-app.zip"
    if not os.path.exists(zip_path):
        raise HTTPException(404, "Pacchetto non disponibile")
    return FileResponse(zip_path, media_type="application/zip", filename="registro-elettronico-app.zip")


@api_router.get("/download-cloud")
async def download_cloud():
    zip_path = "/app/registro-elettronico-cloud.zip"
    if not os.path.exists(zip_path):
        raise HTTPException(404, "Pacchetto cloud non disponibile")
    return FileResponse(zip_path, media_type="application/zip", filename="registro-elettronico-cloud.zip")


# =========================================================
# SEED — preside + default schedule + welcome
# =========================================================
async def seed_initial_data():
    # 1) Preside
    preside_token = os.environ.get("PRESIDE_TOKEN") or uuid.uuid4().hex
    existing = await db.users.find_one({"role": "preside"}, {"_id": 0})
    if not existing:
        preside = User(
            full_name="Gian Lorenzo La Marca",
            role="preside",
            access_token=preside_token,
        )
        await db.users.insert_one(preside.model_dump())
    else:
        # Always sync the preside's token to env (if env provided) so it's recoverable
        if os.environ.get("PRESIDE_TOKEN"):
            await db.users.update_one(
                {"id": existing["id"]},
                {"$set": {"access_token": preside_token}},
            )

    final_preside = await db.users.find_one({"role": "preside"}, {"_id": 0})
    base_url = os.environ.get("PUBLIC_URL", "")
    link_path = f"/#/login/{final_preside['access_token']}"
    full_link = f"{base_url}{link_path}" if base_url else link_path
    logger.info("=" * 70)
    logger.info("PRESIDE LOGIN LINK (Gian Lorenzo La Marca):")
    logger.info("  %s", full_link)
    logger.info("Apri questo URL nel browser per accedere come preside.")
    logger.info("=" * 70)

    # 2) Default schedule
    if await db.schedule.count_documents({}) == 0:
        defaults = {
            "lunedi": ["Italiano", "Italiano", "Matematica", "Musica", "Inglese"],
            "martedi": ["Matematica", "Storia", "Geografia", "Ed. Fisica", "Ed. Fisica"],
            "mercoledi": ["Italiano", "Scienze", "Scienze", "Arte", "Arte"],
            "giovedi": ["Matematica", "Inglese", "Inglese", "Musica", "Religione"],
            "venerdi": ["Italiano", "Storia", "Geografia", "Matematica", "Musica"],
        }
        for day, subjects in defaults.items():
            for idx, subj in enumerate(subjects, start=1):
                slot = ScheduleSlot(day=day, slot=idx, subject=subj)
                await db.schedule.insert_one(slot.model_dump())

    # 3) Welcome message
    if await db.messages.count_documents({}) == 0:
        welcome = Message(
            title="Benvenuti nel nuovo anno scolastico!",
            content=(
                "Cari maestri e allievi, benvenuti nella bacheca del registro elettronico. "
                "Qui troverete tutte le comunicazioni della classe."
            ),
            target="classe",
            author="Il Preside",
            date=datetime.now(timezone.utc).date().isoformat(),
        )
        await db.messages.insert_one(welcome.model_dump())


# =========================================================
# APP WIRING
# =========================================================
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = ROOT_DIR / "static"
if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIR / "static")),
        name="static-assets",
    )

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(STATIC_DIR / "index.html"))


@app.on_event("startup")
async def on_startup():
    await seed_initial_data()


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
