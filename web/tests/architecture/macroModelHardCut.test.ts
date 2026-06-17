import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

const webRoot = process.cwd();
const macroRoot = join(webRoot, "src/features/macro");

const collectSourceFiles = (directory: string): string[] =>
  readdirSync(directory)
    .flatMap((entry) => {
      const path = join(directory, entry);
      const stats = statSync(path);

      if (stats.isDirectory()) {
        return collectSourceFiles(path);
      }

      if (stats.isFile() && (path.endsWith(".ts") || path.endsWith(".tsx"))) {
        return [path];
      }

      return [];
    })
    .sort();

const retiredIdentityFallbackTokens = [
  "`metric:${index}`",
  "`fact:${index}`",
  "`gap:${index}`",
  "`${bucketKey}:${index}`",
  "`row:${rowIndex}`",
  "`row:${index}`",
  "`${stable}:${rowIndex}`",
  'titleByKey[conceptKey] ?? "资产"',
  "`policy-row:${index}`",
  "`curve-row:${index}`",
  "`curve-history:${seriesIndex}`",
  "`tenor:${index}`",
  "`${groupKey}:${index}`",
  "`政策读数 ${index + 1}`",
  "`曲线 ${index + 1}`",
  "`利差历史 ${seriesIndex + 1}`",
  "`期限 ${index + 1}`",
  "`实际利率读数 ${index + 1}`",
  "`点 ${pointIndex + 1}`",
  'conceptKey.split(":")',
  "code.split(/[:_]+/)",
  "`${source}:${index}`",
  'String(chart.status ?? "unknown")',
  'stringValue(value) ?? "unknown"',
  'String(record.headline ?? "今日判断暂不可用")',
  'String(record.status ?? "unknown")',
  'String(record.stance ?? "neutral")',
  'key.split(":").at(-1)',
  'data-severity={item.severity ?? "unknown"}',
  "gapCodeLabel(",
  "GAP_CODE_TERMS",
  "最新宏观观测滞后",
  ".split(/[:_]+/u)",
  'diagnostics.statusLabel ?? "正常"',
  "module.data_health.summary_label ?? module.data_health.summary_status",
  "view.diagnostics.sourceMeta ?? `${sourceCount} 个来源`",
  "stringValue(module.snapshot.status_label) ?? stringValue(module.snapshot.status)",
  "stringValue(module.data_health.summary_label) ??\n      stringValue(module.data_health.summary_status)",
  "TITLE_BY_ID",
  "labelFromIdentifier",
  "WORD_LABELS",
  '.split("_")',
  "node.label ?? node.kind",
  "node.value ?? node.status_label ?? node.status",
  '`${node.label ?? node.kind ?? "node"}:${index}`',
  "`${group.key}:${item.label}:${index}`",
  "String(table.id ?? index)",
  'return explicit ?? "ok";',
  "`${tenorYears}Y`",
  'stringValue(diagnostics.label) ?? "政策走廊诊断"',
  'stringValue(diagnostics.label) ?? "曲线诊断"',
  'stringValue(diagnostics.label) ?? "实际利率诊断"',
  "readHeadline ?? `${ratesTitle(module, moduleId)}：${readinessLabel(readiness)}`",
  "neutralFallbackExplanation(",
  "marketExplanation:",
  "fallback={readSummary}",
  "textValue(brief?.headline) ?? fallback",
  "label ?? `${data.window} 资产相关性矩阵`",
  "meta ?? `${drivers.evidenceCount} 条证据`",
  "fallbackAsOf",
  "存在降级原因",
  'displayText(reason, "存在降级原因")',
  "CORRIDOR_LABELS[CORRIDOR_SERIES_BY_CONCEPT[concept]] ?? concept",
  "stringValue(row.label) ??",
  "stringValue(row.source) ??",
  "stringValue(row.name)",
];

describe("macro model hard cut", () => {
  it("does not restore frontend synthetic identity or asset label fallbacks", () => {
    const offenders = collectSourceFiles(macroRoot).flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredIdentityFallbackTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });
});
