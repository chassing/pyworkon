import { describe, expect, test } from "bun:test"
import { setImmediate } from "node:timers/promises"
import { OpenCode, type PermissionRequest, type SessionInfo } from "@opencode/client"
import { createData } from "@opencode/client/solid"
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
    permission: { list: (id) => entries.get(id)?.permissions },
    form: { list: (id) => entries.get(id)?.forms },
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
  test.each(["new", "existing"])("observes %s sessions without issuing its own hydration requests", async (kind) => {
    const info = {
      id: "new-session", projectID: "project", title: "Session title",
      location: { directory: "/project" }, cost: 0,
      tokens: { input: 0, output: 0, reasoning: 0, cache: { read: 0, write: 0 } },
      time: { created: 1, updated: 1 },
    } satisfies SessionInfo
    const permission: PermissionRequest = {
      id: "permission", sessionID: info.id, action: "shell", resources: ["git status"],
    }
    const gate = Promise.withResolvers<void>()
    let persisted = kind === "existing"
    let pending = true
    const requests: string[] = []
    const fetchMock = Object.assign(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(input instanceof Request ? input.url : String(input)).pathname
      const method = init?.method ?? (input instanceof Request ? input.method : "GET")
      requests.push(`${method} ${path}`)
      if (method === "POST" && path === "/api/session") {
        await gate.promise
        persisted = true
        return Response.json({ data: info })
      }
      if (!persisted) return Response.json({
        _tag: "SessionNotFoundError", sessionID: info.id, message: `Session not found: ${info.id}`,
      }, { status: 404 })
      if (path.endsWith("/permission")) return Response.json({ data: pending ? [permission] : [] })
      if (path.endsWith("/form")) return Response.json({ data: [] })
      throw new Error(`Unexpected request: ${method} ${path}`)
    }, { preconnect: () => {} })
    const api = OpenCode.make({ baseUrl: "http://mock.invalid", fetch: fetchMock })
    const host = createRoot((dispose) => ({
      dispose,
      data: createData({
        api: () => api, directory: "/project",
        event: { on: () => () => {}, listen: () => () => {} },
      }),
    }))
    const created = kind === "new" ? host.data.session.create({
      id: info.id, title: info.title, location: info.location,
    }) : undefined
    if (!created) host.data.session.remember(info)
    const sent: (AgentState | null)[] = []
    const errors: unknown[] = []
    const reporter = new AgentReporter(async (state) => { sent.push(state) }, (error) => { errors.push(error) })
    const dispose = watchAgent(host.data.session, () => info.id, 123, reporter, { createEffect, createRoot })
    try {
      await setImmediate()
      expect(host.data.session.get(info.id)?.title).toBe(info.title)
      expect(persisted).toBe(kind === "existing")
      expect(errors).toEqual([])
      expect(requests).toEqual(created ? ["POST /api/session"] : [])
      expect(sent.at(-1)).toEqual({ name: info.title, status: "idle" })

      gate.resolve()
      await created?.request
      await Promise.all([
        host.data.session.permission.sync(info.id), host.data.session.form.sync(info.id),
      ])
      await setImmediate()
      expect(sent.at(-1)?.status).toBe("waiting")
      host.data.session.setStatus(info.id, "running")
      pending = false
      host.data.session.permission.invalidate(info.id)
      await host.data.session.permission.sync(info.id)
      await setImmediate()
      expect(sent.at(-1)?.status).toBe("working")
      host.data.session.setStatus(info.id, "idle")
      await setImmediate()
      expect(sent.at(-1)?.status).toBe("idle")
      expect(errors).toEqual([])
    } finally {
      gate.resolve()
      await created?.request
      dispose()
      host.dispose()
      await reporter.close()
    }
  })

  test("clears a missing root session and resumes reporting when cached", async () => {
    const { source: base } = sessions()
    const [available, setAvailable] = createSignal(false)
    const sent: (AgentState | null)[] = []
    const source: SessionSource = {
      ...base,
      get: (id) => id === "root" && !available() ? undefined : base.get(id),
    }
    const reporter = new AgentReporter(async (state) => { sent.push(state) }, () => {})
    const dispose = watchAgent(source, () => "root", 123, reporter, { createEffect, createRoot })
    try {
      await setImmediate()
      expect(sent.at(-1)).toBeNull()
      setAvailable(true)
      await setImmediate()
      expect(sent.at(-1)).toEqual({ name: "Implement feature", status: "idle" })
      setAvailable(false)
      await setImmediate()
      expect(sent.at(-1)).toBeNull()
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
    const source: SessionSource = {
      ...base,
      get: (id) => id === "root" ? { title: title() } : base.get(id),
      status: (id) => id === "root" ? status() : base.status(id),
      form: {
        list: (id) => id === "child" ? forms() : [],
      },
    }
    const reporter = new AgentReporter(async (state) => { sent.push(state) }, (error) => { errors.push(error) })
    const dispose = watchAgent(source, selected, 123, reporter, { createEffect, createRoot })
    await setImmediate()
    expect(sent.at(-1)).toEqual({ name: "Initial title", status: "idle" })

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

  test("observes existing permission requests hydrated by the host after attaching", async () => {
    const { source: base } = sessions()
    const [requests, setRequests] = createSignal<string[]>([])
    const source: SessionSource = {
      ...base,
      permission: {
        list: () => requests(),
      },
    }
    const sent: (AgentState | null)[] = []
    const reporter = new AgentReporter(async (state) => { sent.push(state) }, () => {})
    const dispose = watchAgent(source, () => "root", 123, reporter, { createEffect, createRoot })
    await setImmediate()
    expect(sent.at(-1)?.status).toBe("idle")
    setRequests(["existing request"])
    await setImmediate()
    expect(sent.at(-1)?.status).toBe("waiting")
    dispose()
    await reporter.close()
  })
})
