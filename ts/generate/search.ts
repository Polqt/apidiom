import type { ToolMetadata } from "./tools";

export interface ScoredTool {
  tool: ToolMetadata;
  score: number;
}

function tokenize(text: string): string[] {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().split(/\s+/).filter(Boolean);
}

export function scoreTools(query: string, tools: ToolMetadata[]): ScoredTool[] {
  const queryTokens = tokenize(query);
  if (queryTokens.length === 0) return [];

  const scored: ScoredTool[] = [];

  for (const tool of tools) {
    const nameTokens = tokenize(tool.name);
    const descTokens = tokenize(tool.description);
    const tagTokens = tool.endpoint.tags.flatMap(tokenize);

    let score = 0;
    let termsCovered = 0;

    for (const qt of queryTokens) {
      let termScore = 0;

      if (nameTokens.includes(qt)) {
        termScore += 10;
      } else if (tool.name.toLowerCase().includes(qt)) {
        termScore += 5;
      }

      if (descTokens.includes(qt)) {
        termScore += 2;
      } else if (tool.description.toLowerCase().includes(qt)) {
        termScore += 1;
      }

      if (tagTokens.includes(qt)) {
        termScore += 3;
      }

      if (termScore > 0) termsCovered++;
      score += termScore;
    }

    if (termsCovered > 0) {
      const coverageRatio = termsCovered / queryTokens.length;
      score = score * (0.5 + 0.5 * coverageRatio);
    }

    if (score > 0) {
      scored.push({ tool, score });
    }
  }

  return scored.sort((a, b) => b.score - a.score);
}
