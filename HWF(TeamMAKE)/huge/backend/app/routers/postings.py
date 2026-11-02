"""공개 공고 API (API 명세서 4장 GET /postings · /postings/{id} · /job-codes)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import getDb
from ..deps import optionalUser
from ..errors import notFound
from ..models import Application, JobCode, JobPosting, User
from ..services.postings import postingView, revisionsView
from ..timeutil import now

router = APIRouter()


@router.get("/job-codes")
def jobCodes(db: Session = Depends(getDb)):
    rows = db.query(JobCode).order_by(JobCode.sort_order).all()
    return {"items": [{"code": j.code, "name": j.name, "status": j.status} for j in rows]}


@router.get("/postings")
def listPostings(q: str = "", job_code: str = "", page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=50),
                 db: Session = Depends(getDb), user: User | None = Depends(optionalUser)):
    t = now()
    query = db.query(JobPosting).filter(JobPosting.status == "published", JobPosting.open_at <= t, JobPosting.close_at > t)
    if job_code:
        query = query.filter(JobPosting.job_code == job_code)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(JobPosting.title.ilike(like))
    total = query.count()
    rows = query.order_by(JobPosting.close_at.asc()).offset((page - 1) * size).limit(size).all()
    mine = {}
    if user is not None and user.role == "applicant" and rows:
        for a in db.query(Application).filter(Application.user_id == user.id, Application.posting_id.in_([p.id for p in rows])):
            mine[a.posting_id] = a.attempt_status
    items = []
    for p in rows:
        view = postingView(p)
        view["my_attempt_status"] = mine.get(p.id)
        items.append(view)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/postings/{postingId}")
def getPosting(postingId: str, db: Session = Depends(getDb), user: User | None = Depends(optionalUser)):
    p = db.get(JobPosting, postingId)
    if p is None or p.status == "draft":
        raise notFound()
    view = postingView(p)
    view["revisions"] = revisionsView(db, p.id)
    view["server_time"] = now().isoformat(timespec="seconds")
    view["my_application"] = None
    if user is not None and user.role == "applicant":
        a = db.query(Application).filter_by(user_id=user.id, posting_id=p.id).first()
        if a is not None:
            view["my_application"] = {"application_id": a.id, "attempt_status": a.attempt_status}
    return view
