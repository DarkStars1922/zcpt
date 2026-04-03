from datetime import date, datetime, timedelta, timezone

import pytest

API_PREFIX = "/api/v1"


def assert_ok(response):
    payload = response.json()
    assert response.status_code == 200, payload
    assert payload["code"] == 0, payload
    return payload["data"]


def assert_api_code(response, code: int):
    if response.status_code == 401:
        assert code == 401, response.text
        return
    payload = response.json()
    assert response.status_code == 200, payload
    assert payload["code"] == code, payload


def assert_forbidden(response):
    if response.status_code == 401:
        return
    payload = response.json()
    assert response.status_code == 200, payload
    assert payload["code"] == 1003, payload


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
):
    return assert_ok(
        client.post(
            f"{API_PREFIX}/auth/register",
            json={
                "account": account,
                "password": password,
                "name": name,
                "role": role,
                "class_id": class_id,
                "email": email,
            },
        )
    )["user"]


def login_user(client, *, account: str, password: str = "pass1234"):
    return assert_ok(
        client.post(
            f"{API_PREFIX}/auth/login",
            json={"account": account, "password": password},
        )
    )


def upload_file(client, access_token: str, filename: str = "proof.png") -> str:
    return assert_ok(
        client.post(
            f"{API_PREFIX}/files/upload",
            headers=auth_headers(access_token),
            files={"file": (filename, b"\x89PNG\r\n\x1a\nmock", "image/png")},
        )
    )["file_id"]


def create_application(client, access_token: str, *, file_id: str, title: str) -> dict:
    return assert_ok(
        client.post(
            f"{API_PREFIX}/applications",
            headers=auth_headers(access_token),
            json={
                "award_uid": 1,
                "title": title,
                "description": f"description for {title}",
                "occurred_at": date.today().isoformat(),
                "attachments": [{"file_id": file_id}],
                "category": "innovation",
                "sub_type": "achievement",
                "score": 4.0,
            },
        )
    )


