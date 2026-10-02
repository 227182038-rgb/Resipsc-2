/**
 * resipsc instrumentation — server crash protection (PART 3.5).
 *
 * Catches stray asynchronous errors so the server NEVER dies mid-QC.
 * The handlers log and keep running; they must NEVER call process.exit().
 */
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;

  process.on("uncaughtException", (err: Error) => {
    console.error("UNCAUGHT:", err);
  });

  process.on("unhandledRejection", (err: unknown) => {
    console.error("UNHANDLED:", err);
  });
}
