import { describe, expect, test } from "bun:test"
import { setImmediate } from "node:timers/promises"
import { createEffect, createRoot, createSignal } from "solid-js"
import { AgentReporter, agentArguments, readAgent, watchAgent, type AgentState, type SessionSource } from "./status"

interface TestSession {
  title: string
  running: boolean
  permissions: string[]
  forms: string[]
}

function sessions() {
  const entries = new Map<string, TestSession>([
    ["root", { title: "Implement feature", running: false, permissions: [], forms: [] }],
    ["child", { title: "Research", running: false, permissions: [], forms: [] }],
    ["other", { title: "Other project", running: true, permissions: ["p"], forms: [] }],
  ])
  const source: SessionSource = {
    get: (id) => entries.get(id),
    root: (id) => id === "child" ? "root" : id,
    family: (id) => id === "root" ? ["root", "child"] : [id],
    status: (id) => entries.get(id)?.running ? "running" : "idle",
    permission: { list: (id) => entries.get(id)?.permissions, sync: async () => {} },
    form: { list: (id) => entries.get(id)?.forms, sync: async () => {} },
  }
  const session = (id: string) => {
    const entry = entries.get(id)
    if (!entry) throw new Error(`Unknown test session: ${id}`)
    return entry
  }
  return { session, source }
}

describe("session state", () => {
  test("uses the session title and ignores unrelated projects", () => {
    expect(readAgent(sessions().source, "root", 123)).toEqual({ name: "Implement feature", status: "idle" })
  })

  test.each(["root", "child"])("includes working activity from %s", (id) => {
    const { session, source } = sessions()
    session(id).running = true
    expect(readAgent(source, "root", 123)?.status).toBe("working")
  })

  test.each(["permissions", "forms"] as const)("%s take precedence over working", (field) => {
    const { session, source } = sessions()
    session("root").running = true
    session("child")[field].push("pending")
    expect(readAgent(source, "root", 123)?.status).toBe("waiting")
    session("child")[field] = []
    expect(readAgent(source, "root", 123)?.status).toBe("working")
    session("root").running = false
    expect(readAgent(source, "root", 123)?.status).toBe("idle")
  })

  test("follows root titles when viewing a child and updates renamed titles", () => {
    const { session, source } = sessions()
    expect(readAgent(source, "child", 123)?.name).toBe("Implement feature")
    session("root").title = "New title"
    expect(readAgent(source, "child", 123)?.name).toBe("New title")
  })

  test("switches sessions without leaking old activity", () => {
    const { source } = sessions()
    expect(readAgent(source, "other", 123)).toEqual({ name: "Other project", status: "waiting" })
    expect(readAgent(source, "root", 123)?.status).toBe("idle")
  })

  test("clears on home or missing sessions and falls back for untitled sessions", () => {
    const { session, source } = sessions()
    expect(readAgent(source, null, 123)).toBeNull()
    expect(readAgent(source, "missing", 123)).toBeNull()
    session("root").title = ""
    expect(readAgent(source, "root", 123)?.name).toBe("opencode-123")
  })
})

describe("daemon reporting", () => {
  test("passes stable identity and titles as literal arguments, never shell text", () => {
    expect(agentArguments(123, { name: "title ' $(touch file)", status: "waiting" })).toEqual([
      "agent", "--pid", "123", "--name", "title ' $(touch file)", "--status", "waiting",
    ])
    expect(agentArguments(123, null)).toEqual(["agent", "--pid", "123", "--clear"])
  })

  test("serializes updates, deduplicates them, and clears last on cleanup", async () => {
    const sent: unknown[] = []
    const reporter = new AgentReporter(async (state) => { sent.push(state) }, () => {})
    const idle = { name: "Title", status: "idle" } as const
    const working = { name: "Title", status: "working" } as const
    const first = reporter.update(idle)
    const duplicate = reporter.update(idle)
    const second = reporter.update(working)
    await Promise.all([first, duplicate, second])
    await reporter.close()
    await reporter.update(working)
    expect(sent).toEqual([idle, working, null])
  })

  test("cleanup waits for in-flight writes and drops queued stale updates", async () => {
    const sent: unknown[] = []
    const blocked = Promise.withResolvers<void>()
    const started = Promise.withResolvers<void>()
    const reporter = new AgentReporter(async (state) => {
      if (state) {
        started.resolve()
        await blocked.promise
      }
      sent.push(state)
    }, () => {})
    void reporter.update({ name: "Title", status: "working" })
    await started.promise
    void reporter.update({ name: "Old queued update", status: "idle" })
    const closed = reporter.close()
    blocked.resolve()
    await closed
    expect(sent).toEqual([{ name: "Title", status: "working" }, null])
  })

  test("failures do not escape and identical states can retry", async () => {
    let attempts = 0
    const errors: unknown[] = []
    const reporter = new AgentReporter(async () => {
      if (++attempts < 3) throw new Error("daemon unavailable")
    }, (error) => { errors.push(error) })
    const state = { name: "Title", status: "idle" } as const
    await reporter.update(state)
    await reporter.update(state)
    await reporter.update(state)
    await reporter.update(state)
    expect(attempts).toBe(3)
    expect(errors).toHaveLength(1)
    await reporter.close()
  })
})

