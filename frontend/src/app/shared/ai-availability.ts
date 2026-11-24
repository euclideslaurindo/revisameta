import { Api } from '../core/api/api';
import { aiSettings } from '../core/api/fn/ai/ai-settings';

/** True when the project has the AI on and this function allowed and not switched off. */
export async function aiFunctionAvailable(
  api: Api,
  projectId: string,
  fn: string,
): Promise<boolean> {
  try {
    const s = await api.invoke(aiSettings, { project_id: projectId });
    return s.enabled && s.functions.includes(fn) && !s.disabled_functions[fn];
  } catch {
    return false;
  }
}
