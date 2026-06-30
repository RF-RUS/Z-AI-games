export const SERVICE_PORTS = {
  orchestrator: 8100,
  unoCore: 8101,
  replay: 8102,
  perception: 8103,
  adapterWeb: 8104,
  adapterWindows: 8105,
  decision: 8106,
  policyGuard: 8107,
  chatIntent: 8108,
  chatResponse: 8109,
  modelRegistry: 8110,
  modelRuntime: 8111,
  observability: 8112,
  config: 8113,
} as const;

export async function healthCheck(port: number): Promise<{ service: string; status: string }> {
  const r = await fetch(`http://127.0.0.1:${port}/health`);
  return r.json();
}
