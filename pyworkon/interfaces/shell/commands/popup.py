from pyworkon.interfaces.shell import cli


@cli.command()
def popup() -> None:
    """Project switcher popup (exits after selection)."""
    from pyworkon.interfaces.tui.popup import PopupApp

    PopupApp().run()
