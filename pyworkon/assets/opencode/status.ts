import type { createEffect, createRoot } from "solid-js"

export interface SolidRuntime {
  readonly createEffect: typeof createEffect
  readonly createRoot: typeof createRoot
}

export interface AgentState {
  readonly name: string
  readonly status: "idle" | "working" | "waiting"
}

export interface SessionSource {
  get(sessionID: string): { readonly title?: string } | undefined
  root(sessionID: string): string
  family(sessionID: string): readonly string[]
  status(sessionID: string): "idle" | "running"
  readonly permission: {
    list(sessionID: string): readonly unknown[] | undefined
  }
  readonly form: {
    list(sessionID: string): readonly unknown[] | undefined
  }
}

export function watchAgent(
  source: SessionSource,
  selectedSession: () => string | null,
  pid: number,
  reporter: AgentReporter,
  solid: SolidRuntime,
): () => void {
  return solid.createRoot((dispose) => {
    solid.createEffect(() => {
      void reporter.update(readAgent(source, selectedSession(), pid))
    })
    return dispose
  })
}

export function readAgent(source: SessionSource, sessionID: string | null, pid: number): AgentState | null {
  if (!sessionID) return null
  const root = source.root(sessionID)
  const session = source.get(root)
  if (!session) return null
  const family = [...new Set([root, ...source.family(root)])]
  const waiting = family.some((id) => source.permission.list(id)?.length || source.form.list(id)?.length)
  const working = family.some((id) => source.status(id) === "running")
  return {
    name: session.title || `opencode-${pid}`,
    status: waiting ? "waiting" : working ? "working" : "idle",
  }
}

export function agentArguments(pid: number, state: AgentState | null): string[] {
  const identity = ["agent", "--pid", String(pid)]
  return state
    ? [...identity, "--name", state.name, "--status", state.status]
    : [...identity, "--clear"]
}

export class AgentReporter {
  private pending = Promise.resolve()
  private lastSent: AgentState | null | undefined
  private closed = false
  private failed = false

  constructor(
    private readonly send: (state: AgentState | null) => Promise<void>,
    private readonly onError: (error: unknown) => void,
  ) {}

  update(state: AgentState | null): Promise<void> {
    this.pending = this.pending.then(async () => {
      if (this.closed || (this.lastSent !== undefined &&
        this.lastSent?.name === state?.name && this.lastSent?.status === state?.status)) return
      await this.publish(state)
    })
    return this.pending
  }

  async close(): Promise<void> {
    this.closed = true
    await this.pending
    await this.publish(null)
  }

  private async publish(state: AgentState | null): Promise<void> {
    try {
      await this.send(state)
      this.lastSent = state
      this.failed = false
    } catch (error) {
      if (!this.failed) this.onError(error)
      this.failed = true
    }
  }
}
