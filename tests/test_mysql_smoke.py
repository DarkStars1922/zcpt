API_PREFIX = "/api/v1"


def assert_ok(response):
    payload = response.json()
    assert response.status_code == 200, payload
    assert payload["code"] == 0, payload
    return payload["data"]


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def test_mysql_auth_smoke(client_with_mysql):
    client = client_with_mysql

    register_resp = client.post(
        f"{API_PREFIX}/auth/register",
        json={
            "account": "mysql1001",
            "password": "pass1234",
            "name": "MySQL Smoke",
            "role": "student",
            "class_id": 301,
            "email": "mysql1001@example.com",
            "is_reviewer": False,
        },
    )
    user = assert_ok(register_resp)["user"]
    assert user["account"] == "mysql1001"

    login_resp = client.post(
        f"{API_PREFIX}/auth/login",
        json={"account": "mysql1001", "password": "pass1234"},
    )
    login_data = assert_ok(login_resp)

    me = assert_ok(client.get(f"{API_PREFIX}/users/me", headers=auth_headers(login_data["access_token"])))
    assert me["email"] == "mysql1001@example.com"

    categories = assert_ok(
        client.get(f"{API_PREFIX}/applications/categories", headers=auth_headers(login_data["access_token"]))
    )
    assert len(categories) >= 1
