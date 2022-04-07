from nubia.internal.commands.help import HelpCommand


def run_interactive(self, _0, args, _2):
    if args:
        args = args.split()
        try:
            cmd_instance = self.registry.find_command(args[0])
            if not cmd_instance:
                raise UnknownCommand("Command `{}` is " "unknown".format(args[0]))
            else:
                help_msg = cmd_instance.get_help(args[0].lower(), *args)
            print(help_msg)
        except CommandError as e:
            cprint(str(e), "red")
            return 1
    else:
        built_ins = PrettyTable(["Command", "Description"])
        built_ins.align = "l"
        t = PrettyTable(["Command", "Description"])
        t.align = "l"

        commands = {cmd_name: cmd for cmd in self.registry.get_all_commands() for cmd_name in cmd.get_command_names()}

        for cmd_name in sorted(commands):
            cmd = commands[cmd_name]
            table = built_ins if cmd.built_in else t
            cmd_help = cmd.get_help(cmd_name)
            table.add_row([colored(cmd_name, "magenta"), cmd_help])

        print(t)

        cprint("Built-in Commands", "yellow")
        print(built_ins)
        return 0


# HelpCommand.run_interactive = run_interactive
