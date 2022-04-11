class GitLabApi:
    """GitLab REST interface."""

    API_URL = "https://gitlab.com"

    def __init__(self, api_url, username, password):
        """Init."""
        # self._api = GitLabConsumer(base_url=api_url, client=HttpxClient(), auth=(username, password))
        self._username = username

    async def __aenter__(self):
        await self._api.__aenter__()
        return self

    async def __aexit__(self, *args, **kwargs):
        await self._api.__aexit__()

    # async def projects(self) -> list[Repository]:
    #     repos = []
    #     per_page = 100
    #     for page in range(1, 1000):
    #         repos += await self._api.user_repos(page=page, per_page=per_page)
    #         if len(repos) < page * per_page:
    #             break
    #     return repos
