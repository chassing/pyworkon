import { expect, test } from "bun:test"
import { chmod, copyFile, mkdtemp, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"

test("installed runtime loads and observes the compiled host's Solid signals without node_modules", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "pyworkon-plugin-"))
  try {
    await Promise.all(["tui.ts", "status.ts"].map((filename) =>
      copyFile(path.join(import.meta.dir, filename), path.join(directory, filename)),
    ))
    const command = path.join(directory, "pyworkon")
    await Bun.write(command, '#!/usr/bin/env bash\nset -euo pipefail\nprintf \'%s\\n\' "$@" >> "$PYWORKON_TEST_REPORT"\n')
    await chmod(command, 0o755)
    const harness = path.join(directory, "host.ts")
    await Bun.write(harness, `
      import { Plugin } from ${JSON.stringify(fileURLToPath(import.meta.resolve("@opencode/plugin/tui")))}
      import { createPluginSources } from ${JSON.stringify(fileURLToPath(import.meta.resolve("@opencode/plugin/source")))}
      import { ensureRuntimePluginSupport } from ${JSON.stringify(fileURLToPath(import.meta.resolve("@opentui/solid/runtime-plugin-support/configure")))}
      import * as solid from ${JSON.stringify(fileURLToPath(import.meta.resolve("solid-js")))}
      const { createSignal } = solid
      ensureRuntimePluginSupport({ additional: { "@opencode/plugin/tui": { Plugin }, "solid-js": solid } })
      const sources = createPluginSources(async () => {})
      try {
        const loaded = await sources.read(${JSON.stringify(pathToFileURL(path.join(directory, "tui.ts")).href)})
        const [title, rename] = createSignal("Initial title")
        const [status, setStatus] = createSignal("idle")
        const [forms, setForms] = createSignal([])
        const cleanup = await loaded.module.default.setup({
          data: { session: {
            get: () => ({ title: title() }), root: id => id, family: id => [id], status,
            permission: { list: () => [], sync: async () => {} },
            form: { list: forms, sync: async () => {} },
          } },
          ui: { router: { current: () => ({ type: "session", sessionID: "root" }) },
            toast: { show: error => { throw new Error(error.message) } } },
        })
        const report = process.env.PYWORKON_TEST_REPORT
        async function waitFor(value) {
          const deadline = Date.now() + 3000
          while (Date.now() < deadline) {
            if (await Bun.file(report).exists() && (await Bun.file(report).text()).includes(value)) return
            await Bun.sleep(10)
          }
          throw new Error("Missing agent report: " + value)
        }
        try {
          await waitFor("Initial title")
          rename("Renamed title")
          await waitFor("Renamed title")
          setStatus("running")
          await waitFor("working")
          setForms(["pending question"])
          await waitFor("waiting")
        } finally {
          await cleanup()
        }
        await waitFor("--clear")
        console.log(loaded.module.default.id)
      } finally {
        sources.dispose()
      }
    `)
    const executable = path.join(directory, "host")
    const build = Bun.spawn([
      process.execPath, "build", "--compile", "--conditions=browser", harness, "--outfile", executable,
    ], { cwd: import.meta.dir, stdout: "pipe", stderr: "pipe" })
    const [buildErrors, buildExit] = await Promise.all([
      new Response(build.stderr).text(), build.exited,
    ])
    expect({ buildErrors, buildExit }).toEqual({ buildErrors: "", buildExit: 0 })
    if (process.platform === "darwin") {
      const sign = Bun.spawn(["codesign", "--force", "--sign", "-", executable], { stdout: "pipe", stderr: "pipe" })
      const [signErrors, signExit] = await Promise.all([new Response(sign.stderr).text(), sign.exited])
      expect(signExit, signErrors).toBe(0)
    }
    const child = Bun.spawn([executable], {
      cwd: directory, stdout: "pipe", stderr: "pipe",
      env: {
        ...process.env,
        PATH: `${directory}${path.delimiter}${process.env.PATH ?? ""}`,
        TMUX: "test", TMUX_PANE: "%1",
        PYWORKON_TEST_REPORT: path.join(directory, "reports.txt"),
      },
    })
    const [stdout, stderr, exit] = await Promise.all([
      new Response(child.stdout).text(), new Response(child.stderr).text(), child.exited,
    ])
    expect({ stdout, stderr, exit }).toEqual({
      stdout: "pyworkon.agent-status\n", stderr: "", exit: 0,
    })
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
}, 30_000)