@pytest.fixture()
def permission_context(client):
    now = datetime.now(timezone.utc)

    register_user(client, account="admin1", role="admin", name="Admin One")
    register_user(client, account="teacher1", role="teacher", name="Teacher One")
    register_user(client, account="owner301", class_id=301, name="Owner Student", email="owner301@example.com")
    register_user(client, account="peer301", class_id=301, name="Peer Student", email="peer301@example.com")
    register_user(client, account="other302", class_id=302, name="Other Student", email="other302@example.com")
    register_user(client, account="reviewer301", class_id=301, name="Reviewer Student", email="reviewer301@example.com")
    register_user(client, account="activator303", class_id=303, name="Activator Student", email="activator303@example.com")

    admin_login = login_user(client, account="admin1")
    teacher_login = login_user(client, account="teacher1")
    owner_login = login_user(client, account="owner301")
    peer_login = login_user(client, account="peer301")
    other_login = login_user(client, account="other302")
    reviewer_login = login_user(client, account="reviewer301")
    activator_login = login_user(client, account="activator303")

    ctx = {
        "client": client,
        "admin": auth_headers(admin_login["access_token"]),
        "teacher": auth_headers(teacher_login["access_token"]),
        "owner": auth_headers(owner_login["access_token"]),
        "peer": auth_headers(peer_login["access_token"]),
        "other": auth_headers(other_login["access_token"]),
        "reviewer": auth_headers(reviewer_login["access_token"]),
        "activator": auth_headers(activator_login["access_token"]),
        "tokens": {
            "admin": admin_login["access_token"],
            "teacher": teacher_login["access_token"],
            "owner": owner_login["access_token"],
            "peer": peer_login["access_token"],
            "other": other_login["access_token"],
            "reviewer": reviewer_login["access_token"],
            "activator": activator_login["access_token"],
        },
    }

    active_token = assert_ok(
        client.post(
            f"{API_PREFIX}/tokens/reviewer",
            headers=ctx["teacher"],
            json={"class_ids": [301]},
        )
    )
    pending_token = assert_ok(
        client.post(
            f"{API_PREFIX}/tokens/reviewer",
            headers=ctx["teacher"],
            json={"class_ids": [303]},
        )
    )
    assert_ok(
        client.post(
            f"{API_PREFIX}/tokens/reviewer/activate",
            headers=ctx["reviewer"],
            json={"token": active_token["token"]},
        )
    )

    owner_file = upload_file(client, ctx["tokens"]["owner"], "owner.png")
    peer_file = upload_file(client, ctx["tokens"]["peer"], "peer.png")
    other_file = upload_file(client, ctx["tokens"]["other"], "other.png")
    reviewer_file = upload_file(client, ctx["tokens"]["reviewer"], "reviewer.png")

    owner_app = create_application(client, ctx["tokens"]["owner"], file_id=owner_file, title="owner-app")
    peer_app = create_application(client, ctx["tokens"]["peer"], file_id=peer_file, title="peer-app")
    other_app = create_application(client, ctx["tokens"]["other"], file_id=other_file, title="other-app")
    reviewer_self_app = create_application(client, ctx["tokens"]["reviewer"], file_id=reviewer_file, title="reviewer-self")

    assert_ok(
        client.post(
            f"{API_PREFIX}/reviews/{peer_app['application_id']}/decision",
            headers=ctx["reviewer"],
            json={"decision": "approved", "comment": "move to teacher"},
        )
    )

    export_task = assert_ok(
        client.post(
            f"{API_PREFIX}/archives/exports",
            headers={**ctx["teacher"], "Idempotency-Key": "permission-archive-001"},
            json={
                "scope": "applications",
                "format": "xlsx",
                "filters": {"class_id": 301, "term": "2025-2026-1"},
                "store_to_archive": True,
            },
        )
    )
    export_detail = assert_ok(
        client.get(
            f"{API_PREFIX}/teacher/exports/{export_task['task_id']}",
            headers=ctx["teacher"],
        )
    )
    archive_id = assert_ok(client.get(f"{API_PREFIX}/archives/exports", headers=ctx["teacher"]))[0]["archive_id"]

    visible_announcement = assert_ok(
        client.post(
            f"{API_PREFIX}/announcements",
            headers=ctx["teacher"],
            json={
                "title": "class-301-announcement",
                "archive_id": archive_id,
                "scope": {"grade": 2023, "class_ids": [301]},
                "start_at": (now - timedelta(hours=1)).isoformat(),
                "end_at": (now + timedelta(days=2)).isoformat(),
                "show_fields": ["student_name", "score"],
            },
        )
    )
    hidden_announcement = assert_ok(
        client.post(
            f"{API_PREFIX}/announcements",
            headers=ctx["teacher"],
            json={
                "title": "class-302-announcement",
                "archive_id": archive_id,
                "scope": {"grade": 2023, "class_ids": [302]},
                "start_at": (now - timedelta(hours=1)).isoformat(),
                "end_at": (now + timedelta(days=2)).isoformat(),
                "show_fields": ["student_name", "score"],
            },
        )
    )

    appeal = assert_ok(
        client.post(
            f"{API_PREFIX}/appeals",
            headers=ctx["owner"],
            json={
                "announcement_id": visible_announcement["announcement_id"],
                "content": "please review this result",
                "attachments": [],
            },
        )
    )

    email_log = assert_ok(
        client.post(
            f"{API_PREFIX}/notifications/reject-email",
            headers=ctx["teacher"],
            json={
                "application_id": owner_app["application_id"],
                "to": "owner301@example.com",
                "subject": "status notice",
                "body": "queued mail body",
            },
        )
    )

    ctx["active_token"] = active_token
    ctx["pending_token"] = pending_token
    ctx["owner_file"] = owner_file
    ctx["peer_file"] = peer_file
    ctx["other_file"] = other_file
    ctx["reviewer_file"] = reviewer_file
    ctx["owner_app"] = owner_app["application_id"]
    ctx["peer_app"] = peer_app["application_id"]
    ctx["other_app"] = other_app["application_id"]
    ctx["reviewer_self_app"] = reviewer_self_app["application_id"]
    ctx["export_task"] = export_task["task_id"]
    ctx["export_file_url"] = export_detail["file_url"]
    ctx["archive_id"] = archive_id
    ctx["visible_announcement"] = visible_announcement["announcement_id"]
    ctx["hidden_announcement"] = hidden_announcement["announcement_id"]
    ctx["appeal_id"] = appeal["id"]
    ctx["email_log_id"] = email_log["id"]
    return ctx


