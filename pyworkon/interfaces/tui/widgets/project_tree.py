# from rich.panel import Panel
from pathlib import Path
from typing import TypeVar

from rich.console import RenderableType
from rich.text import Text
from rich.tree import Tree
from textual import events
from textual.reactive import Reactive
from textual.widgets import (
    NodeID,
    TreeClick,
    TreeControl,
    TreeNode,
)

from ...project import Project

NodeDataType = TypeVar("NodeDataType")


class TreeEntry:
    def __init__(self, id, icon, project=None) -> None:
        self.id = id
        self.icon = icon
        self.project = project

    @property
    def label(self):
        return Path(self.id).name

    @property
    def parent(self):
        p = str(Path(self.id).parent)
        return None if p == "." else p


class ProjectTree(TreeControl[TreeEntry]):
    def __init__(self, projects: list[Project]) -> None:
        label = "."
        super().__init__(label, data=None)
        self._tree = Tree(label, hide_root=True)
        self.root: TreeNode[NodeDataType] = TreeNode(None, self.id, self, self._tree, label, TreeEntry(".", icon=""))
        self._tree.label = self.root
        self.nodes[NodeID(self.id)] = self.root

        self.projects = projects
        self.root.tree.guide_style = "black"

    has_focus: Reactive[bool] = Reactive(False)

    def on_focus(self) -> None:
        self.has_focus = True

    def on_blur(self) -> None:
        self.has_focus = False

    async def watch_hover_node(self, hover_node: NodeID) -> None:
        for node in self.nodes.values():
            node.tree.guide_style = "bold not dim red" if node.id == hover_node else "black"
        self.refresh(layout=True)

    async def on_mount(self, event: events.Mount) -> None:
        await self.load_projects()

    async def load_projects(self):
        nodes: dict[str, NodeID] = {}

        async def _add_project(node: TreeNode[TreeEntry], tree_entry: TreeEntry):
            if tree_entry.parent:
                if not (parent_id := nodes.get(tree_entry.parent)):
                    # create parent
                    await _add_project(node, TreeEntry(tree_entry.parent, icon="📂"))
                    node = self.nodes[self.id]
                else:
                    node = self.nodes[parent_id]

            await node.add(tree_entry.label, tree_entry)
            node.loaded = True
            await node.expand()
            nodes[tree_entry.id] = self.id

        for project in self.projects:
            await _add_project(self.root, TreeEntry(id=project.id, icon="📄", project=project))

        self.refresh(layout=True)

    def render_node(self, node: TreeNode[TreeEntry]) -> RenderableType:
        meta = {
            "@click": f"click_label({node.id})",
            "tree_node": node.id,
            "cursor": node.is_cursor,
        }
        label = Text(node.data.label) if isinstance(node.data.label, str) else node.data.label
        if node.id == self.hover_node:
            label.stylize("underline")
        if not node.data.project:
            label.stylize("bold magenta")
        else:
            label.stylize("bright_green")
            label.highlight_regex(r"\..*$", "green")

        if label.plain.startswith("."):
            label.stylize("dim")

        if node.is_cursor and self.has_focus:
            label.stylize("reverse")

        icon_label = Text(f"{node.data.icon} ", no_wrap=True, overflow="ellipsis") + label
        icon_label.apply_meta(meta)
        return icon_label

    async def handle_tree_click(self, message: TreeClick[Project]) -> None:
        entry = message.node.data
        if entry.project:
            # await self.emit(FileClick(self, entry.path))
            ...
        else:
            if not message.node.loaded:
                await self.load_directory(message.node)
                await message.node.expand()
            else:
                await message.node.toggle()
