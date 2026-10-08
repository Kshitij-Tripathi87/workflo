export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <h1 className="text-4xl font-bold text-shield-600">Tenant Shield</h1>
      <p className="mt-4 text-lg text-gray-600">
        Multi-tenant isolation testing with SOC 2 evidence reporting.
      </p>
      <div className="mt-8 grid grid-cols-3 gap-4">
        <a href="/runs" className="rounded-lg border p-4 hover:border-shield-500">
          <h2 className="font-semibold">Test Runs</h2>
          <p className="text-sm text-gray-500">View run history and results</p>
        </a>
        <a href="/compliance" className="rounded-lg border p-4 hover:border-shield-500">
          <h2 className="font-semibold">Compliance</h2>
          <p className="text-sm text-gray-500">SOC 2 evidence center</p>
        </a>
        <a href="/settings" className="rounded-lg border p-4 hover:border-shield-500">
          <h2 className="font-semibold">Settings</h2>
          <p className="text-sm text-gray-500">API keys and team management</p>
        </a>
      </div>
    </main>
  );
}