def test_protected_routes_require_auth(permission_context):
    client = permission_context["client"]
    now = datetime.now(timezone.utc)

    specs = [
        ("post", f"{API_PREFIX}/auth/change-password", {"json": {"old_password": "pass1234", "new_password": "newpass1234"}}),
        ("post", f"{API_PREFIX}/auth/logout", {"json": {"refresh_token": "dummy-refresh-token"}}),
        ("get", f"{API_PREFIX}/users/me", {}),
        ("put", f"{API_PREFIX}/users/me", {"json": {"email": "changed@example.com"}}),
        ("get", f"{API_PREFIX}/applications/categories", {}),
        (
            "post",
            f"{API_PREFIX}/applications",
            {
                "json": {
                    "award_uid": 1,
                    "title": "no-auth-create",
                    "description": "no-auth-create",
                    "occurred_at": date.today().isoformat(),
                    "attachments": [{"file_id": permission_context["owner_file"]}],
                    "category": "innovation",
                    "sub_type": "achievement",
                    "score": 4.0,
                }
            },
        ),
        ("get", f"{API_PREFIX}/applications/my", {}),
        ("get", f"{API_PREFIX}/applications/my/category-summary", {}),
        ("get", f"{API_PREFIX}/applications/my/by-category?category=innovation", {}),
        ("get", f"{API_PREFIX}/applications/{permission_context['owner_app']}", {}),
        (
            "put",
            f"{API_PREFIX}/applications/{permission_context['owner_app']}",
            {
                "json": {
                    "award_uid": 1,
                    "title": "no-auth-update",
                    "description": "no-auth-update",
                    "occurred_at": date.today().isoformat(),
                    "attachments": [{"file_id": permission_context["owner_file"]}],
                    "category": "innovation",
                    "sub_type": "achievement",
                    "score": 4.0,
                }
            },
        ),
        ("post", f"{API_PREFIX}/applications/{permission_context['owner_app']}/withdraw", {}),
        ("delete", f"{API_PREFIX}/applications/{permission_context['owner_app']}", {}),
        ("post", f"{API_PREFIX}/files/upload", {"files": {"file": ("proof.png", b"png", "image/png")}}),
        ("get", f"{API_PREFIX}/files/{permission_context['owner_file']}", {}),
        ("get", f"{API_PREFIX}/files/{permission_context['owner_file']}/url", {}),
        ("delete", f"{API_PREFIX}/files/{permission_context['owner_file']}", {}),
        ("get", f"{API_PREFIX}/reviews/pending", {}),
        ("get", f"{API_PREFIX}/reviews/pending-count", {}),
        ("get", f"{API_PREFIX}/reviews/pending/category-summary", {}),
        ("get", f"{API_PREFIX}/reviews/pending/by-category?category=innovation", {}),
        ("get", f"{API_PREFIX}/reviews/history", {}),
        ("get", f"{API_PREFIX}/reviews/{permission_context['owner_app']}", {}),
        (
            "post",
            f"{API_PREFIX}/reviews/{permission_context['owner_app']}/decision",
            {"json": {"decision": "approved", "comment": "no-auth"}},
        ),
        (
            "post",
            f"{API_PREFIX}/reviews/batch-decision",
            {"json": {"application_ids": [permission_context["owner_app"]], "decision": "approved", "comment": "no-auth"}},
        ),
        ("get", f"{API_PREFIX}/teacher/applications", {}),
        (
            "post",
            f"{API_PREFIX}/teacher/applications/{permission_context['peer_app']}/recheck",
            {"json": {"decision": "approved", "comment": "no-auth", "score": 4.0}},
        ),
        ("post", f"{API_PREFIX}/teacher/applications/archive", {"json": {"application_ids": [permission_context["peer_app"]]}}),
        ("get", f"{API_PREFIX}/teacher/statistics", {}),
        ("get", f"{API_PREFIX}/teacher/statistics/classes", {}),
        (
            "post",
            f"{API_PREFIX}/teacher/exports",
            {"json": {"scope": "applications", "format": "xlsx", "filters": {"class_id": 301}, "store_to_archive": False}},
        ),
        ("get", f"{API_PREFIX}/teacher/exports/{permission_context['export_task']}", {}),
        ("get", f"{API_PREFIX}/teacher/exports/{permission_context['export_task']}/download", {}),
        (
            "post",
            f"{API_PREFIX}/archives/exports",
            {"json": {"scope": "applications", "format": "xlsx", "filters": {"class_id": 301}, "store_to_archive": True}},
        ),
        ("get", f"{API_PREFIX}/archives/exports", {}),
        ("get", f"{API_PREFIX}/archives/exports/{permission_context['archive_id']}", {}),
        ("get", f"{API_PREFIX}/archives/exports/{permission_context['archive_id']}/download", {}),
        ("get", f"{API_PREFIX}/announcements", {}),
        (
            "post",
            f"{API_PREFIX}/announcements",
            {
                "json": {
                    "title": "no-auth-announcement",
                    "archive_id": permission_context["archive_id"],
                    "scope": {"grade": 2023, "class_ids": [301]},
                    "start_at": (now - timedelta(hours=1)).isoformat(),
                    "end_at": (now + timedelta(days=1)).isoformat(),
                    "show_fields": ["student_name"],
                }
            },
        ),
        (
            "put",
            f"{API_PREFIX}/announcements/{permission_context['visible_announcement']}",
            {
                "json": {
                    "title": "no-auth-update-announcement",
                    "archive_id": permission_context["archive_id"],
                    "scope": {"grade": 2023, "class_ids": [301]},
                    "start_at": (now - timedelta(hours=1)).isoformat(),
                    "end_at": (now + timedelta(days=1)).isoformat(),
                    "show_fields": ["student_name"],
                }
            },
        ),
        ("post", f"{API_PREFIX}/announcements/{permission_context['visible_announcement']}/close", {}),
        ("delete", f"{API_PREFIX}/announcements/{permission_context['visible_announcement']}", {}),
        (
            "post",
            f"{API_PREFIX}/appeals",
            {
                "json": {
                    "announcement_id": permission_context["visible_announcement"],
                    "content": "no-auth-appeal",
                    "attachments": [],
                }
            },
        ),
        ("get", f"{API_PREFIX}/appeals", {}),
        (
            "post",
            f"{API_PREFIX}/appeals/{permission_context['appeal_id']}/process",
            {"json": {"result": "approved", "result_comment": "no-auth"}},
        ),
        (
            "post",
            f"{API_PREFIX}/notifications/reject-email",
            {"json": {"application_id": permission_context["owner_app"], "to": "owner301@example.com", "subject": "s", "body": "b"}},
        ),
        ("get", f"{API_PREFIX}/notifications/email-logs", {}),
        ("get", f"{API_PREFIX}/ai-audits/{permission_context['owner_app']}/report", {}),
        ("get", f"{API_PREFIX}/ai-audits/logs", {}),
        ("get", f"{API_PREFIX}/system/configs", {}),
        (
            "put",
            f"{API_PREFIX}/system/configs",
            {"json": {"config_key": "announcement_rules", "config_value": {"appeal_days": 3}, "description": "no-auth"}},
        ),
        ("get", f"{API_PREFIX}/system/logs", {}),
        ("get", f"{API_PREFIX}/system/award-dicts", {}),
        (
            "post",
            f"{API_PREFIX}/system/award-dicts",
            {"json": {"award_uid": 990001, "category": "innovation", "sub_type": "achievement", "award_name": "x", "score": 1.0, "max_score": 1.0}},
        ),
        ("put", f"{API_PREFIX}/system/award-dicts/999999", {"json": {"score": 2.0, "max_score": 2.0, "is_active": True}}),
        ("delete", f"{API_PREFIX}/system/award-dicts/999999", {}),
        ("get", f"{API_PREFIX}/tokens", {}),
        ("post", f"{API_PREFIX}/tokens/reviewer", {"json": {"class_ids": [301]}}),
        ("post", f"{API_PREFIX}/tokens/reviewer/activate", {"json": {"token": permission_context['pending_token']['token']}}),
        ("post", f"{API_PREFIX}/tokens/{permission_context['pending_token']['token_id']}/revoke", {}),
    ]

    for method, url, kwargs in specs:
        response = getattr(client, method)(url, **kwargs)
        assert response.status_code == 401, (method, url, response.text)


