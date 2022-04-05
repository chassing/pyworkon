import databases
import orm

from .config import config

database = databases.Database(f"sqlite:///{str(config.db)}")
models = orm.ModelRegistry(database=database)


class Project(orm.Model):
    tablename = "project"
    registry = models
    fields = {
        "id": orm.Integer(primary_key=True),
        "project_id": orm.String(max_length=100),
        "repository_url": orm.String(max_length=255),
    }


class Db:
    async def __aenter__(self):
        await models.create_all()
        return self

    async def __aexit__(self, *args, **kwargs):
        ...

    async def projects(self) -> list[Project]:
        """Get all projects."""
        return await Project.objects.all()

    async def project(self, project_id) -> Project:
        """Get a project by id."""
        return await Project.objects.get(project_id=project_id)

    async def project_update_or_create(self, project_id, repository_url) -> Project:
        """Insert/Update a project."""
        return await Project.objects.update_or_create(
            project_id=project_id, defaults={"repository_url": repository_url}
        )