describe("reactive CLI bridge", () => {
  test.each(["root", "child"])("skips missing %s sessions and resumes synchronization when cached", async (missing) => {
    const { source: base } = sessions()
    const [available, setAvailable] = createSignal(false)
    const synced: string[] = []
    const sent: (AgentState | null)[] = []
    const errors: unknown[] = []
    const get = (id: string) => id === missing && !available() ? undefined : base.get(id)
    const sync = async (kind: string, id: string) => {
      synced.push(`${kind}:${id}`)
      if (!get(id)) throw new Error(`Session not found: ${id}`)
    }
    const source: SessionSource = {
      ...base,
      get,
      permission: { ...base.permission, sync: (id) => sync("permission", id) },
      form: { ...base.form, sync: (id) => sync("form", id) },
    }
    const reporter = new AgentReporter(async (state) => { sent.push(state) }, (error) => { errors.push(error) })
    const dispose = watchAgent(source, () => "root", 123, reporter, (error) => { errors.push(error) }, { createEffect, createRoot })
    try {
      await setImmediate()
      expect(synced).toEqual(missing === "root" ? [] : ["permission:root", "form:root"])
      expect(errors).toEqual([])

      synced.length = 0
      setAvailable(true)
      await setImmediate()
      expect(synced).toEqual(["permission:root", "form:root", "permission:child", "form:child"])
      expect(sent.at(-1)).toEqual({ name: "Implement feature", status: "idle" })

      synced.length = 0
      setAvailable(false)
      await setImmediate()
      expect(synced).toEqual(missing === "root" ? [] : ["permission:root", "form:root"])
      if (missing === "root") expect(sent.at(-1)).toBeNull()
      expect(errors).toEqual([])
    } finally {
      dispose()
      await reporter.close()
    }
  })

  test("reports synchronization failures for existing sessions", async () => {
    const { source: base } = sessions()
    const failure = new Error("server unavailable")
    const source: SessionSource = {
      ...base,
      permission: { ...base.permission, sync: async () => { throw failure } },
    }
    const errors: unknown[] = []
    const reporter = new AgentReporter(async () => {}, (error) => { errors.push(error) })
    const dispose = watchAgent(source, () => "root", 123, reporter, (error) => { errors.push(error) }, { createEffect, createRoot })
    try {
      await setImmediate()
      expect(errors).toEqual([failure])
    } finally {
      dispose()
      await reporter.close()
    }
  })

  test("observes titles, status, questions, route changes and home without polling", async () => {
    const { source: base } = sessions()
    const [selected, select] = createSignal<string | null>("root")
    const [title, rename] = createSignal("Initial title")
    const [status, setStatus] = createSignal<"idle" | "running">("idle")
    const [forms, setForms] = createSignal<string[]>([])
    const sent: (AgentState | null)[] = []
    const errors: unknown[] = []
    const synced: string[] = []
    const source: SessionSource = {
      ...base,
      get: (id) => id === "root" ? { title: title() } : base.get(id),
      status: (id) => id === "root" ? status() : base.status(id),
      form: {
        list: (id) => id === "child" ? forms() : [],
        sync: async (id) => { synced.push(id) },
      },
    }
    const reporter = new AgentReporter(async (state) => { sent.push(state) }, (error) => { errors.push(error) })
    const dispose = watchAgent(source, selected, 123, reporter, (error) => { errors.push(error) }, { createEffect, createRoot })
    await setImmediate()
    expect(sent.at(-1)).toEqual({ name: "Initial title", status: "idle" })
    expect(synced).toEqual(["root", "child"])

    setStatus("running")
    await setImmediate()
    expect(sent.at(-1)?.status).toBe("working")
    setForms(["question"])
    await setImmediate()
    expect(sent.at(-1)?.status).toBe("waiting")
    setForms([])
    rename("Renamed title")
    await setImmediate()
    expect(sent.at(-1)).toEqual({ name: "Renamed title", status: "working" })
    setStatus("idle")
    await setImmediate()
    expect(sent.at(-1)?.status).toBe("idle")

    select("other")
    await setImmediate()
    expect(sent.at(-1)).toEqual({ name: "Other project", status: "waiting" })
    select(null)
    await setImmediate()
    expect(sent.at(-1)).toBeNull()
    dispose()
    const count = sent.length
    select("root")
    rename("Must not publish after disposal")
    await setImmediate()
    expect(sent).toHaveLength(count)
    expect(errors).toEqual([])
    await reporter.close()
  })

  test("hydrates existing permission requests when attaching to a running session", async () => {
    const { source: base } = sessions()
    const [requests, setRequests] = createSignal<string[]>([])
    const source: SessionSource = {
      ...base,
      permission: {
        list: () => requests(),
        sync: async () => {
          await setImmediate()
          setRequests(["existing request"])
        },
      },
    }
    const sent: (AgentState | null)[] = []
    const reporter = new AgentReporter(async (state) => { sent.push(state) }, () => {})
    const dispose = watchAgent(source, () => "root", 123, reporter, () => {}, { createEffect, createRoot })
    await setImmediate()
    expect(sent.at(-1)?.status).toBe("waiting")
    dispose()
    await reporter.close()
  })
})
