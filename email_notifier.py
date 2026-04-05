import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config import (
    EMAIL_ENABLED,
    EMAIL_SMTP_SERVER,
    EMAIL_SMTP_PORT,
    EMAIL_ADDRESS,
    EMAIL_APP_PASSWORD,
    EMAIL_TO,
)


def send_email(subject, body):
    if not EMAIL_ENABLED:
        print("이메일 비활성화 상태")
        return

    if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD or not EMAIL_TO:
        print("이메일 설정 안됨 (config.py 확인)")
        return

    msg = MIMEMultipart()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        server = smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, EMAIL_TO, msg.as_string())
        server.quit()
        print("이메일 전송 완료")
    except Exception as e:
        print(f"이메일 전송 실패: {e}")


def format_email_body(title, content_lines):
    body = f"[{title}]\n\n"
    for line in content_lines:
        body += f"{line}\n"
    return body