def test_application_file_and_attachment_boundaries(permission_context):
    client = permission_context["client"]
    owner = permission_context["owner"]
    other = permission_context["other"]
    reviewer = permission_context["reviewer"]
    teacher = permission_context["teacher"]
    admin = permission_context["admin"]

    assert_ok(client.get(f"{API_PREFIX}/applications/categories", headers=owner))
    owner_detail = assert_ok(client.get(f"{API_PREFIX}/applications/{permission_context['owner_app']}", headers=owner))
    assert owner_detail["application_id"] == permission_context["owner_app"]

    assert_forbidden(client.get(f"{API_PREFIX}/applications/{permission_context['owner_app']}", headers=other))
    assert_ok(client.get(f"{API_PREFIX}/applications/{permission_context['owner_app']}", headers=reviewer))
    assert_forbidden(client.get(f"{API_PREFIX}/applications/{permission_context['other_app']}", headers=reviewer))

    assert_api_code(
        client.post(
            f"{API_PREFIX}/applications",
            headers=teacher,
            json={
                "award_uid": 1,
                "title": "teacher-create",
                "description": "teacher-create",
                "occurred_at": date.today().isoformat(),
                "attachments": [{"file_id": permission_context["owner_file"]}],
                "category": "innovation",
                "sub_type": "achievement",
                "score": 4.0,
            },
        ),
        1003,
    )

    assert_api_code(
        client.post(
            f"{API_PREFIX}/applications",
            headers=owner,
            json={
                "award_uid": 1,
                "title": "bad-attachment-create",
                "description": "bad-attachment-create",
                "occurred_at": date.today().isoformat(),
                "attachments": [{"file_id": permission_context["other_file"]}],
                "category": "innovation",
                "sub_type": "achievement",
                "score": 4.0,
            },
        ),
        1003,
    )

    assert_api_code(
        client.put(
            f"{API_PREFIX}/applications/{permission_context['owner_app']}",
            headers=owner,
            json={
                "award_uid": 1,
                "title": "bad-attachment-update",
                "description": "bad-attachment-update",
                "occurred_at": date.today().isoformat(),
                "attachments": [{"file_id": permission_context["other_file"]}],
                "category": "innovation",
                "sub_type": "achievement",
                "score": 4.0,
            },
        ),
        1003,
    )

    temp_file = upload_file(client, permission_context["tokens"]["owner"], "temp-delete.png")
    temp_app = create_application(client, permission_context["tokens"]["owner"], file_id=temp_file, title="owner-delete-app")
    updated = assert_ok(
        client.put(
            f"{API_PREFIX}/applications/{temp_app['application_id']}",
            headers=owner,
            json={
                "award_uid": 1,
                "title": "owner-update-ok",
                "description": "owner-update-ok",
                "occurred_at": date.today().isoformat(),
                "attachments": [{"file_id": temp_file}],
                "category": "innovation",
                "sub_type": "achievement",
                "score": 4.0,
            },
        )
    )
    assert updated["status"] in {"pending_ai", "pending_review", "ai_abnormal"}
    withdrawn = assert_ok(client.post(f"{API_PREFIX}/applications/{temp_app['application_id']}/withdraw", headers=owner))
    assert withdrawn["status"] == "withdrawn"

    temp_file2 = upload_file(client, permission_context["tokens"]["owner"], "temp-delete-2.png")
    temp_app2 = create_application(client, permission_context["tokens"]["owner"], file_id=temp_file2, title="owner-delete-app-2")
    delete_response = client.delete(f"{API_PREFIX}/applications/{temp_app2['application_id']}", headers=owner)
    assert_ok(delete_response)

    file_meta = assert_ok(client.get(f"{API_PREFIX}/files/{permission_context['owner_file']}", headers={**owner, "accept": "application/json"}))
    assert file_meta["file_id"] == permission_context["owner_file"]
    file_url = assert_ok(client.get(f"{API_PREFIX}/files/{permission_context['owner_file']}/url", headers=owner))
    assert file_url["url"].endswith(permission_context["owner_file"])
    file_content = client.get(file_url["url"], headers=owner)
    assert file_content.status_code == 200
    assert_ok(client.get(f"{API_PREFIX}/files/{permission_context['owner_file']}", headers={**teacher, "accept": "application/json"}))
    assert_ok(client.get(f"{API_PREFIX}/files/{permission_context['owner_file']}", headers={**admin, "accept": "application/json"}))
    assert_ok(client.get(f"{API_PREFIX}/files/{permission_context['owner_file']}", headers={**reviewer, "accept": "application/json"}))
    assert_forbidden(client.get(f"{API_PREFIX}/files/{permission_context['owner_file']}", headers={**other, "accept": "application/json"}))
    assert_forbidden(client.get(f"{API_PREFIX}/files/{permission_context['peer_file']}", headers={**reviewer, "accept": "application/json"}))

    temp_file3 = upload_file(client, permission_context["tokens"]["owner"], "temp-delete-file.png")
    delete_file_response = client.delete(f"{API_PREFIX}/files/{temp_file3}", headers=owner)
    assert_ok(delete_file_response)


