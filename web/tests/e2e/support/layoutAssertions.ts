import { expect, type Page } from "@playwright/test";
import { getUnhandledApiRequests } from "@tests/e2e/support/mockApi";

type NestedOverflowSelector =
  | string
  | {
      selector: string;
      allowHorizontalOverflow?: boolean;
    };

export async function expectNoUnhandledApiRequests(page: Page) {
  const unhandled = getUnhandledApiRequests(page);
  expect(unhandled, `Unhandled /api requests:\n${unhandled.join("\n")}`).toEqual([]);
}

export async function expectNoDocumentHorizontalOverflow(page: Page) {
  const metrics = await page.evaluate(() => ({
    innerWidth: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(
    metrics.scrollWidth,
    `Document scrollWidth ${metrics.scrollWidth} exceeds viewport ${metrics.innerWidth}`,
  ).toBeLessThanOrEqual(metrics.innerWidth + 1);
}

export async function expectNoNestedHorizontalOverflow(
  page: Page,
  selectors: NestedOverflowSelector[],
) {
  const failures = await page.evaluate((items) => {
    return items.flatMap((item) => {
      const selector = typeof item === "string" ? item : item.selector;
      const allowHorizontalOverflow =
        typeof item === "string" ? false : Boolean(item.allowHorizontalOverflow);
      if (allowHorizontalOverflow) return [];

      return Array.from(document.querySelectorAll<HTMLElement>(selector)).flatMap(
        (element, index) => {
          if (element.scrollWidth <= element.clientWidth + 1) return [];
          return [
            {
              selector,
              index,
              clientWidth: element.clientWidth,
              scrollWidth: element.scrollWidth,
              text: element.textContent?.trim().slice(0, 120) ?? "",
            },
          ];
        },
      );
    });
  }, selectors);

  expect(failures, `Nested horizontal overflow:\n${JSON.stringify(failures, null, 2)}`).toEqual([]);
}

export async function expectScrollableToLastMeaningfulElement(
  page: Page,
  containerSelector: string,
  targetSelector: string,
) {
  const result = await page.evaluate(
    ({ containerSelector: containerQuery, targetSelector: targetQuery }) => {
      const container =
        containerQuery === "document"
          ? document.scrollingElement || document.documentElement
          : document.querySelector<HTMLElement>(containerQuery);
      const target = document.querySelector<HTMLElement>(targetQuery);
      if (!container || !target) {
        return {
          ok: false,
          reason: !container ? `Missing ${containerQuery}` : `Missing ${targetQuery}`,
        };
      }

      target.scrollIntoView({ block: "end", inline: "nearest" });
      const targetRect = target.getBoundingClientRect();
      const navRect = document
        .querySelector<HTMLElement>(".mobile-task-nav")
        ?.getBoundingClientRect();
      const viewportBottom = window.innerHeight;
      const occlusionTop = navRect ? Math.max(0, navRect.top) : viewportBottom;
      const visible = targetRect.bottom > 0 && targetRect.top < occlusionTop;

      return {
        ok: visible,
        reason: visible
          ? null
          : `Target rect ${JSON.stringify({
              top: targetRect.top,
              bottom: targetRect.bottom,
            })} is not reachable above fixed mobile nav ${JSON.stringify(
              navRect ? { top: navRect.top, bottom: navRect.bottom } : null,
            )}`,
      };
    },
    { containerSelector, targetSelector },
  );

  expect(result.ok, result.reason ?? "Target should be reachable after scrolling").toBe(true);
}
