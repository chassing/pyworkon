from pyworkon.interfaces.shell import cli
lazy from pyworkon.interfaces.tui.dashboard import DashboardApp


@cli.command()
def dashboard() -> None:
    """Full-detail monitoring dashboard for all open sessions."""
    DashboardApp().run()
