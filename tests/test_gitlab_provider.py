"""Tests for GitLabApi pipeline/job -> CICheck conversion.

GitLab's merge-requests *list* endpoint never includes pipeline info (only
the single-MR GET endpoint does), so `_get_checks` fetches pipelines via the
dedicated MR-pipelines endpoint. A pipeline for a fork-sourced MR runs in the
fork's own project, not the MR's target project, so job fetching must use
the pipeline's own `project_id`. Externally-reported pipelines (status
posted by a third-party CI system) have no jobs at all; those fall back to
a single check reflecting the pipeline's own overall status.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from pyworkon.daemon.models import CICheck, PRStatus
from pyworkon.daemon.providers.gitlab.gitlab import GitLabApi

if TYPE_CHECKING:
    from pytest_httpx2 import HTTPXMock


@pytest.fixture
def gitlab_api() -> GitLabApi:
    return GitLabApi(
        name="gitlab",
        api_url="https://gitlab.example.com",
        username="test",
        password="test-token",
    )


async def test_get_checks_maps_jobs_to_ci_checks(
    gitlab_api: GitLabApi, httpx2_mock: HTTPXMock
) -> None:
    # The pipeline's project_id (99) differs from the MR's own project
    # ("group/project") to exercise fetching jobs from the fork's project.
    httpx2_mock.add_response(
        url=re.compile(r".*/merge_requests/5/pipelines$"),
        json=[
            {
                "id": 7,
                "project_id": 99,
                "status": "running",
                "web_url": "https://gitlab.example.com/fork/project/-/pipelines/7",
            }
        ],
    )
    httpx2_mock.add_response(
        url=re.compile(r".*/projects/99/pipelines/7/jobs"),
        json=[
            {
                "name": "test",
                "status": "success",
                "web_url": "https://gitlab.example.com/fork/project/-/jobs/1",
            },
            {
                "name": "build",
                "status": "failed",
                "web_url": "https://gitlab.example.com/fork/project/-/jobs/2",
            },
        ],
    )

    status, checks = await gitlab_api._get_checks("group/project", 5)

    # Overall status comes from the pipeline itself, not the jobs.
    assert status == PRStatus.PENDING
    assert [c.name for c in checks] == ["build", "test"]
    assert checks[0].status == PRStatus.FAILURE
    assert checks[0].url == "https://gitlab.example.com/fork/project/-/jobs/2"
    assert checks[1].status == PRStatus.SUCCESS


async def test_get_checks_filters_out_manual_jobs(
    gitlab_api: GitLabApi, httpx2_mock: HTTPXMock
) -> None:
    # Manual jobs require a human to trigger them (e.g. optional
    # deploy/diff jobs) and never ran; they shouldn't show as "pending".
    httpx2_mock.add_response(
        url=re.compile(r".*/merge_requests/5/pipelines$"),
        json=[
            {
                "id": 7,
                "project_id": 99,
                "status": "failed",
                "web_url": "https://gitlab.example.com/fork/project/-/pipelines/7",
            }
        ],
    )
    httpx2_mock.add_response(
        url=re.compile(r".*/projects/99/pipelines/7/jobs"),
        json=[
            {
                "name": "manage-mr",
                "status": "failed",
                "web_url": "https://gitlab.example.com/fork/project/-/jobs/1",
            },
            {
                "name": "diff: [env-a]",
                "status": "manual",
                "web_url": "https://gitlab.example.com/fork/project/-/jobs/2",
            },
            {
                "name": "diff: [env-b]",
                "status": "manual",
                "web_url": "https://gitlab.example.com/fork/project/-/jobs/3",
            },
        ],
    )

    status, checks = await gitlab_api._get_checks("group/project", 5)

    assert status == PRStatus.FAILURE
    assert [c.name for c in checks] == ["manage-mr"]


async def test_get_checks_falls_back_to_single_check_when_all_jobs_are_manual(
    gitlab_api: GitLabApi, httpx2_mock: HTTPXMock
) -> None:
    httpx2_mock.add_response(
        url=re.compile(r".*/merge_requests/5/pipelines$"),
        json=[
            {
                "id": 7,
                "project_id": 99,
                "status": "success",
                "web_url": "https://gitlab.example.com/fork/project/-/pipelines/7",
            }
        ],
    )
    httpx2_mock.add_response(
        url=re.compile(r".*/projects/99/pipelines/7/jobs"),
        json=[
            {
                "name": "diff: [env-a]",
                "status": "manual",
                "web_url": "https://gitlab.example.com/fork/project/-/jobs/2",
            },
        ],
    )

    status, checks = await gitlab_api._get_checks("group/project", 5)

    assert status == PRStatus.SUCCESS
    assert checks == [
        CICheck(
            name="Pipeline",
            status=PRStatus.SUCCESS,
            url="https://gitlab.example.com/fork/project/-/pipelines/7",
        )
    ]


async def test_get_checks_returns_none_status_when_no_pipelines(
    gitlab_api: GitLabApi, httpx2_mock: HTTPXMock
) -> None:
    httpx2_mock.add_response(json=[])

    status, checks = await gitlab_api._get_checks("group/project", 5)

    assert status == PRStatus.NONE
    assert checks == []


async def test_get_checks_falls_back_to_single_check_when_pipeline_has_no_jobs(
    gitlab_api: GitLabApi, httpx2_mock: HTTPXMock
) -> None:
    # Externally-reported pipeline status (e.g. posted by a third-party CI
    # system) has no job breakdown at all.
    httpx2_mock.add_response(
        url=re.compile(r".*/merge_requests/5/pipelines$"),
        json=[
            {
                "id": 7,
                "project_id": 99,
                "status": "success",
                "web_url": "https://gitlab.example.com/fork/project/-/pipelines/7",
            }
        ],
    )
    httpx2_mock.add_response(
        url=re.compile(r".*/pipelines/7/jobs"),
        json=[],
    )

    status, checks = await gitlab_api._get_checks("group/project", 5)

    assert status == PRStatus.SUCCESS
    assert checks == [
        CICheck(
            name="Pipeline",
            status=PRStatus.SUCCESS,
            url="https://gitlab.example.com/fork/project/-/pipelines/7",
        )
    ]


async def test_get_pr_info_includes_job_level_checks(
    gitlab_api: GitLabApi, httpx2_mock: HTTPXMock
) -> None:
    httpx2_mock.add_response(
        url=re.compile(r".*/merge_requests\?.*"),
        json=[
            {
                "iid": 5,
                "title": "Add feature",
                "source_branch": "feature",
                "state": "opened",
            }
        ],
    )
    httpx2_mock.add_response(
        url=re.compile(r".*/merge_requests/5/pipelines$"),
        json=[
            {
                "id": 7,
                "project_id": 99,
                "status": "running",
                "web_url": "https://gitlab.example.com/fork/project/-/pipelines/7",
            }
        ],
    )
    httpx2_mock.add_response(
        url=re.compile(r".*/projects/99/pipelines/7/jobs"),
        json=[
            {
                "name": "lint",
                "status": "success",
                "web_url": "https://gitlab.example.com/fork/project/-/jobs/1",
            },
            {
                "name": "test",
                "status": "running",
                "web_url": "https://gitlab.example.com/fork/project/-/jobs/2",
            },
        ],
    )
    httpx2_mock.add_response(
        url=re.compile(r".*/approval_state$"),
        json={"rules": []},
    )

    pr_info = await gitlab_api.get_pr_info("group/project", "feature")

    assert pr_info is not None
    assert pr_info.status == PRStatus.PENDING
    assert [c.name for c in pr_info.ci_checks] == ["lint", "test"]
