from datetime import date, datetime, timedelta, timezone

from app.core.security import decode_token


API_PREFIX = "/api/v1"


def assert_ok(response):
    payload = response.json()
    assert response.status_code == 200, payload
    assert payload["code"] == 0, payload
    return payload["data"]


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def register_user(
    client,
    *,
    account: str,
    password: str = "pass1234",
    name: str = "Test User",
    role: str = "student",
    class_id: int | None = None,
    email: str | None = None,
    is_reviewer: bool = False,
):
    response = client.post(
        f"{API_PREFIX}/auth/register",
        json={
            "account": account,
            "password": password,
            "name": name,
            "role": role,
            "class_id": class_id,
            "email": email,
            "is_reviewer": is_reviewer,
        },
    )
    return assert_ok(response)["user"]


def login_user(client, *, account: str, password: str = "pass1234"):
    response = client.post(
        f"{API_PREFIX}/auth/login",
        json={"account": account, "password": password},
    )
    return assert_ok(response)


def upload_file(client, access_token: str, filename: str = "proof.png") -> str:
    response = client.post(
        f"{API_PREFIX}/files/upload",
        headers=auth_headers(access_token),
        files={"file": (filename, b"\x89PNG\r\n\x1a\nmock", "image/png")},
    )
    return assert_ok(response)["file_id"]


def create_application(client, access_token: str, *, award_uid: int = 1, file_id: str | None = None):
    attachments = [{"file_id": file_id}] if file_id else []
    response = client.post(
        f"{API_PREFIX}/applications",
        headers=auth_headers(access_token),
        json={
            "award_uid": award_uid,
            "title": "志愿服务",
            "description": "参与学院志愿活动",
            "occurred_at": date.today().isoformat(),
            "attachments": attachments,
            "category": "innovation",
            "sub_type": "achievement",
            "score": 4.0,
        },
    )
    return assert_ok(response)


def test_upload_analysis_and_ai_audit_use_real_summary(client, monkeypatch):
    from app.core.config import settings

    settings.file_analysis_enabled = True

    def fake_run_document_ocr(_):
        return {
            "ocr_text": "省级志愿服务一等奖证书 Applicant One 学生工作处 2026年04月01日",
            "ocr_pages": [
                {
                    "page_index": 0,
                    "text": "省级志愿服务一等奖证书\nApplicant One\n学生工作处\nApplicant One 2026年04月01日",
                    "width": 600,
                    "height": 800,
                    "lines": [
                        {"text": "省级志愿服务一等奖证书", "score": 0.99, "box": [10, 20, 320, 80]},
                        {"text": "Applicant One", "score": 0.98, "box": [10, 120, 220, 170]},
                        {"text": "学生工作处", "score": 0.97, "box": [360, 600, 520, 680]},
                        {"text": "Applicant One 2026年04月01日", "score": 0.95, "box": [280, 700, 560, 760]},
                    ],
                }
            ],
            "layout_pages": [
                {
                    "page_index": 0,
                    "boxes": [{"label": "seal", "score": 0.99, "coordinate": [330, 560, 560, 720]}],
                }
            ],
        }

    monkeypatch.setattr("app.services.file_analysis_service.run_document_ocr", fake_run_document_ocr)

    register_user(
        client,
        account="stud4001",
        name="Applicant One",
        class_id=301,
        email="stud4001@example.com",
    )
    student_login = login_user(client, account="stud4001")
    student_headers = auth_headers(student_login["access_token"])

    upload_resp = assert_ok(
        client.post(
            f"{API_PREFIX}/files/upload",
            headers=student_headers,
            files={"file": ("省级志愿服务一等奖证书.png", b"mock", "image/png")},
        )
    )
    assert upload_resp["analysis_status"] == "completed"
    assert upload_resp["analysis"]["seal"]["detected"] is True
    file_id = upload_resp["file_id"]

    application = assert_ok(
        client.post(
            f"{API_PREFIX}/applications",
            headers=student_headers,
            json={
                "award_uid": 1,
                "title": "省级志愿服务一等奖",
                "description": "Applicant One 志愿服务材料",
                "occurred_at": date.today().isoformat(),
                "attachments": [{"file_id": file_id}],
                "category": "innovation",
                "sub_type": "achievement",
                "score": 4.0,
            },
        )
    )

    ai_report = assert_ok(client.get(f"{API_PREFIX}/ai-audits/{application['application_id']}/report", headers=student_headers))
    assert ai_report["status"] == "completed"
    assert ai_report["result"] == "pass"
    assert ai_report["identity_check"]["status"] == "matched"
    assert ai_report["consistency_check"]["title_check"]["status"] == "matched"
    assert ai_report["consistency_check"]["level_check"]["status"] == "matched"
    assert ai_report["consistency_check"]["seal_check"]["detected"] is True
    assert ai_report["consistency_check"]["signature_check"]["detected"] is True


