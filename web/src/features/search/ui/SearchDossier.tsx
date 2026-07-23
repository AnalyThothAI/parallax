import {
  ObsidianCase,
  ObsidianCaseHeader,
  ObsidianFieldGrid,
  ObsidianPill,
  ObsidianSection,
} from "@shared/ui/case-file";

import type { SearchCaseView } from "../model/searchCase";

export function SearchDossier({ view }: { view: SearchCaseView }) {
  return (
    <ObsidianCase aria-label={`Search case ${view.title}`} className="search-dossier" id="overview">
      <ObsidianCaseHeader
        badge={<ObsidianPill tone={view.resolver.tone}>{view.resultKind}</ObsidianPill>}
        eyebrow="search case"
        subtitle={view.subtitle}
        title={view.title}
      />
      <ObsidianSection title="Case file">
        <ObsidianFieldGrid
          fields={[view.official, view.community, view.market, view.resolver, view.evidence]}
        />
      </ObsidianSection>
    </ObsidianCase>
  );
}
