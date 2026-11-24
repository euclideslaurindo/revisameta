import { createConnection, createServer } from "node:net";

/**
 * The tests share Caddy's network, where Caddy listens on port 80. Users reach it on
 * localhost:8080 (the published port), and signed storage links point there too, so
 * this forwards 8080 -> 80 and the browser uses the very same addresses as a user.
 */
export default async function globalSetup(): Promise<() => Promise<void>> {
  const server = createServer((client) => {
    const upstream = createConnection({ host: "127.0.0.1", port: 80 });
    client.pipe(upstream).pipe(client);
    const close = (): void => {
      client.destroy();
      upstream.destroy();
    };
    client.on("error", close);
    upstream.on("error", close);
  });
  await new Promise<void>((resolve) =>
    server.listen(8080, "127.0.0.1", resolve),
  );
  return () => new Promise<void>((resolve) => server.close(() => resolve()));
}
