"""관리자 2단계-B API: 지원자 비교 · 다음 전형 대상자 · 통계 · 운영 현황 (API 명세서 10장, 화면정의서 S-R07~S-R09).

모두 읽기 전용이다. 결과·판정을 바꾸는 입력은 없다 (AC-14).
"""

import re
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import getDb
from ..deps import requireAdmin
from ..domain import status as st
from ..errors import ApiError, notFound
from ..models import Application, AuditLog, InterviewSession, JobPosting, Notification, Question, Result, StatsArchive, User
from ..services import coding_bank
from ..timeutil import asKst, iso, now

router = APIRouter(prefix="/admin")

RESERVE_MINIMUM = 5  # 종류별 예비 질문 최소 개수 (TRD 15장 T-05)
MAIL_FAILED_DAYS = 7
STATS_MONTHS = 12
COUNTED = st.FINAL_STATUSES - {st.NOT_TAKEN_CLOSED}  # 미응시 마감은 통계에서 뺀다 (API 명세서 10장)


def score(value) -> str | None:
    return None if value is None else f"{Decimal(value):.2f}"


EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def maskEmail(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:2]}***@{domain}"


@router.get("/applicants/compare")
def compare(ids: str = Query(..., max_length=200), db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    """2~3명 비교 (ADM-03). 참고용이며 결과는 바뀌지 않는다."""
    appIds = list(dict.fromkeys(i.strip() for i in ids.split(",") if i.strip()))
    if not 2 <= len(appIds) <= 3:
        raise ApiError(400, "COMPARE_COUNT", "2~3명을 골라 주세요.")
    items = []
    for appId in appIds:
        a = db.get(Application, appId)
        if a is None or a.attempt_status == st.DRAFTING:
            raise notFound()
        r = db.query(Result).filter_by(application_id=a.id).first()
        items.append({
            "application_id": a.id, "name": a.user.name, "posting_id": a.posting_id, "posting_title": a.posting.title,
            "attempt_status": a.attempt_status, "analysis_status": a.analysis_status,
            "decision": r.ai_decision if r else None, "total_score": score(r.total_score) if r else None,
            "interview_score": score(r.interview_score) if r else None, "coding_score": score(r.coding_score) if r else None,
            "pass_score": score(r.pass_score) if r else None, "item_scores": r.item_points if r else {},
            "strengths": r.strengths if r else [], "improvements": r.improvements if r else [],
        })
    db.add(AuditLog(actor_id=admin.id, action="applicant.compare", target=",".join(appIds)[:128]))
    db.commit()
    return {"items": items, "same_posting": len({i["posting_id"] for i in items}) == 1}


@router.get("/postings/{postingId}/passed")
def passed(postingId: str, q: str | None = Query(None, max_length=50), db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    """다음 전형 대상자 = 1차 합격자와 연락처 (ADM-06). 삭제 예정일을 함께 알려 그 전에 연락하게 한다."""
    p = db.get(JobPosting, postingId)
    if p is None:
        raise notFound()
    rows = (db.query(Application, Result).join(Result, Result.application_id == Application.id)
            .filter(Application.posting_id == p.id, Result.ai_decision == "pass")
            .order_by(Result.total_score.desc()).all())
    items = [{"application_id": a.id, "name": a.user.name, "email": a.user.email, "phone": a.user.phone,
              "total_score": score(r.total_score), "decided_at": iso(r.decided_at), "purge_at": iso(a.purge_at)}
             for a, r in rows if not q or q.strip() in a.user.name]
    undecided = (db.query(Application).filter(Application.posting_id == p.id, Application.attempt_status.in_(COUNTED),
                                              Application.analysis_status != "decided").count())
    purgeDates = [asKst(a.purge_at) for a, _ in rows if a.purge_at]
    db.add(AuditLog(actor_id=admin.id, action="passed.view", target=p.id))
    db.commit()
    return {"posting": {"posting_id": p.id, "title": p.title, "status": p.status}, "items": items,
            "undecided": undecided, "purge_at": iso(min(purgeDates)) if purgeDates else None}


@router.get("/stats")
def stats(posting_id: str | None = None, db: Session = Depends(getDb), _admin: User = Depends(requireAdmin)):
    """집계 숫자만 (ADM-07). 이름·연락처 없음. 보관 기간이 지나 지운 건은 익명 집계(StatsArchive)에서 더한다."""
    base = db.query(Application).filter(Application.attempt_status != st.DRAFTING)
    if posting_id:
        base = base.filter(Application.posting_id == posting_id)
    scope = base.with_entities(Application.id).subquery()
    apps = base.with_entities(Application.id, Application.posting_id, Application.attempt_status, Application.completed_at,
                              Application.end_detail).all()
    results = {row.application_id: row for row in db.query(Result.application_id, Result.total_score, Result.ai_decision, Result.item_points)
               .join(scope, scope.c.id == Result.application_id)}
    sessions = Counter(dict(db.query(InterviewSession.application_id, func.count()).join(scope, scope.c.id == InterviewSession.application_id)
                            .group_by(InterviewSession.application_id).all()))
    titles = dict(db.query(JobPosting.id, JobPosting.title).all())
    current = asKst(now())
    monthStart = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    taken = [a for a in apps if a.attempt_status in COUNTED]
    decided = [results[a.id] for a in taken if a.id in results]
    months = []
    for back in range(STATS_MONTHS - 1, -1, -1):
        year, month = divmod(current.year * 12 + current.month - 1 - back, 12)
        months.append(f"{year:04d}-{month + 1:02d}")
    monthly = Counter(asKst(a.completed_at).strftime("%Y-%m") for a in taken if a.completed_at)
    bins = Counter(min(int(r.total_score) // 10, 9) for r in decided)
    itemSums: dict[str, list] = defaultdict(lambda: [Decimal(0), 0])
    for r in decided:
        for item, value in (r.item_points or {}).items():
            if value is not None:
                itemSums[item][0] += Decimal(str(value))
                itemSums[item][1] += 1
    # 공고별 [응시, 판정, 합격, 총점 합]
    byPosting: dict[str, list] = defaultdict(lambda: [0, 0, 0, Decimal(0)])
    for a in taken:
        group = byPosting[a.posting_id]
        group[0] += 1
        if a.id in results:
            group[1] += 1
            group[2] += int(results[a.id].ai_decision == "pass")
            group[3] += Decimal(results[a.id].total_score)
    totals = {"applications": len(apps), "taken": len(taken), "decided": len(decided),
              "passed": sum(r.ai_decision == "pass" for r in decided), "total_sum": sum((Decimal(r.total_score) for r in decided), Decimal(0)),
              "resumed": sum(max(sessions.get(a.id, 0) - 1, 0) for a in taken),
              "cheating_cancelled": sum(1 for a in taken if a.attempt_status == st.CANCELLED and a.end_detail == "exit_twice")}
    archived = db.query(StatsArchive)
    if posting_id:
        archived = archived.filter(StatsArchive.posting_id == posting_id)
    for row in archived:  # 보관 기간이 지나 지운 건 (CONFLICTS F1)
        for key in ("applications", "taken", "decided", "passed", "resumed", "cheating_cancelled"):
            totals[key] += getattr(row, key)
        totals["total_sum"] += Decimal(row.total_sum)
        if row.month:
            monthly[row.month] += row.taken
        for i, count in enumerate(row.score_bins or []):
            bins[i] += count
        for item, (itemSum, count) in (row.item_sums or {}).items():
            itemSums[item][0] += Decimal(itemSum)
            itemSums[item][1] += count
        if row.taken:
            group = byPosting[row.posting_id]
            group[0] += row.taken
            group[1] += row.decided
            group[2] += row.passed
            group[3] += Decimal(row.total_sum)
            titles.setdefault(row.posting_id, row.posting_title)
    postings = [{"posting_id": pid, "title": titles.get(pid, ""), "taken": takenCount,
                 "pass_rate": round(100 * passedCount / decidedCount) if decidedCount else None,
                 "average_total": score(totalSum / decidedCount) if decidedCount else None}
                for pid, (takenCount, decidedCount, passedCount, totalSum) in byPosting.items()]
    return {
        "applications": totals["applications"],
        "taken": totals["taken"],
        "taken_this_month": monthly.get(monthStart.strftime("%Y-%m"), 0),
        "completion_rate": round(100 * totals["taken"] / totals["applications"]) if totals["applications"] else None,
        "pass_rate": round(100 * totals["passed"] / totals["decided"]) if totals["decided"] else None,
        "average_total": score(totals["total_sum"] / totals["decided"]) if totals["decided"] else None,
        "item_averages": {item: score(itemSum / count) for item, (itemSum, count) in itemSums.items() if count},
        "score_bins": [{"from": i * 10, "to": i * 10 + 10, "count": bins.get(i, 0)} for i in range(10)],
        "resumed": totals["resumed"],
        "cheating_cancelled": totals["cheating_cancelled"],
        "monthly": [{"month": m, "taken": monthly.get(m, 0)} for m in months],
        "postings": sorted(postings, key=lambda p: -p["taken"]),
    }


@router.get("/ops-status")
def opsStatus(db: Session = Depends(getDb), _admin: User = Depends(requireAdmin)):
    """운영 현황: 확인 필요 건 · 최근 7일 메일 최종 실패 · 문항 수 (화면정의서 S-R09)."""
    review = (db.query(Application).filter(Application.analysis_status == "needs_review")
              .order_by(Application.completed_at).all())
    since = now() - timedelta(days=MAIL_FAILED_DAYS)
    failed = (db.query(Notification, User).join(User, User.id == Notification.user_id)
              .filter(Notification.email_status == "failed", Notification.created_at >= since)
              .order_by(Notification.created_at.desc()).all())
    today = asKst(now()).replace(hour=0, minute=0, second=0, microsecond=0)
    deferred = db.query(Notification).filter(Notification.email_status == "deferred", Notification.created_at >= today).count()
    reserve = dict(db.query(Question.kind, func.count()).filter(Question.source == "reserve", Question.status == "active")
                   .group_by(Question.kind).all())
    bank = db.query(Question).filter(Question.source.in_(("excel", "generated")), Question.status == "active").count()
    levels = Counter(p["level"] for p in coding_bank.PROBLEMS.values())
    return {
        "needs_review": [{"application_id": a.id, "name": a.user.name, "posting_title": a.posting.title,
                          "since": iso(a.completed_at), "reason": a.review_reason} for a in review],
        "mail_failed": {"count": len(failed), "items": [
            {"to": maskEmail(u.email), "kind": n.kind, "title": n.title,
             "reason": EMAIL_PATTERN.sub(lambda m: maskEmail(m.group()), n.email_fail_reason or "") or None, "at": iso(n.created_at)}
            for n, u in failed[:50]]},
        "mail_deferred_today": deferred,
        "questions": {"bank": bank, "reserve_total": sum(reserve.values())},
        "reserve_questions": [{"category": kind, "count": reserve.get(kind, 0), "below_minimum": reserve.get(kind, 0) < RESERVE_MINIMUM}
                              for kind in ("personality", "company", "resume", "job")],
        "coding_problems": dict(levels),
    }
