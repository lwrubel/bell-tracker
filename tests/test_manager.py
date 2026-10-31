import pytest
from conftest import ADMIN_PASSWORD, RINGER_PASSWORD, login

REPORTS = [
    "equipment-table",
    "equipment-pull-list",
    "bass-bells",
    "cases-list",
    "cover-sheets",
]


@pytest.mark.parametrize("report", REPORTS)
def test_manager_can_open_every_report(client, manager, program, piece, report):
    login(client, manager, RINGER_PASSWORD)
    response = client.get(f"/programs/{program.id}/reports/{report}")
    assert response.status_code == 200


@pytest.mark.parametrize("report", REPORTS)
def test_ringer_cannot_open_reports(client, ringer, program, report):
    login(client, ringer, RINGER_PASSWORD)
    response = client.get(f"/programs/{program.id}/reports/{report}")
    assert response.status_code == 403


def test_manager_sees_report_buttons_but_no_admin_link(client, manager, program):
    login(client, manager, RINGER_PASSWORD)
    body = client.get("/").get_data(as_text=True)

    for report in REPORTS:
        assert f"/programs/{program.id}/reports/{report}" in body
    assert 'href="/admin/"' not in body


@pytest.mark.parametrize("url", ["/admin/", "/admin/user/", "/admin/program/"])
def test_manager_is_kept_out_of_the_admin_panel(client, manager, url):
    login(client, manager, RINGER_PASSWORD)
    response = client.get(url, follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_admin_can_make_a_user_a_manager(client, db, admin_user, ringer):
    login(client, admin_user, ADMIN_PASSWORD)
    form = client.get(f"/admin/user/edit/?id={ringer.id}").get_data(as_text=True)
    assert "Is Manager" in form

    client.post(
        f"/admin/user/edit/?id={ringer.id}",
        data={
            "email": ringer.email,
            "name": ringer.name,
            "is_manager": "y",
            "password": "",
        },
    )

    db.session.refresh(ringer)
    assert ringer.is_manager is True
    assert ringer.is_admin is False
