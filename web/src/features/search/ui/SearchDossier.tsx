import {
  ResearchFieldGrid,
  ResearchHeader,
  ResearchPanel,
  ResearchSection,
  ResearchTag,
} from "@shared/ui/ResearchPrimitives";

import type { SearchCaseView } from "../model/searchCase";

export function SearchDossier({ view }: { view: SearchCaseView }) {
  return (
    <ResearchPanel
      aria-label={`Search case ${view.title}`}
      className="search-dossier"
      id="overview"
    >
      <ResearchHeader
        badge={<ResearchTag tone={view.resolver.tone}>{view.resultKind}</ResearchTag>}
        eyebrow="search dossier"
        subtitle={view.subtitle}
        title={view.title}
      />
      <ResearchSection title="对象事实">
        <ResearchFieldGrid
          fields={[view.official, view.community, view.market, view.resolver, view.evidence]}
        />
      </ResearchSection>
    </ResearchPanel>
  );
}
