"""사이트 알림 + 메일 (TRD 10장, 테이블 정의서 4-22).

사이트 알림 행은 메일과 상관없이 항상 남는다. 메일은 worker 가 보내고, "잠시 뒤 다시"(4xx)·연결 실패만
60·300·1800초 뒤 최대 3번 다시 보낸다. 영구 오류(5xx)는 바로 실패로 기록한다.
메일에는 알림 문구와 화면 주소만 넣는다 (점수·이유 같은 내용은 넣지 않는다).
"""

import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from .. import db as dbModule
from ..config import ENV
from ..models import Notification, User
from ..timeutil import now

log = logging.getLogger("huge.notify")

MAIL_FROM = "Huge 채용 <noreply@huge.local>"
RETRY_DELAYS_SEC = (60, 300, 1800)


def create(db: Session, userId: str, kind: str, title: str, link: str | None = None, applicationId: str | None = None) -> Notification:
    """알림 행을 만든다(커밋은 호출한 쪽). 메일은 커밋 뒤 queueMail 로 넣는다."""
    row = Notification(user_id=userId, application_id=applicationId, kind=kind, title=title[:200], link=link)
    db.add(row)
    db.flush()
    return row


def exists(db: Session, userId: str, kind: str, applicationId: str | None = None, title: str | None = None) -> bool:
    """같은 알림을 두 번 만들지 않기 위해 (매시 작업이 같은 건을 다시 볼 수 있음)."""
    query = db.query(Notification).filter_by(user_id=userId, kind=kind, application_id=applicationId)
    if title is not None:
        query = query.filter_by(title=title)
    return query.first() is not None


def adminIds(db: Session) -> list[str]:
    return [u.id for u in db.query(User).filter_by(role="admin")]


def mailBody(row: Notification) -> str:
    link = f"{ENV.publicOrigin}{row.link}" if row.link else ENV.publicOrigin
    return f"{row.title}\n\n자세한 내용은 아래 주소에서 로그인해 확인해 주세요.\n{link}\n\n— Huge 채용 (Team AIIT)"


class MailRetry(Exception):
    pass


def sendNow(notificationId: str) -> str:
    """메일 1통. 'sent' · 'failed' · 'skipped'. 다시 보낼 오류는 MailRetry."""
    db = dbModule.SessionLocal()
    try:
        row = db.get(Notification, notificationId)
        if row is None or row.email_status in ("sent", "failed", "skipped"):
            return "skipped"
        user = db.get(User, row.user_id)
        if user is None or not user.email:
            row.email_status = "skipped"
            db.commit()
            return "skipped"
        message = EmailMessage()
        message["From"] = MAIL_FROM
        message["To"] = user.email
        message["Subject"] = " ".join(row.title.split())  # 줄바꿈이 있으면 머리글 오류
        message.set_content(mailBody(row))
        try:
            with smtplib.SMTP(ENV.smtpHost, ENV.smtpPort, timeout=20) as smtp:
                smtp.send_message(message)
        except smtplib.SMTPResponseException as exc:
            if 400 <= exc.smtp_code < 500:
                return retryOrFail(db, row, f"{exc.smtp_code} temporary")
            row.email_status = "failed"
            row.email_fail_reason = f"{exc.smtp_code} {str(exc.smtp_error)[:150]}"
            db.commit()
            return "failed"
        except smtplib.SMTPRecipientsRefused:
            row.email_status = "failed"  # 받는 주소 거부는 다시 보내도 같다
            row.email_fail_reason = "recipient refused"
            db.commit()
            return "failed"
        except (OSError, smtplib.SMTPException) as exc:
            return retryOrFail(db, row, type(exc).__name__)
        row.email_status = "sent"
        row.email_sent_at = now()
        db.commit()
        return "sent"
    finally:
        db.close()


def sendPlain(to: str, subject: str, body: str) -> str:
    """알림 행 없이 보내는 메일 (비밀번호 재설정 — 링크에 토큰이 있어 DB 에 남기지 않는다). 다시 보낼 오류는 MailRetry."""
    message = EmailMessage()
    message["From"] = MAIL_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(ENV.smtpHost, ENV.smtpPort, timeout=20) as smtp:
            smtp.send_message(message)
    except smtplib.SMTPResponseException as exc:
        if 400 <= exc.smtp_code < 500:
            raise MailRetry(exc.smtp_code) from exc
        return "failed"
    except smtplib.SMTPRecipientsRefused:
        return "failed"
    except (OSError, smtplib.SMTPException) as exc:
        raise MailRetry(type(exc).__name__) from exc
    return "sent"


def retryOrFail(db: Session, row: Notification, reason: str) -> str:
    if row.email_retry_count >= len(RETRY_DELAYS_SEC):
        row.email_status = "failed"
        row.email_fail_reason = reason[:200]
        db.commit()
        return "failed"
    row.email_retry_count += 1
    row.email_fail_reason = reason[:200]
    db.commit()
    raise MailRetry(RETRY_DELAYS_SEC[row.email_retry_count - 1])
