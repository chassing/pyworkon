from pyworkon.interfaces.shell import cli


@cli.command()
def dashboard() -> None:
    """Full-detail monitoring dashboard for all open sessions."""
    from pyworkon.interfaces.tui.dashboard import DashboardApp

    DashboardApp().run()
