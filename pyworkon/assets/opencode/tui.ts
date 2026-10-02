import { execFile, spawnSync } from "node:child_process"
import { promisify } from "node:util"
import { Plugin } from "@opencode/plugin/tui"
import { createEffect, createRoot } from "solid-js"
import { AgentReporter, agentArguments, watchAgent } from "./status"

const run = promisify(execFile)

export default Plugin.define({
  id: "pyworkon.agent-status",
  setup(context) {
    // The shared server has no reliable terminal/pane identity. Run only in the CLI.
    if (!process.env.TMUX || !process.env.TMUX_PANE) return
    const pid = process.pid
    const reportError = (error: unknown) => {
      context.ui.toast.show({
        title: "pyworkon",
        message: `Agent status unavailable: ${error instanceof Error ? error.message : String(error)}`,
        variant: "warning",
      })
    }
    const reporter = new AgentReporter(async (state) => {
      await run("pyworkon", agentArguments(pid, state), { timeout: 3000 })
    }, reportError)

    const dispose = watchAgent(context.data.session, () => {
      const route = context.ui.router.current()
      return route.type === "session" ? route.sessionID : null
    }, pid, reporter, reportError, { createEffect, createRoot })

    // Node's exit event cannot await plugin cleanup or asynchronous subprocesses.
    const onExit = () => {
      spawnSync("pyworkon", agentArguments(pid, null), { timeout: 1000, stdio: "ignore" })
    }
    process.once("exit", onExit)
    return async () => {
      dispose()
      await reporter.close()
      process.off("exit", onExit)
    }
  },
})
