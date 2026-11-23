export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <h1 className="text-4xl font-bold text-workflo-600">Workflo</h1>
      <p className="mt-4 text-lg text-gray-600">
        Verified execution evidence for AI-assisted software changes.
      </p>
      <div className="mt-8 grid grid-cols-3 gap-4">
        <a href="/projects" className="rounded-lg border p-4 hover:border-workflo-500">
          <h2 className="font-semibold">Projects</h2>
          <p className="text-sm text-gray-500">
            Repositories, policy and connected runners
          </p>
        </a>
        <a href="/runs" className="rounded-lg border p-4 hover:border-workflo-500">
          <h2 className="font-semibold">Runs</h2>
          <p className="text-sm text-gray-500">
            Run timeline, reports and signed receipts
          </p>
        </a>
        <a href="/settings" className="rounded-lg border p-4 hover:border-workflo-500">
          <h2 className="font-semibold">Settings</h2>
          <p className="text-sm text-gray-500">
            Inference providers, privacy mode and keys
          </p>
        </a>
      </div>
    </main>
  );
}
