from textual.app import App
from textual.widgets import (
    Footer,
    Header,
    Placeholder,
    ScrollView,
)

from ..project import Project
from .widgets.project_tree import ProjectTree


class PyWorkonTui(App):
    """An example of a very simple Textual App"""

    async def on_load(self) -> None:
        """Sent before going in to application mode."""

        # Bind our basic keys
        await self.bind("b", "view.toggle('sidebar')", "Toggle sidebar")
        await self.bind("q", "quit", "Quit")

    async def on_mount(self) -> None:
        """Call after terminal goes in to application mode"""

        # Create our widgets
        # In this a scroll view for the code and a directory tree
        self.body = ScrollView()
        self.project_tree = ProjectTree(
            [Project("github/chassing/pyworkon"), Project("github/org/foobar"), Project("gitlab/chassing/juppi")]
        )

        # Dock our widgets
        await self.view.dock(Header(), edge="top")
        await self.view.dock(Footer(), edge="bottom")

        # Note the directory is also in a scroll view
        await self.view.dock(ScrollView(self.project_tree), edge="left", size=48, name="sidebar")
        # await self.view.dock(self.body, edge="top")
        await self.view.dock(Placeholder(), edge="top")
        await self.set_focus(self.project_tree)