def test_reviewer_teacher_admin_and_notification_boundaries(permission_context):
    client = permission_context["client"]
    owner = permission_context["owner"]
    reviewer = permission_context["reviewer"]
    teacher = permission_context["teacher"]
    admin = permission_context["admin"]

    assert_forbidden(client.get(f"{API_PREFIX}/reviews/pending", headers=owner))
    assert_forbidden(client.get(f"{API_PREFIX}/reviews/pending-count", headers=owner))
    assert_forbidden(client.get(f"{API_PREFIX}/reviews/pending/category-summary", headers=owner))
    assert_forbidden(client.get(f"{API_PREFIX}/reviews/pending/by-category?category=innovation", headers=owner))
    assert_forbidden(client.get(f"{API_PREFIX}/reviews/history", headers=owner))

    pending = assert_ok(client.get(f"{API_PREFIX}/reviews/pending", headers=reviewer))
    pending_ids = {item["application_id"] for item in pending["list"]}
    assert permission_context["owner_app"] in pending_ids
    assert permission_context["reviewer_self_app"] not in pending_ids
    assert_ok(client.get(f"{API_PREFIX}/reviews/pending-count", headers=reviewer))
    assert_ok(client.get(f"{API_PREFIX}/reviews/pending/category-summary", headers=reviewer))
    assert_ok(client.get(f"{API_PREFIX}/reviews/pending/by-category?category=innovation", headers=reviewer))
    history = assert_ok(client.get(f"{API_PREFIX}/reviews/history", headers=reviewer))
    assert history["total"] >= 1
    assert_ok(client.get(f"{API_PREFIX}/reviews/{permission_context['owner_app']}", headers=reviewer))
    assert_api_code(client.get(f"{API_PREFIX}/reviews/{permission_context['peer_app']}", headers=reviewer), 1000)
    assert_forbidden(
        client.post(
            f"{API_PREFIX}/reviews/{permission_context['reviewer_self_app']}/decision",
            headers=reviewer,
            json={"decision": "approved", "comment": "self review"},
        )
    )

    batch_file = upload_file(client, permission_context["tokens"]["peer"], "batch-app.png")
    batch_app = create_application(client, permission_context["tokens"]["peer"], file_id=batch_file, title="batch-target")
    batch_result = assert_ok(
        client.post(
            f"{API_PREFIX}/reviews/batch-decision",
            headers=reviewer,
            json={"application_ids": [batch_app["application_id"]], "decision": "approved", "comment": "batch-ok"},
        )
    )
    assert batch_result["success_count"] == 1

    assert_api_code(client.get(f"{API_PREFIX}/reviews/{permission_context['owner_app']}", headers=teacher), 1000)
    teacher_pending = assert_ok(client.get(f"{API_PREFIX}/reviews/pending", headers=teacher))
    assert any(item["application_id"] == permission_context["peer_app"] for item in teacher_pending["list"])
    assert_ok(client.get(f"{API_PREFIX}/reviews/{permission_context['peer_app']}", headers=teacher))
    rechecked = assert_ok(
        client.post(
            f"{API_PREFIX}/reviews/{permission_context['peer_app']}/decision",
            headers=teacher,
            json={"decision": "approved", "comment": "teacher-approved"},
        )
    )
    assert rechecked["status"] == "approved"

    admin_pending = assert_ok(client.get(f"{API_PREFIX}/reviews/pending", headers=admin))
    assert admin_pending["total"] >= 0
    admin_recheck = assert_ok(
        client.post(
            f"{API_PREFIX}/teacher/applications/{permission_context['peer_app']}/recheck",
            headers=admin,
            json={"decision": "rejected", "comment": "admin-recheck", "score": 3.0},
        )
    )
    assert admin_recheck["status"] == "rejected"

    assert_forbidden(client.get(f"{API_PREFIX}/teacher/applications", headers=reviewer))
    assert_ok(client.get(f"{API_PREFIX}/teacher/applications", headers=teacher))
    assert_ok(client.get(f"{API_PREFIX}/teacher/statistics", headers=teacher))
    assert_ok(client.get(f"{API_PREFIX}/teacher/statistics/classes", headers=teacher))
    assert_ok(client.get(f"{API_PREFIX}/teacher/exports/{permission_context['export_task']}", headers=teacher))
    teacher_download = client.get(f"{API_PREFIX}/teacher/exports/{permission_context['export_task']}/download", headers=teacher)
    assert teacher_download.status_code == 200
    admin_download = client.get(f"{API_PREFIX}/teacher/exports/{permission_context['export_task']}/download", headers=admin)
    assert admin_download.status_code == 200
    assert_forbidden(client.get(f"{API_PREFIX}/teacher/exports/{permission_context['export_task']}/download", headers=owner))

    assert_ok(
        client.post(
            f"{API_PREFIX}/teacher/applications/archive",
            headers=teacher,
            json={"application_ids": [permission_context["peer_app"]]},
        )
    )

    assert_forbidden(
        client.post(
            f"{API_PREFIX}/notifications/reject-email",
            headers=reviewer,
            json={"application_id": permission_context["owner_app"], "to": "owner301@example.com", "subject": "s", "body": "b"},
        )
    )
    assert_forbidden(client.get(f"{API_PREFIX}/notifications/email-logs", headers=reviewer))
    assert_ok(client.get(f"{API_PREFIX}/notifications/email-logs", headers=teacher))
    assert_ok(client.get(f"{API_PREFIX}/notifications/email-logs", headers=admin))

    assert_ok(client.get(f"{API_PREFIX}/ai-audits/{permission_context['owner_app']}/report", headers=owner))
    assert_forbidden(client.get(f"{API_PREFIX}/ai-audits/{permission_context['owner_app']}/report", headers=permission_context["other"]))
    assert_ok(client.get(f"{API_PREFIX}/ai-audits/{permission_context['owner_app']}/report", headers=teacher))
    assert_ok(client.get(f"{API_PREFIX}/ai-audits/{permission_context['owner_app']}/report", headers=admin))
    assert_forbidden(client.get(f"{API_PREFIX}/ai-audits/logs", headers=reviewer))
    assert_ok(client.get(f"{API_PREFIX}/ai-audits/logs", headers=teacher))
    assert_ok(client.get(f"{API_PREFIX}/ai-audits/logs", headers=admin))


