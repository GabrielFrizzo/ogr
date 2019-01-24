import datetime
import logging

from ogr.services.abstract import (
    GitService,
    GitProject,
    PullRequest,
    PRComment,
    GitUser,
)
from ogr.services.our_pagure import OurPagure
from ogr.utils import PRStatus

logger = logging.getLogger(__name__)


class PagureService(GitService):
    def __init__(
            self, token=None, instance_url="https://src.fedoraproject.org", **kwargs
    ):
        super().__init__()
        self.instance_url = instance_url
        self._token = token
        self.pagure_kwargs = kwargs

        self.pagure = OurPagure(pagure_token=token, instance_url=instance_url, **kwargs)

    def get_project(self, **kwargs):
        project_kwargs = self.pagure_kwargs.copy()
        project_kwargs.update(kwargs)
        return PagureProject(
            instance_url=self.instance_url,
            token=self._token,
            service=self,
            **project_kwargs,
        )

    @property
    def user(self):
        return PagureUser(service=self)

    def change_token(self, new_token: str):
        """
        Change an API token.

        Only for this instance and newly created Projects via get_project.
        """
        self._token = new_token
        self.pagure.change_token(new_token)


class PagureProject(GitProject):
    def __init__(
            self,
            repo=None,
            namespace=None,
            username=None,
            instance_url=None,
            token=None,
            is_fork=False,
            service=None,
            **kwargs,
    ):
        if is_fork and username:
            complete_namespace = f"fork/{username}/{namespace}"
        else:
            complete_namespace = namespace

        super().__init__(repo=repo, namespace=complete_namespace, service=service)

        self.instance_url = instance_url
        self._token = token

        self.pagure_kwargs = kwargs
        if username:
            self.pagure_kwargs["username"] = username

        self.pagure = OurPagure(
            pagure_token=token,
            pagure_repository=f"{namespace}/{self.repo}",
            namespace=namespace,
            fork_username=username if is_fork else None,
            instance_url=instance_url,
            **kwargs,
        )

    def __str__(self):
        return f"namespace={self.namespace} repo={self.repo}"

    def __repr__(self):
        return f"PagureProject(namespace={self.namespace}, repo={self.repo})"

    def get_branches(self):
        return self.pagure.get_branches()

    def get_description(self):
        return self.pagure.get_project_description()

    def get_pr_list(self, status=PRStatus.open):
        status = status.name.lower().capitalize()
        raw_prs = self.pagure.list_requests(status=status)
        prs = [self._pr_from_pagure_dict(pr_dict) for pr_dict in raw_prs]
        return prs

    def get_pr_info(self, pr_id):
        pr_dict = self.pagure.request_info(request_id=pr_id)
        result = self._pr_from_pagure_dict(pr_dict)
        return result

    def _get_all_pr_comments(self, pr_id):
        raw_comments = self.pagure.request_info(request_id=pr_id)["comments"]

        parsed_comments = [
            self._prcomment_from_pagure_dict(comment_dict)
            for comment_dict in raw_comments
        ]
        return parsed_comments

    def pr_comment(self, pr_id, body, commit=None, filename=None, row=None):
        return self.pagure.comment_request(
            request_id=pr_id, body=body, commit=commit, filename=filename, row=row
        )

    def pr_close(self, pr_id):
        return self.pagure.close_request(request_id=pr_id)

    def pr_merge(self, pr_id):
        return self.pagure.merge_request(request_id=pr_id)

    def pr_create(self, title, body, target_branch, source_branch):
        return self.pagure.create_request(
            title=title,
            body=body,
            target_branch=target_branch,
            source_branch=source_branch,
        )

    def fork_create(self):
        return self.pagure.create_fork()

    def get_fork(self):
        """
        PagureRepo instance of the fork of this repo.
        """
        kwargs = self.pagure_kwargs.copy()
        kwargs.update(
            repo=self.repo,
            namespace=self.namespace,
            instance_url=self.instance_url,
            token=self._token,
            is_fork=True,
        )
        if "username" not in kwargs:
            kwargs["username"] = self.service.user.get_username()

        fork_project = PagureProject(**kwargs)
        try:
            if fork_project.exists() and fork_project.pagure.get_parent():
                return fork_project
        except:
            return None
        return None

    def exists(self):
        return self.pagure.project_exists()

    def is_forked(self):
        pass

    @property
    def is_fork(self):
        return "fork" in self.namespace

    def get_git_urls(self):
        return self.pagure.get_git_urls()

    def get_commit_flags(self, commit):
        return self.pagure.get_commit_flags(commit=commit)

    def _pr_from_pagure_dict(self, pr_dict):
        return PullRequest(
            title=pr_dict["title"],
            id=pr_dict["id"],
            status=PRStatus[pr_dict["status"].lower()],
            url="/".join(
                [
                    self.instance_url,
                    pr_dict["project"]["url_path"],
                    "pull-request",
                    str(pr_dict["id"]),
                ]
            ),
            description=pr_dict["initial_comment"],
            author=pr_dict["user"]["name"],
            source_branch=pr_dict["branch_from"],
            target_branch=pr_dict["branch"],
            created=datetime.datetime.fromtimestamp(int(pr_dict["date_created"])),
        )

    @staticmethod
    def _prcomment_from_pagure_dict(comment_dict):
        return PRComment(
            comment=comment_dict["comment"],
            author=comment_dict["user"]["name"],
            created=datetime.datetime.fromtimestamp(int(comment_dict["date_created"])),
            edited=datetime.datetime.fromtimestamp(int(comment_dict["edited_on"]))
            if comment_dict["edited_on"]
            else None,
        )

    def change_token(self, new_token: str):
        """
        Change an API token.

        Only for this instance.
        """
        self._token = new_token
        self.pagure.change_token(new_token)


class PagureUser(GitUser):
    def get_username(self):
        return self.service.pagure.whoami()

    def __init__(self, service):
        super().__init__(service=service)
