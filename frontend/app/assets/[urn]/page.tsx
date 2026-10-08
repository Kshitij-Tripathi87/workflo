export default async function AssetPage({
  params,
}: {
  // Next.js 15: dynamic route params are async (a Promise) and must be awaited.
  params: Promise<{ urn: string }>;
}) {
  const { urn: rawUrn } = await params;

  // Next.js already URL-decodes route segments, but be defensive against
  // malformed values (URIError on stray escape sequences).
  let urn = "";
  try {
    urn = decodeURIComponent(rawUrn);
  } catch {
    urn = rawUrn || "(malformed)";
  }

  const safe = urn || "(none)";
  return (
    <main style={{ padding: 24 }}>
      <h1>Asset detail</h1>
      <p>{safe}</p>
    </main>
  );
}