def test_archive_announcement_appeal_and_token_boundaries(permission_context):
    client = permission_context["client"]
    owner = permission_context["owner"]
    other = permission_context["other"]
    reviewer = permission_context["reviewer"]
    teacher = permission_context["teacher"]
    admin = permission_context["admin"]

    teacher_archive_download = client.get(f"{API_PREFIX}/archives/exports/{permission_context['archive_id']}/download", headers=teacher)
    assert teacher_archive_download.status_code == 200
    admin_archive_download = client.get(f"{API_PREFIX}/archives/exports/{permission_context['archive_id']}/download", headers=admin)
    assert admin_archive_download.status_code == 200
    owner_archive_download = client.get(f"{API_PREFIX}/archives/exports/{permission_context['archive_id']}/download", headers=owner)
    assert owner_archive_download.status_code == 200
    reviewer_archive_download = client.get(f"{API_PREFIX}/archives/exports/{permission_context['archive_id']}/download", headers=reviewer)
    assert reviewer_archive_download.status_code == 200
    assert_forbidden(client.get(f"{API_PREFIX}/archives/exports/{permission_context['archive_id']}/download", headers=permission_context["activator"]))
    assert_forbidden(client.get(f"{API_PREFIX}/archives/exports", headers=owner))
    assert_ok(client.get(f"{API_PREFIX}/archives/exports", headers=teacher))
    assert_ok(client.get(f"{API_PREFIX}/archives/exports/{permission_context['archive_id']}", headers=teacher))

    owner_announcements = assert_ok(client.get(f"{API_PREFIX}/announcements", headers=owner))
    owner_titles = {item["title"] for item in owner_announcements}
    assert "class-301-announcement" in owner_titles
    assert "class-302-announcement" not in owner_titles
    other_announcements = assert_ok(client.get(f"{API_PREFIX}/announcements", headers=other))
    other_titles = {item["title"] for item in other_announcements}
    assert "class-302-announcement" in other_titles
    assert "class-301-announcement" not in other_titles
    assert_ok(client.get(f"{API_PREFIX}/announcements", headers=teacher))
    assert_forbidden(
        client.post(
            f"{API_PREFIX}/announcements",
            headers=owner,
            json={
                "title": "student-announcement",
                "archive_id": permission_context["archive_id"],
                "scope": {"grade": 2023, "class_ids": [301]},
                "start_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                "end_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "show_fields": ["student_name"],
            },
        )
    )
    updated = assert_ok(
        client.put(
            f"{API_PREFIX}/announcements/{permission_context['visible_announcement']}",
            headers=teacher,
            json={
                "title": "class-301-announcement-updated",
                "archive_id": permission_context["archive_id"],
                "scope": {"grade": 2023, "class_ids": [301]},
                "start_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                "end_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "show_fields": ["student_name", "score"],
            },
        )
    )
    assert updated["title"] == "class-301-announcement-updated"

    assert_api_code(
        client.post(
            f"{API_PREFIX}/appeals",
            headers=owner,
            json={
                "announcement_id": permission_context["hidden_announcement"],
                "content": "wrong scope appeal",
                "attachments": [],
            },
        ),
        1003,
    )
    assert_api_code(
        client.post(
            f"{API_PREFIX}/appeals",
            headers=owner,
            json={
                "announcement_id": permission_context["visible_announcement"],
                "content": "wrong attachment appeal",
                "attachments": [{"file_id": permission_context["other_file"]}],
            },
        ),
        1003,
    )

    closed = assert_ok(client.post(f"{API_PREFIX}/announcements/{permission_context['hidden_announcement']}/close", headers=admin))
    assert closed["status"] == "closed"
    delete_response = client.delete(f"{API_PREFIX}/announcements/{permission_context['hidden_announcement']}", headers=admin)
    assert_ok(delete_response)

    owner_appeals = assert_ok(client.get(f"{API_PREFIX}/appeals", headers=owner))
    assert owner_appeals["total"] == 1
    teacher_appeals = assert_ok(client.get(f"{API_PREFIX}/appeals", headers=teacher))
    assert teacher_appeals["total"] >= 1
    assert_forbidden(client.post(f"{API_PREFIX}/appeals/{permission_context['appeal_id']}/process", headers=owner, json={"result": "approved"}))
    processed = assert_ok(
        client.post(
            f"{API_PREFIX}/appeals/{permission_context['appeal_id']}/process",
            headers=teacher,
            json={"result": "approved", "result_comment": "processed"},
        )
    )
    assert processed["status"] == "processed"

    assert_forbidden(client.get(f"{API_PREFIX}/tokens", headers=owner))
    assert_ok(client.get(f"{API_PREFIX}/tokens", headers=teacher))
    assert_ok(client.get(f"{API_PREFIX}/tokens", headers=admin))
    assert_forbidden(client.post(f"{API_PREFIX}/tokens/reviewer", headers=owner, json={"class_ids": [301]}))
    assert_forbidden(
        client.post(
            f"{API_PREFIX}/tokens/reviewer/activate",
            headers=teacher,
            json={"token": permission_context["pending_token"]["token"]},
        )
    )
    activated = assert_ok(
        client.post(
            f"{API_PREFIX}/tokens/reviewer/activate",
            headers=permission_context["activator"],
            json={"token": permission_context["pending_token"]["token"]},
        )
    )
    assert activated["is_reviewer"] is True
    revoke_response = client.post(
        f"{API_PREFIX}/tokens/{permission_context['pending_token']['token_id']}/revoke",
        headers=admin,
    )
    assert_ok(revoke_response)


