from pyworkon.interfaces.shell import cli
lazy from pyworkon.interfaces.tui.popup import PopupApp


@cli.command()
def popup() -> None:
    """Project switcher popup (exits after selection)."""
    PopupApp().run()
