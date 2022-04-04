from .app_mode.shell import PyWorkonShell

# from .tui import PyWorkonTui


def run():
    # PyWorkonTui.run(title="PyWorkon", log="textual.log")
    PyWorkonShell.run()


if __name__ == "__main__":
    run()