def test_admin_only_system_boundaries(permission_context):
    client = permission_context["client"]
    admin = permission_context["admin"]
    teacher = permission_context["teacher"]
    owner = permission_context["owner"]

    assert_forbidden(client.get(f"{API_PREFIX}/system/configs", headers=teacher))
    assert_forbidden(client.get(f"{API_PREFIX}/system/configs", headers=owner))
    configs = assert_ok(client.get(f"{API_PREFIX}/system/configs", headers=admin))
    assert "categories" in configs

    updated = assert_ok(
        client.put(
            f"{API_PREFIX}/system/configs",
            headers=admin,
            json={
                "config_key": "announcement_rules",
                "config_value": {"appeal_deadline_days": 5},
                "description": "updated by admin",
            },
        )
    )
    assert updated["config_key"] == "announcement_rules"

    assert_forbidden(client.get(f"{API_PREFIX}/system/logs", headers=teacher))
    assert_ok(client.get(f"{API_PREFIX}/system/logs", headers=admin))

    assert_forbidden(client.get(f"{API_PREFIX}/system/award-dicts", headers=teacher))
    award_list = assert_ok(client.get(f"{API_PREFIX}/system/award-dicts", headers=admin))
    assert len(award_list) >= 1
    created_award = assert_ok(
        client.post(
            f"{API_PREFIX}/system/award-dicts",
            headers=admin,
            json={
                "award_uid": 990099,
                "category": "innovation",
                "sub_type": "achievement",
                "award_name": "permission-award",
                "score": 2.0,
                "max_score": 2.0,
            },
        )
    )
    updated_award = assert_ok(
        client.put(
            f"{API_PREFIX}/system/award-dicts/{created_award['id']}",
            headers=admin,
            json={"score": 2.5, "max_score": 2.5, "is_active": True},
        )
    )
    assert updated_award["score"] == 2.5
    deleted = client.delete(f"{API_PREFIX}/system/award-dicts/{created_award['id']}", headers=admin)
    assert_ok(deleted)
