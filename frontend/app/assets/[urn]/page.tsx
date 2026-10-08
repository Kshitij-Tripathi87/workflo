export default function AssetPage({ params }: { params: { urn: string } }) {
  // Next.js already URL-decodes route segments, but be defensive against
  // malformed values (URIError on stray escape sequences).
  let urn = "";
  try {
    urn = decodeURIComponent(params.urn);
  } catch {
    urn = params.urn || "(malformed)";
  }

  const safe = urn || "(none)";
  return (
    <main style={{ padding: 24 }}>
      <h1>Asset detail</h1>
      <p>{safe</p>
  </main>
  );
}
