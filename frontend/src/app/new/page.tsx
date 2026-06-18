"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { Server, Template } from "@/lib/types";

export default function NewServer() {
  const router = useRouter();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [selected, setSelected] = useState<Template | null>(null);
  const [name, setName] = useState("");
  const [vars, setVars] = useState<Record<string, string>>({});
  const [created, setCreated] = useState<Server | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.templates().then(setTemplates).catch(() => setError("could not load templates"));
  }, []);

  function pick(t: Template) {
    setSelected(t);
    setVars(Object.fromEntries(t.variables.map((v) => [v.key, v.default])));
    setStep(2);
  }

  async function submit() {
    if (!selected) return;
    setSubmitting(true);
    setError(null);
    try {
      const server = await api.create({ template_id: selected.id, name, variables: vars });
      setCreated(server);
      setStep(3);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl px-6 py-10">
      <Link href="/" className="text-sm text-neutral-500 hover:underline">
        ← Back
      </Link>
      <h1 className="mb-6 mt-2 text-2xl font-semibold">New server</h1>

      {error && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {step === 1 && (
        <div className="grid gap-3">
          <p className="text-sm text-neutral-400">Choose a game template</p>
          {templates.map((t) => (
            <button
              key={t.id}
              onClick={() => pick(t)}
              className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4 text-left hover:border-emerald-600/50"
            >
              <div className="font-medium">{t.name}</div>
              <div className="text-xs text-neutral-500">
                app {t.app_id} · {t.anonymous_login ? "anonymous" : "login required"} ·{" "}
                {t.ports.map((p) => `${p.default}/${p.protocol}`).join(", ")}
              </div>
            </button>
          ))}
        </div>
      )}

      {step === 2 && selected && (
        <div className="grid gap-4">
          <div>
            <label className="mb-1 block text-sm text-neutral-400">Server name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="my-cs2-server"
              className="w-full rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm outline-none focus:border-emerald-600"
            />
            <p className="mt-1 text-xs text-neutral-600">letters, numbers, - and _ only</p>
          </div>

          {selected.variables.map((v) => (
            <div key={v.key}>
              <label className="mb-1 block text-sm text-neutral-400">{v.key}</label>
              <input
                value={vars[v.key] ?? ""}
                onChange={(e) => setVars({ ...vars, [v.key]: e.target.value })}
                placeholder={v.key.toUpperCase().endsWith("PASSWORD") ? "(auto-generated if empty)" : ""}
                className="w-full rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm outline-none focus:border-emerald-600"
              />
            </div>
          ))}

          <div className="flex gap-2">
            <button
              onClick={() => setStep(1)}
              className="rounded-lg border border-neutral-800 px-4 py-2 text-sm hover:bg-neutral-900"
            >
              Back
            </button>
            <button
              onClick={submit}
              disabled={!name || submitting}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
            >
              {submitting ? "Creating…" : "Create server"}
            </button>
          </div>
        </div>
      )}

      {step === 3 && created && (
        <div className="grid gap-4">
          <div className="rounded-xl border border-emerald-600/30 bg-emerald-500/5 p-5">
            <div className="font-medium text-emerald-400">Server created</div>
            <div className="mt-1 text-sm text-neutral-400">{created.name}</div>
            <div className="mt-4 text-sm text-neutral-400">Assigned ports (host):</div>
            <div className="mt-1 flex flex-wrap gap-2">
              {created.ports.map((p) => (
                <span
                  key={`${p.protocol}-${p.host_port}`}
                  className="rounded bg-neutral-800 px-2.5 py-1 font-mono text-sm"
                >
                  {p.host_port}/{p.protocol}
                </span>
              ))}
            </div>
            {Object.entries(created.variables).length > 0 && (
              <div className="mt-4 text-xs text-neutral-500">
                {Object.entries(created.variables).map(([k, v]) => (
                  <div key={k}>
                    <span className="text-neutral-400">{k}</span> = {v}
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => router.push(`/servers/${created.id}`)}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500"
            >
              Open & install
            </button>
            <Link href="/" className="rounded-lg border border-neutral-800 px-4 py-2 text-sm hover:bg-neutral-900">
              Dashboard
            </Link>
          </div>
        </div>
      )}
    </main>
  );
}
