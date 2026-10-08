import express from "express";
import { createServer } from "http";
import path from "path";
import { fileURLToPath } from "url";
import { TrialSignupInputError, createTrialSignup } from "./trialSignups";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function startServer() {
  const app = express();
  const server = createServer(app);
  app.use(express.json({ limit: "8kb" }));

  app.post("/api/trial-signups", async (req, res) => {
    try {
      await createTrialSignup(req.body?.email, req.body?.consent);
      res.status(201).json({ ok: true, message: "Your trial request has been recorded." });
    } catch (error) {
      if (error instanceof TrialSignupInputError) {
        res.status(400).json({ ok: false, message: error.message });
        return;
      }
      console.error("[trial-signup] Unable to record trial request", error);
      res.status(503).json({ ok: false, message: "Trial requests are temporarily unavailable. Please try again." });
    }
  });

  // Serve static files from dist/public in production
  const staticPath =
    process.env.NODE_ENV === "production"
      ? path.resolve(__dirname, "public")
      : path.resolve(__dirname, "..", "dist", "public");

  app.use(express.static(staticPath));

  // Handle client-side routing - serve index.html for all routes
  app.get("*", (_req, res) => {
    res.sendFile(path.join(staticPath, "index.html"));
  });

  const port = process.env.PORT || 3000;

  server.listen(port, () => {
    console.log(`Server running on http://localhost:${port}/`);
  });
}

startServer().catch(console.error);