def test_auth_and_profile_flow(client):
    user = register_user(
        client,
        account="stud1001",
        name="Student One",
        class_id=301,
        email="stud1001@example.com",
    )
    assert user["account"] == "stud1001"
    assert "password_hash" not in user

    login_data = login_user(client, account="stud1001")
    access_token = login_data["access_token"]
    refresh_token = login_data["refresh_token"]

    me = assert_ok(client.get(f"{API_PREFIX}/users/me", headers=auth_headers(access_token)))
    assert me["account"] == "stud1001"
    assert me["class_id"] == 301

    updated = assert_ok(
        client.put(
            f"{API_PREFIX}/users/me",
            headers=auth_headers(access_token),
            json={"email": "updated@example.com", "phone": "13800000000"},
        )
    )
    assert updated["email"] == "updated@example.com"
    assert updated["phone"] == "13800000000"

    assert_ok(
        client.post(
            f"{API_PREFIX}/auth/change-password",
            headers=auth_headers(access_token),
            json={"old_password": "pass1234", "new_password": "newpass1234"},
        )
    )

    unauthorized = client.get(f"{API_PREFIX}/users/me", headers=auth_headers(access_token))
    assert unauthorized.status_code == 401

    old_login = client.post(
        f"{API_PREFIX}/auth/login",
        json={"account": "stud1001", "password": "pass1234"},
    )
    assert old_login.json()["code"] != 0

    relogin = login_user(client, account="stud1001", password="newpass1234")
    new_access_token = relogin["access_token"]

    assert_ok(
        client.post(
            f"{API_PREFIX}/auth/logout",
            headers=auth_headers(new_access_token),
            json={"refresh_token": relogin["refresh_token"]},
        )
    )
    logged_out = client.get(f"{API_PREFIX}/users/me", headers=auth_headers(new_access_token))
    assert logged_out.status_code == 401

    refresh_resp = client.post(
        f"{API_PREFIX}/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.json()["code"] != 0


def test_application_review_notification_and_ai_flow(client):
    register_user(client, account="teach1001", role="teacher", name="Teacher One")
    teacher_login = login_user(client, account="teach1001")
    teacher_headers = auth_headers(teacher_login["access_token"])

    register_user(
        client,
        account="stud2001",
        name="Applicant One",
        class_id=301,
        email="stud2001@example.com",
    )
    student_login = login_user(client, account="stud2001")
    student_headers = auth_headers(student_login["access_token"])

    file_id = upload_file(client, student_login["access_token"])
    created = create_application(client, student_login["access_token"], file_id=file_id)
    application_id = created["application_id"]

    detail = assert_ok(client.get(f"{API_PREFIX}/applications/{application_id}", headers=student_headers))
    assert detail["attachments"][0]["file_id"] == file_id

    ai_report = assert_ok(client.get(f"{API_PREFIX}/ai-audits/{application_id}/report", headers=student_headers))
    assert ai_report["status"] == "completed"
    assert ai_report["result"] == "pass"

    token_data = assert_ok(
        client.post(
            f"{API_PREFIX}/tokens/reviewer",
            headers=teacher_headers,
            json={"class_ids": [301]},
        )
    )

    register_user(client, account="revi3001", name="Reviewer One", class_id=301)
    reviewer_login = login_user(client, account="revi3001")
    reviewer_headers = auth_headers(reviewer_login["access_token"])

    activated = assert_ok(
        client.post(
            f"{API_PREFIX}/tokens/reviewer/activate",
            headers=reviewer_headers,
            json={"token": token_data["token"]},
        )
    )
    assert activated["is_reviewer"] is True

    pending = assert_ok(client.get(f"{API_PREFIX}/reviews/pending", headers=reviewer_headers))
    assert pending["total"] == 1
    assert pending["list"][0]["application_id"] == application_id

    review_result = assert_ok(
        client.post(
            f"{API_PREFIX}/reviews/{application_id}/decision",
            headers=reviewer_headers,
            json={"decision": "approved", "comment": "材料齐全"},
        )
    )
    assert review_result["status"] == "pending_teacher"

    history = assert_ok(client.get(f"{API_PREFIX}/reviews/history", headers=reviewer_headers))
    assert history["total"] == 1

    rechecked = assert_ok(
        client.post(
            f"{API_PREFIX}/teacher/applications/{application_id}/recheck",
            headers=teacher_headers,
            json={"decision": "approved", "comment": "终审通过", "score": 4.0},
        )
    )
    assert rechecked["status"] == "approved"

    stats = assert_ok(client.get(f"{API_PREFIX}/teacher/statistics", headers=teacher_headers))
    assert stats["total_count"] >= 1
    assert stats["status_summary"]["approved"] >= 1

    queued_email = assert_ok(
        client.post(
            f"{API_PREFIX}/notifications/reject-email",
            headers=teacher_headers,
            json={
                "application_id": application_id,
                "to": "stud2001@example.com",
                "subject": "状态通知",
                "body": "这是一封异步模拟邮件",
            },
        )
    )
    assert queued_email["status"] == "queued"

    email_logs = assert_ok(
        client.get(f"{API_PREFIX}/notifications/email-logs?status=mock_sent", headers=teacher_headers)
    )
    assert email_logs["total"] >= 1

    token_list = assert_ok(client.get(f"{API_PREFIX}/tokens", headers=teacher_headers))
    assert token_list["total"] == 1

    revoke_resp = client.post(f"{API_PREFIX}/tokens/{token_data['token_id']}/revoke", headers=teacher_headers)
    assert_ok(revoke_resp)

    ai_logs = assert_ok(client.get(f"{API_PREFIX}/ai-audits/logs", headers=teacher_headers))
    assert ai_logs["total"] >= 1


def test_export_archive_announcement_appeal_and_system_flow(client):
    register_user(client, account="admin100", role="admin", name="Admin One")
    admin_login = login_user(client, account="admin100")
    admin_headers = auth_headers(admin_login["access_token"])

    register_user(client, account="teach2001", role="teacher", name="Teacher Two")
    teacher_login = login_user(client, account="teach2001")
    teacher_headers = auth_headers(teacher_login["access_token"])

    register_user(client, account="stud4001", name="Student Two", class_id=301, email="stud4001@example.com")
    student_login = login_user(client, account="stud4001")
    student_headers = auth_headers(student_login["access_token"])

    now = datetime.now(timezone.utc)
    export_payload = {
        "scope": "applications",
        "format": "xlsx",
        "filters": {"class_id": 301, "term": "2025-2026-1"},
        "store_to_archive": True,
    }

    export_one = assert_ok(
        client.post(
            f"{API_PREFIX}/archives/exports",
            headers={**teacher_headers, "Idempotency-Key": "archive-export-001"},
            json=export_payload,
        )
    )
    export_two = assert_ok(
        client.post(
            f"{API_PREFIX}/archives/exports",
            headers={**teacher_headers, "Idempotency-Key": "archive-export-001"},
            json=export_payload,
        )
    )
    assert export_one["task_id"] == export_two["task_id"]

    task = assert_ok(client.get(f"{API_PREFIX}/teacher/exports/{export_one['task_id']}", headers=teacher_headers))
    assert task["status"] == "completed"
    assert task["file_url"]

    download = client.get(task["file_url"], headers=teacher_headers)
    assert download.status_code == 200
    assert download.content

    archives = assert_ok(client.get(f"{API_PREFIX}/archives/exports", headers=teacher_headers))
    assert len(archives) == 1
    archive_id = archives[0]["archive_id"]

    archive_detail = assert_ok(client.get(f"{API_PREFIX}/archives/exports/{archive_id}", headers=teacher_headers))
    assert archive_detail["archive_id"] == archive_id

    archive_download = client.get(f"{API_PREFIX}/archives/exports/{archive_id}/download", headers=student_headers)
    assert archive_download.status_code == 200
    assert archive_download.content

    announcement = assert_ok(
        client.post(
            f"{API_PREFIX}/announcements",
            headers=teacher_headers,
            json={
                "title": "2025学年综测公示",
                "archive_id": archive_id,
                "scope": {"grade": 2023, "class_ids": [301]},
                "start_at": (now - timedelta(hours=1)).isoformat(),
                "end_at": (now + timedelta(days=2)).isoformat(),
                "show_fields": ["student_name", "score"],
            },
        )
    )
    announcement_id = announcement["announcement_id"]

    announcement_list = assert_ok(client.get(f"{API_PREFIX}/announcements", headers=student_headers))
    assert len(announcement_list) == 1
    assert announcement_list[0]["announcement_id"] == announcement_id

    appeal = assert_ok(
        client.post(
            f"{API_PREFIX}/appeals",
            headers=student_headers,
            json={
                "announcement_id": announcement_id,
                "content": "对公示结果有异议，申请复核。",
                "attachments": [],
            },
        )
    )
    appeal_id = appeal["id"]

    appeal_list = assert_ok(client.get(f"{API_PREFIX}/appeals", headers=teacher_headers))
    assert appeal_list["total"] == 1

    processed = assert_ok(
        client.post(
            f"{API_PREFIX}/appeals/{appeal_id}/process",
            headers=teacher_headers,
            json={"result": "approved", "result_comment": "已复核并修正"},
        )
    )
    assert processed["status"] == "processed"

    configs = assert_ok(client.get(f"{API_PREFIX}/system/configs", headers=admin_headers))
    assert "categories" in configs

    updated_config = assert_ok(
        client.put(
            f"{API_PREFIX}/system/configs",
            headers=admin_headers,
            json={
                "config_key": "announcement_rules",
                "config_value": {"appeal_deadline_days": 3},
                "description": "announcement config",
            },
        )
    )
    assert updated_config["config_key"] == "announcement_rules"

    award_list = assert_ok(client.get(f"{API_PREFIX}/system/award-dicts", headers=admin_headers))
    assert len(award_list) >= 1

    created_award = assert_ok(
        client.post(
            f"{API_PREFIX}/system/award-dicts",
            headers=admin_headers,
            json={
                "award_uid": 999001,
                "category": "innovation",
                "sub_type": "achievement",
                "award_name": "自定义奖项",
                "score": 2.5,
                "max_score": 2.5,
            },
        )
    )
    award_id = created_award["id"]

    updated_award = assert_ok(
        client.put(
            f"{API_PREFIX}/system/award-dicts/{award_id}",
            headers=admin_headers,
            json={"score": 3.0, "max_score": 3.0, "is_active": True},
        )
    )
    assert updated_award["score"] == 3.0

    delete_response = client.delete(f"{API_PREFIX}/system/award-dicts/{award_id}", headers=admin_headers)
    assert_ok(delete_response)

    logs = assert_ok(client.get(f"{API_PREFIX}/system/logs", headers=admin_headers))
    assert logs["total"] >= 1


def test_real_redis_blacklist_and_idempotency(client_with_redis):
    client, redis_client = client_with_redis

    register_user(client, account="teach9001", role="teacher", name="Teacher Redis")
    teacher_login = login_user(client, account="teach9001")
    teacher_headers = auth_headers(teacher_login["access_token"])

    logout_response = client.post(
        f"{API_PREFIX}/auth/logout",
        headers=teacher_headers,
        json={"refresh_token": teacher_login["refresh_token"]},
    )
    assert_ok(logout_response)

    jti = decode_token(teacher_login["access_token"])["jti"]
    blacklist_key = f"auth:blacklist:{jti}"
    assert redis_client.exists(blacklist_key) == 1

    unauthorized = client.get(f"{API_PREFIX}/users/me", headers=teacher_headers)
    assert unauthorized.status_code == 401

    export_payload = {
        "scope": "applications",
        "format": "xlsx",
        "filters": {"class_id": 301},
        "store_to_archive": False,
    }

    first = assert_ok(
        client.post(
            f"{API_PREFIX}/teacher/exports",
            headers={**auth_headers(login_user(client, account='teach9001', password='pass1234')['access_token']), "Idempotency-Key": "redis-export-001"},
            json=export_payload,
        )
    )
    second = assert_ok(
        client.post(
            f"{API_PREFIX}/teacher/exports",
            headers={**auth_headers(login_user(client, account='teach9001', password='pass1234')['access_token']), "Idempotency-Key": "redis-export-001"},
            json=export_payload,
        )
    )
    assert first["task_id"] == second["task_id"]
    assert redis_client.exists("idempotency:teacher_export:redis-export-001") == 1
    assert redis_client.exists(f"export:{first['task_id']}") == 1
