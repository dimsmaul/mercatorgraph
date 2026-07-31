// Runtime config for the browser — reads WORKER_URL at request time so a published
// image is not tied to a build-time worker URL.
export const dynamic = 'force-dynamic';

export function GET() {
  return Response.json({
    workerUrl: process.env.WORKER_URL ?? 'http://localhost:8000',
  });
}
